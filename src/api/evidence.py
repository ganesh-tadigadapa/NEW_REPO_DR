"""Per-scan evidence files and the clinician-review ledger.

Two stores, deliberately separate from each other and from the account store:

  `scan_evidence/{scan_id}.json`
      The full /v1/analyze response for one scan — images, Grad-CAM, lesion detail,
      rule findings. This is what lets a verified doctor reopen a report later. It is
      written by the API layer AFTER the pipeline has returned, so `pipeline.py` is
      untouched and knows nothing about who is allowed to read this.

  `clinician_reviews.json`
      An APPEND-ONLY ledger of doctor reviews, keyed by scan id. Reviews are never
      written into the scan record and never overwrite anything. The AI's grade, the
      rule engine's grade and the clinician's opinion are three separate facts about the
      same scan, and the audit trail is the whole point: you can always answer "what did
      the model say, and what did the human say, and when?"
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.auth import config as cfg

log = logging.getLogger("dr-api.evidence")

_LOCK = threading.RLock()

# Review statuses a clinician may record. Nothing here changes the AI prediction.
REVIEW_STATUSES = ("reviewed", "needs_further_review", "confirmed", "disagreed")
REVIEW_STATUS_LABELS = {
    "reviewed": "Reviewed",
    "needs_further_review": "Needs further review",
    "confirmed": "Confirmed",
    "disagreed": "Disagreed",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_id(scan_id: str) -> str:
    """Scan ids come from the pipeline, but this value becomes a filename, so it is
    constrained here rather than trusted."""
    keep = [c for c in str(scan_id) if c.isalnum() or c in "-_"]
    return "".join(keep)[:64]


class EvidenceStore:
    def __init__(self, directory: Path | None = None, enabled: bool | None = None):
        self.dir = Path(directory or cfg.SCAN_EVIDENCE_DIR)
        self.enabled = cfg.STORE_SCAN_EVIDENCE if enabled is None else enabled
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, result: dict) -> bool:
        """Persist one analyse result. Failure is logged and swallowed: a doctor losing
        the ability to reopen a report later must never turn a successful screening into
        an error for the health worker in front of the patient."""
        if not self.enabled:
            return False
        sid = _safe_id(result.get("scan_id", ""))
        if not sid:
            return False
        try:
            payload = dict(result)
            # The PDF is regenerable and large; the images are what a reviewer needs.
            payload.pop("report", None)
            path = self.dir / f"{sid}.json"
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload))
            os.replace(tmp, path)
            return True
        except Exception:                            # noqa: BLE001
            log.exception("evidence write failed for %s (screening result unaffected)", sid)
            return False

    def load(self, scan_id: str) -> dict | None:
        sid = _safe_id(scan_id)
        path = self.dir / f"{sid}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:                            # noqa: BLE001
            log.exception("evidence read failed for %s", sid)
            return None


class ClinicianReviewLedger:
    """Append-only. `record()` adds; nothing ever edits or deletes."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or (cfg.SCAN_EVIDENCE_DIR.parent / "clinician_reviews.json"))
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def _read(self) -> list:
        try:
            return json.loads(self.path.read_text())
        except Exception:                            # noqa: BLE001
            return []

    def record(self, scan_id: str, *, status: str, reviewer_account_id: str,
               notes: str = "", clinician_grade: int | None = None) -> dict:
        entry = {
            "scan_id": scan_id,
            "status": status,
            "status_label": REVIEW_STATUS_LABELS.get(status, status),
            # The clinician's own grade, when they choose to give one. Stored in its own
            # field; the AI grade is in the scan record and is never touched by this.
            "clinician_grade": clinician_grade,
            "notes": notes,
            "reviewed_by": reviewer_account_id,
            "reviewed_at": _now(),
        }
        with _LOCK:
            rows = self._read()
            rows.append(entry)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(rows, indent=2))
            os.replace(tmp, self.path)
        return entry

    def history(self, scan_id: str) -> list[dict]:
        return [r for r in self._read() if r.get("scan_id") == scan_id]

    def latest(self, scan_id: str) -> dict | None:
        h = self.history(scan_id)
        return h[-1] if h else None

    def latest_by_scan(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for r in self._read():
            out[r.get("scan_id")] = r
        return out


_EVIDENCE: EvidenceStore | None = None
_LEDGER: ClinicianReviewLedger | None = None


def get_evidence_store() -> EvidenceStore:
    global _EVIDENCE
    if _EVIDENCE is None:
        _EVIDENCE = EvidenceStore()
    return _EVIDENCE


def get_review_ledger() -> ClinicianReviewLedger:
    global _LEDGER
    if _LEDGER is None:
        _LEDGER = ClinicianReviewLedger()
    return _LEDGER


def set_stores(evidence: EvidenceStore | None, ledger: ClinicianReviewLedger | None) -> None:
    """Test seam."""
    global _EVIDENCE, _LEDGER
    _EVIDENCE, _LEDGER = evidence, ledger
