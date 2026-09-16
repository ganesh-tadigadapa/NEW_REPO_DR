"""The report PDF, kept exactly as the pipeline produced it, plus who it belongs to.

Three problems this file solves, and nothing else:

  1. **The PDF exists for one HTTP response and then it is gone.** `pipeline.py` renders
     it into the `/v1/analyze` body, and `EvidenceStore` deliberately strips it before
     writing the evidence file. To deliver that report later, the bytes have to be kept.
     `save()` is handed the SAME bytes the browser received — it never re-renders, never
     re-runs the model, never touches the image again.

  2. **The scan record has no owner, on purpose.** `/v1/analyze` does not write the
     caller onto the scan, because the screening result must not depend on who uploaded
     the image. So ownership is recorded HERE, in the delivery layer, in a separate file
     from the medical record. The pipeline still knows nothing about accounts.

  3. **Twilio has to fetch the PDF over the public internet.** A session token cannot
     travel to Twilio, so the media URL carries an HMAC signature instead: bound to one
     scan id, expiring in minutes, and useless for any other file. There is no endpoint
     anywhere that takes a path.

What is NOT here: a directory listing, a "latest report" lookup, a scan-id search, or
any way to reach a file by anything other than a signed token for that exact id.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

from src.delivery import config as cfg

log = logging.getLogger("dr-delivery.media")

_LOCK = threading.RLock()

# Domain separation. A signature produced for a media URL must be worthless as a session
# token and vice versa, even though both are keyed with AUTH_SECRET.
_PURPOSE = "carebridge-report-media-v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def safe_scan_id(scan_id: str) -> str:
    """A scan id is about to become a filename, so it is CONSTRAINED, not trusted.

    Alphanumerics, dash and underscore only. Every `.`, `/` and `\\` is dropped, which
    is what makes `../../etc/passwd` resolve to `etcpasswd` — a name that does not exist
    — instead of escaping the directory. The store then builds its own path from this
    value; no caller-supplied string ever reaches `Path()`.
    """
    keep = [c for c in str(scan_id or "") if c.isalnum() or c in "-_"]
    return "".join(keep)[:64]


# --------------------------------------------------------------------- signing
def _sign(scan_id: str, expires_at: int) -> str:
    msg = f"{_PURPOSE}|{scan_id}|{expires_at}".encode()
    digest = hmac.new(cfg.signing_secret().encode(), msg, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def mint_media_token(scan_id: str, ttl: int | None = None) -> tuple[str, int]:
    """A one-report, time-limited capability. Returns (token, expiry epoch seconds)."""
    ttl = ttl or cfg.REPORT_MEDIA_TTL_SECONDS
    expires_at = int(datetime.now(timezone.utc).timestamp()) + max(30, ttl)
    return f"{expires_at}.{_sign(safe_scan_id(scan_id), expires_at)}", expires_at


def verify_media_token(scan_id: str, token: str) -> bool:
    """True only for a live signature over THIS scan id.

    Note the order: the signature is checked before the expiry is trusted, because the
    expiry is part of the signed string. An attacker editing the timestamp invalidates
    the signature rather than extending the lifetime.
    """
    try:
        raw_exp, sig = str(token).split(".", 1)
        expires_at = int(raw_exp)
    except (ValueError, AttributeError):
        return False
    if not hmac.compare_digest(_sign(safe_scan_id(scan_id), expires_at), sig):
        return False
    return datetime.now(timezone.utc).timestamp() <= expires_at


def media_url(scan_id: str, ttl: int | None = None) -> tuple[str, int]:
    """The absolute URL handed to Twilio. Built from PUBLIC_BASE_URL, which is operator
    configuration — never from a request header, which a caller controls."""
    sid = safe_scan_id(scan_id)
    token, expires_at = mint_media_token(sid, ttl)
    return f"{cfg.PUBLIC_BASE_URL}/v1/reports/media/{sid}.pdf?token={token}", expires_at


# ----------------------------------------------------------------------- store
class ReportMediaStore:
    """`{scan_id}.pdf` next to `{scan_id}.json`. Two small files, one directory."""

    def __init__(self, directory: Path | None = None, enabled: bool | None = None):
        self.dir = Path(directory or cfg.REPORT_MEDIA_DIR)
        self.enabled = cfg.STORE_REPORT_PDF if enabled is None else enabled
        if self.enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    # -- paths: the only two places a path is constructed ---------------------
    def _pdf_path(self, sid: str) -> Path:
        return self.dir / f"{sid}.pdf"

    def _meta_path(self, sid: str) -> Path:
        return self.dir / f"{sid}.json"

    # -- write ----------------------------------------------------------------
    def save(self, result: dict, pdf_bytes: bytes, *, account_id: str,
             kind: str = "screening_report") -> bool:
        """Keep the finished report. Called AFTER `/v1/analyze` has its answer.

        Best effort, exactly like the evidence store: a patient losing the option to
        forward their report must never turn a successful screening into an error for
        the health worker standing in front of them.

        The metadata is a WHITELIST built field by field — there is no `**result` here,
        and there must not be. `patient_ref` is free text that may hold a name, so it is
        not copied; the grade fields are copied VERBATIM from the result so the WhatsApp
        message can never disagree with the PDF.

        `kind` says WHICH document this is. It exists because this store now holds two:
        the screening report, and the Eye Health Passport comparison report
        (src/passport/media.py). They are sent by different endpoints composing different
        wording, so the send path checks the kind rather than assuming every PDF in here
        is a screening report — see `routes.py`.
        """
        if not self.enabled or not pdf_bytes:
            return False
        sid = safe_scan_id(result.get("scan_id", ""))
        if not sid or not account_id:
            return False
        grading = result.get("grading") or {}
        quality = result.get("quality") or {}
        meta = {
            "scan_id": sid,
            "kind": kind,
            "created_at": result.get("created_at") or _now(),
            # The owner. Recorded here and nowhere in the medical record.
            "account_id": account_id,
            "filename": ((result.get("report") or {}).get("filename")
                         or f"dr-report-{sid}.pdf"),
            "size_bytes": len(pdf_bytes),
            # Copied, not derived. Used only to compose the message text.
            "icdr_grade": grading.get("icdr_grade"),
            "icdr_label": grading.get("icdr_label"),
            "referable": grading.get("referable"),
            "gradeable": quality.get("gradeable"),
            "deliveries": [],
        }
        try:
            with _LOCK:
                tmp = self._pdf_path(sid).with_suffix(".pdf.tmp")
                tmp.write_bytes(pdf_bytes)
                os.replace(tmp, self._pdf_path(sid))
                self._write_meta(sid, meta)
            return True
        except Exception:                                # noqa: BLE001
            log.exception("report media write failed for %s (screening result unaffected)",
                          sid)
            return False

    def _write_meta(self, sid: str, meta: dict) -> None:
        tmp = self._meta_path(sid).with_suffix(".json.tmp")
        tmp.write_text(json.dumps(meta))
        os.replace(tmp, self._meta_path(sid))

    # -- read -----------------------------------------------------------------
    def meta(self, scan_id: str) -> dict | None:
        sid = safe_scan_id(scan_id)
        if not sid:
            return None
        path = self._meta_path(sid)
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())
        except Exception:                                # noqa: BLE001
            log.exception("report media metadata unreadable for %s", sid)
            return None

    def pdf_path(self, scan_id: str) -> Path | None:
        """The file, or None. The returned path is built from the sanitised id, so it is
        always inside `self.dir` by construction rather than by checking afterwards."""
        sid = safe_scan_id(scan_id)
        if not sid:
            return None
        path = self._pdf_path(sid)
        return path if path.exists() else None

    def owned_by(self, scan_id: str, account_id: str) -> bool:
        meta = self.meta(scan_id)
        return bool(meta and meta.get("account_id") and meta["account_id"] == account_id)

    # -- deliveries ------------------------------------------------------------
    def last_delivery(self, scan_id: str, channel: str = "whatsapp") -> dict | None:
        meta = self.meta(scan_id) or {}
        rows = [d for d in (meta.get("deliveries") or []) if d.get("channel") == channel]
        return rows[-1] if rows else None

    def record_delivery(self, scan_id: str, *, channel: str, provider_message_id: str | None,
                        status: str | None, to_masked: str) -> dict | None:
        """Append one delivery. The recipient is stored MASKED — the full number lives in
        the account record and has no reason to be duplicated here."""
        sid = safe_scan_id(scan_id)
        entry = {
            "channel": channel,
            "provider_message_id": provider_message_id,
            "status": status,
            "to_masked": to_masked,
            "sent_at": _now(),
        }
        try:
            with _LOCK:
                meta = self.meta(sid)
                if meta is None:
                    return None
                meta.setdefault("deliveries", []).append(entry)
                self._write_meta(sid, meta)
            return entry
        except Exception:                                # noqa: BLE001
            log.exception("delivery record write failed for %s", sid)
            return entry


_STORE: ReportMediaStore | None = None


def get_media_store() -> ReportMediaStore:
    global _STORE
    if _STORE is None:
        _STORE = ReportMediaStore()
    return _STORE


def set_media_store(store: ReportMediaStore | None) -> None:
    """Test seam."""
    global _STORE
    _STORE = store
