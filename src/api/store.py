"""Scan + review persistence.

Firestore in the cloud, a local JSON file when there is no GCP. The interface is
identical so the API never branches on which one is live — and, importantly, the app
runs and demos with zero cloud dependencies, which is what let us keep building while
the billing account was closed.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()


class LocalStore:
    """Append-only JSON store. Good enough for a screening demo; not a database."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text("[]")

    def _read(self) -> list:
        try:
            return json.loads(self.path.read_text())
        except Exception:
            return []

    def _write(self, rows: list) -> None:
        self.path.write_text(json.dumps(rows, indent=2))

    def save_scan(self, rec: dict) -> None:
        with _LOCK:
            rows = self._read()
            rows.append(rec)
            self._write(rows[-500:])

    def save_review(self, scan_id: str, review: dict) -> bool:
        with _LOCK:
            rows = self._read()
            for r in rows:
                if r.get("scan_id") == scan_id:
                    r["review"] = {**review,
                                   "recorded_at": datetime.now(timezone.utc)
                                   .isoformat().replace("+00:00", "Z")}
                    self._write(rows)
                    return True
            return False

    def list_scans(self, limit: int = 50) -> list:
        return list(reversed(self._read()))[:limit]

    @property
    def backend(self) -> str:
        return f"local-json:{self.path.name}"


class FirestoreStore:
    def __init__(self, collection: str = "scans"):
        from google.cloud import firestore          # imported lazily
        self.db = firestore.Client()
        self.col = collection

    def save_scan(self, rec: dict) -> None:
        self.db.collection(self.col).document(rec["scan_id"]).set(rec)

    def save_review(self, scan_id: str, review: dict) -> bool:
        ref = self.db.collection(self.col).document(scan_id)
        if not ref.get().exists:
            return False
        ref.update({"review": {**review,
                               "recorded_at": datetime.now(timezone.utc)
                               .isoformat().replace("+00:00", "Z")}})
        return True

    def list_scans(self, limit: int = 50) -> list:
        q = (self.db.collection(self.col)
             .order_by("created_at", direction="DESCENDING").limit(limit))
        return [d.to_dict() for d in q.stream()]

    @property
    def backend(self) -> str:
        return "firestore"


def get_store():
    if os.getenv("USE_FIRESTORE", "").lower() in ("1", "true", "yes"):
        try:
            return FirestoreStore()
        except Exception as e:                     # noqa: BLE001
            print(f"[store] Firestore unavailable ({e}); falling back to local JSON")
    from src.common.config import REPO_ROOT
    return LocalStore(Path(os.getenv("LOCAL_STORE_PATH",
                                     str(REPO_ROOT / "data" / "interim" / "scans.json"))))
