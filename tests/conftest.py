"""Fixtures for the authentication and report-access tests.

Every test gets its own tmp_path-backed account store, evidence store and review ledger,
so nothing touches the developer's real data/interim files and no test can see another
test's accounts.

The app under test is assembled from the auth and reports routers ONLY. That is
deliberate: it keeps the suite fast (no TensorFlow import, no model load) and it proves
the point the architecture is making — the access-control layer stands up entirely
without the medical pipeline.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import evidence as evidence_mod
from src.api import reports as reports_mod
from src.auth import config as auth_cfg
from src.auth.storage import LocalAuthStore, set_auth_store
from src.passport.store import PassportStore, set_passport_store


class FakeScanStore:
    """Stands in for src.api.store.LocalStore. Same three methods the reports router
    uses, and nothing else."""

    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def list_scans(self, limit: int = 50):
        return list(reversed(self.rows))[:limit]

    def save_scan(self, rec):
        self.rows.append(rec)

    backend = "fake"


@pytest.fixture
def auth_store(tmp_path, monkeypatch):
    store = LocalAuthStore(tmp_path / "auth")
    set_auth_store(store)
    monkeypatch.setattr(auth_cfg, "ADMIN_MOBILES", (), raising=False)
    yield store
    set_auth_store(None)


@pytest.fixture
def evidence(tmp_path):
    ev = evidence_mod.EvidenceStore(tmp_path / "scan_evidence", enabled=True)
    ledger = evidence_mod.ClinicianReviewLedger(tmp_path / "clinician_reviews.json")
    evidence_mod.set_stores(ev, ledger)
    yield ev, ledger
    evidence_mod.set_stores(None, None)


@pytest.fixture
def scan_store():
    return FakeScanStore()


@pytest.fixture
def passport(tmp_path):
    """A tmp-backed Eye Health Passport store, for the longitudinal tests.

    Autouse-adjacent but not autouse: tests that never touch the passport should not pay
    for a store, and the `client` fixture below requests it explicitly so that recording
    a clinician review can grant longitudinal access without writing to the developer's
    real data/interim files.
    """
    store = PassportStore(tmp_path / "passport", enabled=True)
    set_passport_store(store)
    yield store
    set_passport_store(None)


@pytest.fixture
def client(auth_store, evidence, scan_store, passport):
    """Auth + reports + passport, with no medical pipeline.

    The passport router is mounted because report authorisation now DEPENDS on it: a
    doctor may open a scan only if its owner — recorded in the passport layer — has an
    active care relationship with them. Testing the reports API without the layer that
    decides who owns what would test a different application.
    """
    from src.auth.routes import router as auth_router
    from src.passport.routes import router as passport_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(reports_mod.router)
    app.include_router(passport_router)
    app.dependency_overrides[reports_mod.get_scan_store] = lambda: scan_store
    with TestClient(app) as c:
        c.scan_store = scan_store          # convenience handle for the tests
        c.passport = passport
        yield c


# ------------------------------------------------------------------ helpers
def signup(client, mobile: str, role: str = "user", profile: dict | None = None) -> dict:
    """Sign in through the HTTP API and return the session response.

    One call now: there is no code to request and none to verify.
    """
    body = {"mobile": mobile, "intent": "signup", "role": role}
    if role == "doctor":
        body["doctor_profile"] = profile or {
            "doctor_name": "Dr Test", "registration_number": "TN-12345",
            "hospital": "District Hospital",
        }
    r = client.post("/v1/auth/sign-in", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------- ownership and care relationships
# A scan on its own belongs to nobody. `/v1/analyze` records the owner in the PASSPORT
# layer (never on the medical scan record), and the doctor-facing report endpoints now
# resolve ownership through it. A test that wants a doctor to read a scan therefore has
# to say whose scan it is and who was given access — the same two facts the product
# requires, rather than a back door that skips them.
PATIENT = "+919876500001"


def own_scan(client, scan_id: str, account_id: str, **over) -> dict:
    """Record that `account_id` owns `scan_id`, exactly as a screening would."""
    rec = {
        "screening_id": scan_id,
        "account_id": account_id,
        "created_at": "2026-09-15T10:00:00Z",
        "icdr_grade": 2,
        "severity_label": "Moderate NPDR",
        "referable": True,
        "confidence": 0.91,
        "gradeable": True,
        "quality_status": "pass",
        "report_available": True,
        "model_id": "run-test",
        **over,
    }
    client.passport.save_screening(rec)
    return rec


def share_with_doctor(client, *, patient_account_id: str, doctor_account_id: str) -> dict:
    """The care relationship, created the way a patient sharing a code creates it."""
    return client.passport.grant_access(
        account_id=patient_account_id, doctor_account_id=doctor_account_id,
        reason="patient_shared_code", granted_by=patient_account_id)


def patient_with_shared_scan(client, scan_id: str, doctor_account_id: str,
                             mobile: str = PATIENT) -> str:
    """Sign a patient up, give them `scan_id`, and share it with `doctor_account_id`.

    Returns the patient's account id.
    """
    patient = signup(client, mobile, "user")
    account_id = patient["account"]["account_id"]
    own_scan(client, scan_id, account_id)
    share_with_doctor(client, patient_account_id=account_id,
                      doctor_account_id=doctor_account_id)
    return account_id


SCAN_WITH_PII = {
    # A record that deliberately contains exactly the information the doctor-facing API
    # must never return. The privacy tests assert against this.
    "scan_id": "sc_privacytest01",
    "created_at": "2026-09-15T10:00:00Z",
    "patient_ref": "Lakshmi Narayanan +919812345678",
    "model_id": "run-test",
    "gradeable": True,
    "quality_score": 0.81,
    "recapture_instruction": None,
    "icdr_grade": 2,
    "referable": True,
    "confidence": 0.91,
    "rule_grade": 2,
    "rule_flag": None,
    "lesions": {"microaneurysms": {"count": 14, "by_quadrant": {}}},
    "timing_ms": {"total": 1200},
    "reviewed": False,
}
