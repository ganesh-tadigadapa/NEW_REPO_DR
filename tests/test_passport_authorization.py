"""Who may read a longitudinal record, and who may not.

The passport is the most identifying thing this system holds. One screening result is a
grade on an anonymous scan; a SEQUENCE of screening results linked to one account is a
person's medical history over years. So it has a stricter rule than the report
collection, and this file is that rule written down:

  * a patient reads their OWN record and nothing else, by ownership rather than by role;
  * a verified doctor additionally needs a GRANT for that specific patient, created by
    recording a clinician review on one of their screenings or by an administrator;
  * an unverified doctor and an ordinary user reach none of it;
  * and a record that is not yours answers 404, never 403 — a different status would
    confirm that the account id or the screening id exists.

The anonymity rule from `tests/test_reports_privacy.py` is re-asserted here for the
doctor-facing shapes, because a new module is exactly where a name or a mobile number
gets copied in by accident.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth import config as auth_cfg
from src.passport import service as passport_service
from src.passport.routes import router as passport_router
from tests.conftest import auth_header, signup
from tests.test_passport_longitudinal import analyze_result

PATIENT = "+919812370001"
OTHER_PATIENT = "+919812370002"
DOCTOR = "+919812370003"
OTHER_DOCTOR = "+919812370004"
ADMIN = "+919812370005"

# Field NAMES that must never appear in a longitudinal view, whatever the record holds.
# Checked as keys rather than as substrings of the response text, exactly as
# `tests/test_reports_privacy.py` does — the view's own `note` field says the words
# "mobile number" in order to promise it is absent, and a substring check flags that.
FORBIDDEN_FIELD_NAMES = ["patient_ref", "patient_name", "patient_mobile", "mobile",
                         "name", "contact", "address"]
# VALUES that must never appear anywhere in the response, including inside prose.
FORBIDDEN_VALUES = ["Lakshmi", "+919812345678", "9812345678"]


def _keys(node, out=None):
    """Every key name anywhere in a nested response."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            _keys(v, out)
    elif isinstance(node, list):
        for item in node:
            _keys(item, out)
    return out


@pytest.fixture
def api(auth_store, evidence, passport):
    from src.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(passport_router)
    with TestClient(app) as c:
        c.passport = passport
        yield c


def account_of(api, token):
    return api.get("/v1/auth/me", headers=auth_header(token)).json()["account"]


def make_patient(api, passport, mobile, prefix="sc"):
    """A signed-in patient with two screenings, grade 1 then grade 2."""
    session = signup(api, mobile)
    account_id = session["account"]["account_id"]
    for i, (grade, when) in enumerate([(1, "2026-09-16T09:00:00Z"),
                                       (2, "2027-03-16T09:00:00Z")], start=1):
        passport_service.record_screening(
            analyze_result(f"{prefix}_{i}", grade=grade, created_at=when), account_id)
    return {"token": session["token"], "account_id": account_id,
            "latest": f"{prefix}_2"}


def verified_doctor(api, auth_store, mobile):
    session = signup(api, mobile, role="doctor")
    account_id = session["account"]["account_id"]
    auth_store.set_doctor_verified(account_id, True, by="test")
    return {"token": session["token"], "account_id": account_id}


# ======================================= 16. a patient reaches only their own
def test_a_patient_reads_only_their_own_passport(api, passport):
    mine = make_patient(api, passport, PATIENT, prefix="sc_mine")
    theirs = make_patient(api, passport, OTHER_PATIENT, prefix="sc_theirs")

    body = api.get("/v1/passport", headers=auth_header(mine["token"])).json()
    ids = [p["screening_id"] for p in body["timeline"]]
    assert ids == ["sc_mine_1", "sc_mine_2"]
    assert not any(i.startswith("sc_theirs") for i in ids)
    assert theirs["account_id"] not in json.dumps(body)


def test_a_patient_cannot_read_another_patients_comparison(api, passport):
    mine = make_patient(api, passport, PATIENT, prefix="sc_mine")
    make_patient(api, passport, OTHER_PATIENT, prefix="sc_theirs")

    r = api.get("/v1/passport/screenings/sc_theirs_2/comparison",
                headers=auth_header(mine["token"]))
    # 404, not 403: a different status would confirm that screening exists.
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "not_found"


def test_a_patient_cannot_download_another_patients_comparison_pdf(api, passport):
    mine = make_patient(api, passport, PATIENT, prefix="sc_mine")
    make_patient(api, passport, OTHER_PATIENT, prefix="sc_theirs")

    r = api.get("/v1/passport/screenings/sc_theirs_2/comparison.pdf",
                headers=auth_header(mine["token"]))
    assert r.status_code == 404


def test_a_patient_cannot_reach_the_doctor_view_of_their_own_record(api, passport):
    """The doctor endpoints are role-gated even for the record's own subject: a patient
    who could call them could call them with somebody else's id."""
    mine = make_patient(api, passport, PATIENT, prefix="sc_mine")
    r = api.get(f"/v1/passport/patients/{mine['account_id']}",
                headers=auth_header(mine["token"]))
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "doctor_access_required"


def test_every_passport_endpoint_needs_a_session(api):
    for path in ["/v1/passport", "/v1/passport/status", "/v1/passport/follow-up",
                 "/v1/passport/screenings/sc_1/comparison",
                 "/v1/passport/screenings/sc_1/comparison.pdf",
                 "/v1/passport/patients/acc_x", "/v1/passport/by-scan/sc_1",
                 "/v1/passport/patients"]:
        assert api.get(path).status_code == 401, path
    assert api.post("/v1/passport/screenings/sc_1/comparison/whatsapp",
                    json={"language": "en"}).status_code == 401
    assert api.post("/v1/passport/access",
                    json={"account_id": "a", "doctor_account_id": "b"}).status_code == 401


# ============================== 17. a doctor needs a grant, not just a role
def test_an_ordinary_user_cannot_read_any_patient_record(api, auth_store, passport):
    patient = make_patient(api, passport, PATIENT)
    intruder = signup(api, OTHER_PATIENT)
    r = api.get(f"/v1/passport/patients/{patient['account_id']}",
                headers=auth_header(intruder["token"]))
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "doctor_access_required"


def test_an_unverified_doctor_cannot_read_any_patient_record(api, auth_store, passport):
    patient = make_patient(api, passport, PATIENT)
    pending = signup(api, DOCTOR, role="doctor")          # created unverified
    r = api.get(f"/v1/passport/patients/{patient['account_id']}",
                headers=auth_header(pending["token"]))
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "doctor_verification_pending"


def test_a_verified_doctor_without_a_grant_is_refused(api, auth_store, passport):
    """The rule that makes this different from the report collection.

    Being a verified doctor is enough to read anonymised REPORTS. It is not enough to
    read one person's history over time — that needs a care relationship.
    """
    patient = make_patient(api, passport, PATIENT)
    doctor = verified_doctor(api, auth_store, DOCTOR)

    r = api.get(f"/v1/passport/patients/{patient['account_id']}",
                headers=auth_header(doctor["token"]))
    assert r.status_code == 404, "an ungranted doctor must not learn the account exists"
    r2 = api.get(f"/v1/passport/by-scan/{patient['latest']}",
                 headers=auth_header(doctor["token"]))
    assert r2.status_code == 404


def test_a_granted_doctor_sees_the_longitudinal_history(api, auth_store, passport):
    patient = make_patient(api, passport, PATIENT)
    doctor = verified_doctor(api, auth_store, DOCTOR)
    passport.grant_access(account_id=patient["account_id"],
                          doctor_account_id=doctor["account_id"],
                          reason="clinician_review", granted_by=doctor["account_id"])

    body = api.get(f"/v1/passport/patients/{patient['account_id']}",
                   headers=auth_header(doctor["token"])).json()
    assert body["history_count"] == 2
    assert [p["icdr_grade"] for p in body["timeline"]] == [1, 2]
    assert body["latest_comparison"]["change_label"] == "One ICDR category higher"
    assert body["anonymised"] is True


def test_a_grant_for_one_patient_is_not_a_grant_for_another(api, auth_store, passport):
    mine = make_patient(api, passport, PATIENT, prefix="sc_mine")
    theirs = make_patient(api, passport, OTHER_PATIENT, prefix="sc_theirs")
    doctor = verified_doctor(api, auth_store, DOCTOR)
    passport.grant_access(account_id=mine["account_id"],
                          doctor_account_id=doctor["account_id"],
                          reason="clinician_review", granted_by=doctor["account_id"])

    assert api.get(f"/v1/passport/patients/{mine['account_id']}",
                   headers=auth_header(doctor["token"])).status_code == 200
    assert api.get(f"/v1/passport/patients/{theirs['account_id']}",
                   headers=auth_header(doctor["token"])).status_code == 404
    assert api.get(f"/v1/passport/by-scan/{theirs['latest']}",
                   headers=auth_header(doctor["token"])).status_code == 404


def test_one_doctors_grant_is_not_another_doctors_grant(api, auth_store, passport):
    patient = make_patient(api, passport, PATIENT)
    granted = verified_doctor(api, auth_store, DOCTOR)
    stranger = verified_doctor(api, auth_store, OTHER_DOCTOR)
    passport.grant_access(account_id=patient["account_id"],
                          doctor_account_id=granted["account_id"],
                          reason="clinician_review", granted_by=granted["account_id"])

    assert api.get(f"/v1/passport/patients/{patient['account_id']}",
                   headers=auth_header(granted["token"])).status_code == 200
    assert api.get(f"/v1/passport/patients/{patient['account_id']}",
                   headers=auth_header(stranger["token"])).status_code == 404


def test_a_doctors_patient_list_holds_only_their_granted_patients(api, auth_store,
                                                                  passport):
    mine = make_patient(api, passport, PATIENT, prefix="sc_mine")
    make_patient(api, passport, OTHER_PATIENT, prefix="sc_theirs")
    doctor = verified_doctor(api, auth_store, DOCTOR)
    passport.grant_access(account_id=mine["account_id"],
                          doctor_account_id=doctor["account_id"],
                          reason="clinician_review", granted_by=doctor["account_id"])

    body = api.get("/v1/passport/patients", headers=auth_header(doctor["token"])).json()
    assert body["count"] == 1
    assert body["patients"][0]["patient_id"] == mine["account_id"]
    assert body["patients"][0]["history_count"] == 2


def test_recording_a_clinician_review_grants_access_to_that_patient(api, auth_store,
                                                                    passport):
    """The one automatic grant, exercised through `service.grant_from_review`.

    The HTTP path that calls it is `/v1/reports/{scan_id}/review`, which lives in the
    reports router; `tests/test_doctor_review.py` covers that endpoint. What is asserted
    here is the consequence: after a review, the doctor can open the timeline.
    """
    patient = make_patient(api, passport, PATIENT)
    doctor = verified_doctor(api, auth_store, DOCTOR)
    assert api.get(f"/v1/passport/patients/{patient['account_id']}",
                   headers=auth_header(doctor["token"])).status_code == 404

    passport_service.grant_from_review(patient["latest"], doctor["account_id"])

    assert api.get(f"/v1/passport/patients/{patient['account_id']}",
                   headers=auth_header(doctor["token"])).status_code == 200


# ------------------------------------------------------ the doctor's own view
def test_the_doctor_view_carries_no_patient_identity(api, auth_store, passport):
    """Anonymised by construction, re-asserted against a record built from a result that
    deliberately contains a name and a mobile number."""
    patient = make_patient(api, passport, PATIENT)
    doctor = verified_doctor(api, auth_store, DOCTOR)
    passport.grant_access(account_id=patient["account_id"],
                          doctor_account_id=doctor["account_id"],
                          reason="clinician_review", granted_by=doctor["account_id"])

    response = api.get(f"/v1/passport/patients/{patient['account_id']}",
                       headers=auth_header(doctor["token"]))
    body, raw = response.json(), response.text

    present = _keys(body)
    for field in FORBIDDEN_FIELD_NAMES:
        assert field not in present, f"{field} leaked into the doctor view"
    for value in FORBIDDEN_VALUES + [PATIENT]:
        assert value not in raw, f"the doctor view leaked {value!r}"


def test_a_granted_doctor_can_set_a_follow_up_and_an_ungranted_one_cannot(
        api, auth_store, passport):
    patient = make_patient(api, passport, PATIENT)
    granted = verified_doctor(api, auth_store, DOCTOR)
    stranger = verified_doctor(api, auth_store, OTHER_DOCTOR)
    passport.grant_access(account_id=patient["account_id"],
                          doctor_account_id=granted["account_id"],
                          reason="clinician_review", granted_by=granted["account_id"])
    body = {"screening_id": patient["latest"], "follow_up_months": 2,
            "reason": "Reviewing sooner.", "priority": "soon"}

    refused = api.post(f"/v1/passport/patients/{patient['account_id']}/follow-up",
                       json=body, headers=auth_header(stranger["token"]))
    assert refused.status_code == 404

    ok = api.post(f"/v1/passport/patients/{patient['account_id']}/follow-up",
                  json=body, headers=auth_header(granted["token"]))
    assert ok.status_code == 200, ok.text
    payload = ok.json()
    assert payload["follow_up"]["basis"] == "clinician_override"
    assert payload["follow_up"]["recommended_window"]["max_months"] == 2
    # And nothing clinical moved.
    assert payload["ai_grade_unchanged"] == 2
    assert payload["ai_referable_unchanged"] is True


# ---------------------------------------------------------------- admin grants
def test_only_an_administrator_can_assign_a_patient_to_a_doctor(api, auth_store,
                                                                monkeypatch, passport):
    patient = make_patient(api, passport, PATIENT)
    doctor = verified_doctor(api, auth_store, DOCTOR)
    body = {"account_id": patient["account_id"],
            "doctor_account_id": doctor["account_id"]}

    assert api.post("/v1/passport/access", json=body,
                    headers=auth_header(doctor["token"])).status_code == 403
    assert api.post("/v1/passport/access", json=body,
                    headers=auth_header(patient["token"])).status_code == 403

    monkeypatch.setattr(auth_cfg, "ADMIN_MOBILES", (ADMIN,), raising=False)
    admin = signup(api, ADMIN)
    assert admin["account"]["role"] == "admin"

    r = api.post("/v1/passport/access", json=body, headers=auth_header(admin["token"]))
    assert r.status_code == 200, r.text
    assert api.get(f"/v1/passport/patients/{patient['account_id']}",
                   headers=auth_header(doctor["token"])).status_code == 200


def test_access_cannot_be_granted_to_an_account_that_is_not_a_verified_doctor(
        api, auth_store, monkeypatch, passport):
    patient = make_patient(api, passport, PATIENT)
    ordinary = signup(api, OTHER_PATIENT)
    monkeypatch.setattr(auth_cfg, "ADMIN_MOBILES", (ADMIN,), raising=False)
    admin = signup(api, ADMIN)

    r = api.post("/v1/passport/access",
                 json={"account_id": patient["account_id"],
                       "doctor_account_id": ordinary["account"]["account_id"]},
                 headers=auth_header(admin["token"]))
    assert r.status_code == 400
    assert r.json()["detail"]["error"]["code"] == "not_a_verified_doctor"


def test_an_administrator_can_read_a_record_without_a_grant(api, auth_store, monkeypatch,
                                                             passport):
    """An administrator assigns grants, so one who could not see a record could not
    assign it either."""
    patient = make_patient(api, passport, PATIENT)
    monkeypatch.setattr(auth_cfg, "ADMIN_MOBILES", (ADMIN,), raising=False)
    admin = signup(api, ADMIN)
    r = api.get(f"/v1/passport/patients/{patient['account_id']}",
                headers=auth_header(admin["token"]))
    assert r.status_code == 200
