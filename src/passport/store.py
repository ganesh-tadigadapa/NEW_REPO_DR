"""The longitudinal record: screenings, follow-up plans, and doctor access grants.

Four JSON documents in one directory, written under a process lock and replaced
atomically — the same shape as `src/auth/storage.py`, and deliberately a SEPARATE set of
files from both the account store and the medical scan store.

**What a screening row holds, and why it is short.** Exactly the fields the longitudinal
feature needs to draw a timeline, compare two results and decide a follow-up window:
identity, time, grade, severity, quality, referral, confidence, and whether a report
exists. It is built field by field in `screening_record()` — there is no `**result`
anywhere in this module, and there must not be one. In particular `patient_ref` (free
text that may hold a name), the images, the Grad-CAM and the lesion detail are NOT
copied: the full evidence already lives in `src/api/evidence.py` for the doctors who are
allowed to open it.

**Ownership lives here.** `account_id` is on the passport row, never on the medical scan
record — see the package docstring.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.auth import config as auth_cfg
from src.common.config import ICDR_LABELS
from src.passport import config as cfg

log = logging.getLogger("dr-passport.store")

_LOCK = threading.RLock()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def safe_id(raw: str) -> str:
    """Ids reach URLs and comparisons; they are constrained rather than trusted."""
    keep = [c for c in str(raw or "") if c.isalnum() or c in "-_"]
    return "".join(keep)[:64]


def quality_status(gradeable: bool | None) -> str:
    """The same three-way vocabulary the doctor-facing reports API already uses."""
    if gradeable is True:
        return "pass"
    if gradeable is False:
        return "refused"
    return "unknown"


def screening_record(result: dict, *, account_id: str) -> dict:
    """One passport row, built from an `/v1/analyze` response. A WHITELIST.

    Every clinical value is copied verbatim from what the pipeline already decided.
    Nothing is recomputed, re-thresholded or inferred here.
    """
    grading = result.get("grading") or {}
    quality = result.get("quality") or {}
    grade = grading.get("icdr_grade")
    return {
        "screening_id": safe_id(result.get("scan_id", "")),
        "account_id": account_id,
        "created_at": result.get("created_at") or now_iso(),
        # --- what the model said, verbatim ---------------------------------
        "icdr_grade": grade,
        "severity_label": (grading.get("icdr_label")
                           or (ICDR_LABELS.get(grade) if grade is not None else None)),
        "referable": grading.get("referable"),
        "confidence": grading.get("confidence"),
        # --- whether the image could be graded at all -----------------------
        "gradeable": quality.get("gradeable"),
        "quality_status": quality_status(quality.get("gradeable")),
        # --- what the patient can be given ----------------------------------
        "report_available": bool((result.get("report") or {}).get("pdf_b64")),
        "model_id": result.get("model_id"),
    }


# Unambiguous alphabet: no O/0, no I/1/L. A share code is read aloud across a desk or
# copied off a phone screen, and "was that an O or a zero?" is a support call.
_CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_CODE_LENGTH = 8
# Domain separation, so a share-code hash is worthless as a session token or an OTP hash
# even though all three are keyed with AUTH_SECRET.
_CODE_PURPOSE = "carebridge-passport-share-code-v1"


def generate_share_code() -> str:
    """A short capability, formatted for a human to read out. ~31^8 ≈ 8.5e11 values."""
    raw = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LENGTH))
    return f"{raw[:4]}-{raw[4:]}"


def normalise_share_code(raw: str) -> str:
    """What the doctor typed -> the canonical form. Case and dashes do not matter."""
    keep = [c for c in str(raw or "").upper() if c.isalnum()]
    joined = "".join(keep)[:_CODE_LENGTH]
    return f"{joined[:4]}-{joined[4:]}" if len(joined) == _CODE_LENGTH else joined


def hash_share_code(code: str) -> str:
    """Keyed hash. The plaintext code is returned to its owner ONCE and never stored.

    Same discipline as the OTP: somebody who reads this file cannot use what is in it.
    """
    msg = f"{_CODE_PURPOSE}|{normalise_share_code(code)}".encode()
    return hmac.new(auth_cfg.AUTH_SECRET.encode(), msg, hashlib.sha256).hexdigest()


class _JsonFile:
    """One JSON document on disk, read and written under a process-wide lock."""

    def __init__(self, path: Path, empty):
        self.path = path
        self._empty = empty
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.write_text(json.dumps(empty))

    def read(self):
        try:
            return json.loads(self.path.read_text())
        except Exception:                                # noqa: BLE001
            return json.loads(json.dumps(self._empty))

    def write(self, data) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, self.path)


class PassportStore:
    """Prototype longitudinal store. Good enough for a screening programme demo.

    The surface is small on purpose: swapping in Firestore later means implementing
    these methods and nothing else. Every read that can be scoped to a patient IS scoped
    to a patient — there is no "list every screening" method here, because nothing in
    this feature needs one.
    """

    def __init__(self, directory: Path | None = None, enabled: bool | None = None):
        d = Path(directory or cfg.PASSPORT_STORE_DIR)
        self.dir = d
        self.enabled = cfg.PASSPORT_ENABLED if enabled is None else enabled
        self._screenings = _JsonFile(d / "screenings.json", [])
        self._follow_ups = _JsonFile(d / "follow_ups.json", [])
        self._grants = _JsonFile(d / "access_grants.json", [])
        self._share_codes = _JsonFile(d / "share_codes.json", [])

    # ------------------------------------------------------------ screenings
    def save_screening(self, rec: dict) -> dict | None:
        """Append one screening to its owner's history. Idempotent per screening id."""
        if not self.enabled:
            return None
        sid = safe_id(rec.get("screening_id", ""))
        if not sid or not rec.get("account_id"):
            return None
        with _LOCK:
            rows = self._screenings.read()
            for existing in rows:
                if existing.get("screening_id") == sid:
                    return existing
            rows.append(rec)
            self._screenings.write(rows[-cfg.MAX_HISTORY * 20:])
        return rec

    def history(self, account_id: str, limit: int = cfg.MAX_HISTORY) -> list[dict]:
        """This patient's screenings, OLDEST FIRST.

        Ascending because that is the order a timeline is read in and the order a
        comparison walks. Callers that want "the latest" take the last element; nothing
        re-sorts a slice of this and gets a different answer.
        """
        rows = [r for r in self._screenings.read() if r.get("account_id") == account_id]
        rows.sort(key=lambda r: (str(r.get("created_at") or ""),
                                 str(r.get("screening_id") or "")))
        return rows[-max(1, limit):]

    def get_screening(self, screening_id: str) -> dict | None:
        sid = safe_id(screening_id)
        if not sid:
            return None
        for r in self._screenings.read():
            if r.get("screening_id") == sid:
                return r
        return None

    def previous_valid(self, account_id: str, screening_id: str) -> dict | None:
        """The immediately previous GRADED screening for the same patient, or None.

        "Valid" means the quality gate passed and a grade exists. An ungradeable visit is
        a real event on the timeline and is shown there, but it is not a result, so it
        can never be one half of a grade comparison — see comparison.py.
        """
        rows = self.history(account_id)
        try:
            idx = next(i for i, r in enumerate(rows)
                       if r.get("screening_id") == safe_id(screening_id))
        except StopIteration:
            return None
        for r in reversed(rows[:idx]):
            if r.get("gradeable") is True and r.get("icdr_grade") is not None:
                return r
        return None

    def latest_valid(self, account_id: str) -> dict | None:
        for r in reversed(self.history(account_id)):
            if r.get("gradeable") is True and r.get("icdr_grade") is not None:
                return r
        return None

    # ------------------------------------------------------------ follow-ups
    def save_follow_up(self, rec: dict) -> dict:
        """Record a follow-up plan and retire any earlier open one for this patient.

        Superseding rather than editing keeps the history honest: you can always answer
        "what was this patient told to do, and when did that change, and why?"
        """
        rec = {**rec, "follow_up_id": rec.get("follow_up_id") or ("fu_" + uuid.uuid4().hex[:16])}
        with _LOCK:
            rows = self._follow_ups.read()
            for r in rows:
                if (r.get("account_id") == rec.get("account_id")
                        and r.get("status") in ("scheduled", "due")
                        and r.get("follow_up_id") != rec["follow_up_id"]):
                    r["status"] = "superseded"
                    r["superseded_at"] = now_iso()
                    r["superseded_by"] = rec["follow_up_id"]
            rows.append(rec)
            self._follow_ups.write(rows[-cfg.MAX_HISTORY * 20:])
        return rec

    def follow_ups(self, account_id: str) -> list[dict]:
        rows = [r for r in self._follow_ups.read() if r.get("account_id") == account_id]
        rows.sort(key=lambda r: str(r.get("created_at") or ""))
        return rows

    def get_follow_up(self, follow_up_id: str) -> dict | None:
        fid = safe_id(follow_up_id)
        for r in self._follow_ups.read():
            if r.get("follow_up_id") == fid:
                return r
        return None

    def active_follow_up(self, account_id: str) -> dict | None:
        """The one plan currently in force, or None. There is at most one by
        construction — `save_follow_up` supersedes the rest."""
        for r in reversed(self.follow_ups(account_id)):
            if r.get("status") in ("scheduled", "due"):
                return r
        return None

    def update_follow_up(self, follow_up_id: str, **changes) -> dict | None:
        fid = safe_id(follow_up_id)
        with _LOCK:
            rows = self._follow_ups.read()
            for r in rows:
                if r.get("follow_up_id") == fid:
                    r.update(changes)
                    r["updated_at"] = now_iso()
                    self._follow_ups.write(rows)
                    return r
        return None

    def complete_follow_ups(self, account_id: str, *, by_screening_id: str) -> int:
        """Close the open plan because the patient came back and was screened.

        This is the RETURN step of the loop, recorded rather than assumed: a plan is
        "completed" only when a screening actually happened against it.
        """
        closed = 0
        with _LOCK:
            rows = self._follow_ups.read()
            for r in rows:
                if (r.get("account_id") == account_id
                        and r.get("status") in ("scheduled", "due")):
                    r["status"] = "completed"
                    r["completed_at"] = now_iso()
                    r["completed_by_screening_id"] = safe_id(by_screening_id)
                    closed += 1
            if closed:
                self._follow_ups.write(rows)
        return closed

    # -------------------------------------------------------- access grants
    #
    # THE DOCTOR-PATIENT RELATIONSHIP. A verified doctor role says "this person is a
    # clinician". A grant says "this clinician is looking after THIS patient". Both are
    # required for any patient-linked read, and the second is the one a patient controls.
    #
    # A grant carries a `status`, so access can be taken back. Rows written before the
    # field existed are treated as active — `_grant_active` reads a missing status as
    # "active" rather than dropping historic care relationships on upgrade.
    def grant_access(self, *, account_id: str, doctor_account_id: str, reason: str,
                     granted_by: str) -> dict:
        """Authorise ONE doctor to read ONE patient's longitudinal record.

        Created when the patient shares a code with a doctor, when a doctor records a
        clinician review on that patient's screening, or when an administrator assigns
        one. Nothing else creates one.

        Re-granting a REVOKED relationship reactivates that same row rather than adding
        a second one, so the history of who was given access stays readable.
        """
        now = now_iso()
        with _LOCK:
            rows = self._grants.read()
            for r in rows:
                if (r.get("account_id") == account_id
                        and r.get("doctor_account_id") == doctor_account_id):
                    if _grant_active(r):
                        return r
                    r["status"] = "active"
                    r["reason"] = reason
                    r["granted_by"] = granted_by
                    r["granted_at"] = now
                    r["revoked_at"] = None
                    r["revoked_by"] = None
                    self._grants.write(rows)
                    return r
            entry = {
                "account_id": account_id,
                "doctor_account_id": doctor_account_id,
                "status": "active",
                "reason": reason,
                "granted_by": granted_by,
                "granted_at": now,
                "revoked_at": None,
                "revoked_by": None,
            }
            rows.append(entry)
            self._grants.write(rows)
        return entry

    def revoke_access(self, *, account_id: str, doctor_account_id: str,
                      revoked_by: str) -> dict | None:
        """Withdraw one doctor's access. Returns the revoked grant, or None if there
        was no active one.

        The row is marked, not deleted: "who could see my record, and until when?" is a
        question a patient is entitled to an answer to. `has_access` consults `status`
        on every call, so the next request from that doctor is already refused — there
        is no cached authorisation anywhere to outlive this.
        """
        with _LOCK:
            rows = self._grants.read()
            for r in rows:
                if (r.get("account_id") == account_id
                        and r.get("doctor_account_id") == doctor_account_id
                        and _grant_active(r)):
                    r["status"] = "revoked"
                    r["revoked_at"] = now_iso()
                    r["revoked_by"] = revoked_by
                    self._grants.write(rows)
                    return r
        return None

    def has_access(self, *, account_id: str, doctor_account_id: str) -> bool:
        """The single question every doctor-facing read asks. Re-read from disk each
        time, so a revocation takes effect on the very next request."""
        return any(r.get("account_id") == account_id
                   and r.get("doctor_account_id") == doctor_account_id
                   and _grant_active(r)
                   for r in self._grants.read())

    def granted_patients(self, doctor_account_id: str) -> list[str]:
        """The patients this doctor may currently read. Revoked ones are not here."""
        seen: list[str] = []
        for r in self._grants.read():
            if r.get("doctor_account_id") == doctor_account_id and _grant_active(r):
                aid = r.get("account_id")
                if aid and aid not in seen:
                    seen.append(aid)
        return seen

    def grants_for_patient(self, account_id: str, *,
                           include_revoked: bool = False) -> list[dict]:
        """Who this patient has shared their record with. The patient's own view."""
        return [r for r in self._grants.read()
                if r.get("account_id") == account_id
                and (include_revoked or _grant_active(r))]

    # ---------------------------------------------------- patient share codes
    #
    # How a patient hands access to a doctor they have never met: the patient generates
    # a short code on their own result page and reads it across the desk. The doctor
    # redeems it, which creates the grant.
    #
    # The code is a CAPABILITY, so it is treated like one: hashed at rest with the same
    # discipline as an OTP, single use, short-lived, and bound to the patient who made
    # it. The plaintext is returned exactly once, to its owner, and is never stored,
    # logged or re-displayed.
    def create_share_code(self, *, account_id: str) -> tuple[dict, str] | None:
        """Mint one code for this patient. Returns (record, PLAINTEXT) — or None if the
        patient already has the maximum number outstanding."""
        code = generate_share_code()
        now = datetime.now(timezone.utc).timestamp()
        with _LOCK:
            rows = [r for r in self._share_codes.read() if not _code_dead(r, now)]
            mine = [r for r in rows if r.get("account_id") == account_id]
            if len(mine) >= cfg.SHARE_CODE_MAX_ACTIVE:
                self._share_codes.write(rows)
                return None
            entry = {
                "code_id": "shc_" + uuid.uuid4().hex[:16],
                "account_id": account_id,
                # The hash. There is no field anywhere in this record for the code.
                "code_hash": hash_share_code(code),
                "created_at": now_iso(),
                "expires_at": now + cfg.SHARE_CODE_TTL_SECONDS,
                "redeemed_at": None,
                "redeemed_by": None,
                "cancelled_at": None,
            }
            rows.append(entry)
            self._share_codes.write(rows)
        return entry, code

    def active_share_codes(self, account_id: str) -> list[dict]:
        now = datetime.now(timezone.utc).timestamp()
        return [r for r in self._share_codes.read()
                if r.get("account_id") == account_id and not _code_dead(r, now)]

    def cancel_share_code(self, *, account_id: str, code_id: str) -> bool:
        """The patient changed their mind before anyone redeemed it."""
        cid = safe_id(code_id)
        with _LOCK:
            rows = self._share_codes.read()
            for r in rows:
                if (r.get("code_id") == cid
                        and r.get("account_id") == account_id
                        and r.get("redeemed_at") is None
                        and r.get("cancelled_at") is None):
                    r["cancelled_at"] = now_iso()
                    self._share_codes.write(rows)
                    return True
        return False

    def redeem_share_code(self, *, code: str, doctor_account_id: str) -> dict | None:
        """Consume a code and return its record, or None.

        None covers every failure — unknown, expired, already used, cancelled — because
        a doctor typing a code has no business learning which of those it was, and the
        distinction would turn this into an oracle for guessing codes.

        The code is consumed inside the lock before the grant is created, so two
        simultaneous redemptions cannot both succeed.
        """
        wanted = hash_share_code(code)
        now = datetime.now(timezone.utc).timestamp()
        with _LOCK:
            rows = self._share_codes.read()
            for r in rows:
                if _code_dead(r, now):
                    continue
                # compare_digest: a share code is a secret, so it is compared like one.
                if not hmac.compare_digest(str(r.get("code_hash") or ""), wanted):
                    continue
                r["redeemed_at"] = now_iso()
                r["redeemed_by"] = doctor_account_id
                self._share_codes.write(rows)
                return r
        return None

    @property
    def backend(self) -> str:
        return f"local-json:{self.dir.name}"


def _grant_active(row: dict) -> bool:
    """A grant with no `status` predates revocation and is treated as active."""
    return row.get("status", "active") == "active"


def _code_dead(row: dict, now: float) -> bool:
    """Expired, already redeemed, or cancelled — in all three cases, unusable."""
    return bool(row.get("redeemed_at") or row.get("cancelled_at")
                or float(row.get("expires_at") or 0) <= now)


_STORE: PassportStore | None = None


def get_passport_store() -> PassportStore:
    global _STORE
    if _STORE is None:
        _STORE = PassportStore()
    return _STORE


def set_passport_store(store: PassportStore | None) -> None:
    """Test seam."""
    global _STORE
    _STORE = store
