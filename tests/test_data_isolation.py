"""Patient/doctor data isolation, and the IDOR attempts that must fail.

AUTHENTICATION says who you are. AUTHORISATION says what you may open. This file is
entirely about the second, and about the specific ways a client might try to talk its way
past it: editing an id in a URL, putting somebody else's id in a body, asking for a role,
or holding on to access after it was taken away.

The rule every endpoint here enforces is the same one:

    a verified doctor ROLE          (the programme's half of the decision)
  + an active care RELATIONSHIP     (the patient's half)

Both, every time, re-read from the store on every request. Neither is ever taken from the
request, and there is no endpoint in the application that lists every patient.

`404` rather than `403` throughout, deliberately: a different status for "exists but not
yours" would turn these endpoints into an oracle for discovering that a scan id or an
account id exists at all.
"""
from __future__ import annotations

import copy

import pytest

from src.auth import service
from tests.conftest import (SCAN_WITH_PII, auth_header, own_scan, share_with_doctor,
                            signup)

PATIENT_A = "+919800000001"
PATIENT_B = "+919800000002"
DOCTOR_1 = "+919700000001"
DOCTOR_2 = "+919700000002"
ADMIN = "+919600000001"

SCAN_A = "sc_patient_a_0001"
SCAN_B = "sc_patient_b_0001"


def scan(scan_id: str, **over) -> dict:
    rec = copy.deepcopy(SCAN_WITH_PII)
    rec["scan_id"] = scan_id
    rec.update(over)
    return rec


@pytest.fixture
def world(client, auth_store):
    """Two patients with a screening each, two verified doctors, and no sharing at all.

    Every test starts from "nobody has been given access to anything", so any success
    below had to be granted explicitly.
    """
    a = signup(client, PATIENT_A, "user")
    b = signup(client, PATIENT_B, "user")

    d1 = signup(client, DOCTOR_1, "doctor")
    service.approve_doctor(d1["account"]["account_id"], approved=True, store=auth_store)
    d2 = signup(client, DOCTOR_2, "doctor")
    service.approve_doctor(d2["account"]["account_id"], approved=True, store=auth_store)

    client.scan_store.save_scan(scan(SCAN_A))
    client.scan_store.save_scan(scan(SCAN_B))
    own_scan(client, SCAN_A, a["account"]["account_id"])
    own_scan(client, SCAN_B, b["account"]["account_id"])

    return {
        "a": a, "b": b, "d1": d1, "d2": d2,
        "a_id": a["account"]["account_id"], "b_id": b["account"]["account_id"],
        "d1_id": d1["account"]["account_id"], "d2_id": d2["account"]["account_id"],
        "ha": auth_header(a["token"]), "hb": auth_header(b["token"]),
        "h1": auth_header(d1["token"]), "h2": auth_header(d2["token"]),
    }


# ===================================================== PATIENT DATA ISOLATION
def test_a_patient_sees_only_their_own_passport(client, world):
    ra = client.get("/v1/passport", headers=world["ha"]).json()
    rb = client.get("/v1/passport", headers=world["hb"]).json()
    ids_a = [s["screening_id"] for s in ra.get("timeline", ra.get("screenings", []))]
    ids_b = [s["screening_id"] for s in rb.get("timeline", rb.get("screenings", []))]
    assert SCAN_A in str(ids_a) and SCAN_B not in str(ids_a)
    assert SCAN_B in str(ids_b) and SCAN_A not in str(ids_b)


def test_a_patient_cannot_open_another_patients_comparison(client, world):
    r = client.get(f"/v1/passport/screenings/{SCAN_B}/comparison", headers=world["ha"])
    assert r.status_code == 404


def test_a_patient_cannot_download_another_patients_comparison_pdf(client, world):
    r = client.get(f"/v1/passport/screenings/{SCAN_B}/comparison.pdf",
                   headers=world["ha"])
    assert r.status_code == 404


def test_a_patient_cannot_reach_the_doctor_view_of_any_record(client, world):
    """Including their own: the doctor view is a different object with a different rule."""
    for target in (world["a_id"], world["b_id"]):
        r = client.get(f"/v1/passport/patients/{target}", headers=world["ha"])
        assert r.status_code == 403, target


def test_a_patient_cannot_read_the_doctor_report_collection(client, world):
    assert client.get("/v1/reports", headers=world["ha"]).status_code == 403
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["ha"]).status_code == 403
    assert client.post(f"/v1/reports/{SCAN_A}/review", json={"status": "confirmed"},
                       headers=world["ha"]).status_code == 403


def test_a_patient_cannot_send_another_patients_follow_up_reminder(client, world):
    r = client.post("/v1/passport/follow-up/fu_not_mine/reminder", json={},
                    headers=world["ha"])
    assert r.status_code == 404


# ======================================================= DOCTOR AUTHORISATION
def test_a_verified_doctor_with_no_relationship_sees_no_reports(client, world):
    """The heart of it. A doctor role is not a licence to read every patient."""
    body = client.get("/v1/reports", headers=world["h1"]).json()
    assert body["count"] == 0
    assert body["reports"] == []
    assert body["scope"] == "authorised_patients"


def test_a_verified_doctor_with_no_relationship_cannot_open_a_report(client, world):
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404


def test_a_verified_doctor_with_no_relationship_cannot_review_a_report(client, world):
    """Reviewing used to CREATE the relationship, which meant any doctor could
    self-grant access to any patient. It now requires the relationship first."""
    r = client.post(f"/v1/reports/{SCAN_A}/review", json={"status": "confirmed"},
                    headers=world["h1"])
    assert r.status_code == 404
    assert client.passport.has_access(account_id=world["a_id"],
                                      doctor_account_id=world["d1_id"]) is False


def test_sharing_gives_exactly_one_doctor_exactly_one_patient(client, world):
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])

    # The shared pair works.
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200
    body = client.get("/v1/reports", headers=world["h1"]).json()
    assert [r["scan_id"] for r in body["reports"]] == [SCAN_A]

    # The other patient is still invisible to this doctor...
    assert client.get(f"/v1/reports/{SCAN_B}", headers=world["h1"]).status_code == 404
    # ...and the other doctor still sees nothing at all.
    assert client.get("/v1/reports", headers=world["h2"]).json()["count"] == 0
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h2"]).status_code == 404


def test_the_patient_list_holds_only_this_doctors_patients(client, world):
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    ids = [p["patient_id"]
           for p in client.get("/v1/passport/patients", headers=world["h1"]).json()["patients"]]
    assert ids == [world["a_id"]]
    assert client.get("/v1/passport/patients",
                      headers=world["h2"]).json()["patients"] == []


def test_an_unverified_doctor_is_refused_even_with_a_relationship(client, auth_store,
                                                                  world):
    """Two independent conditions. A grant does not substitute for verification."""
    pending = signup(client, "+919700000009", "doctor")
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=pending["account"]["account_id"])
    h = auth_header(pending["token"])
    assert client.get("/v1/reports", headers=h).status_code == 403
    assert client.get(f"/v1/reports/{SCAN_A}", headers=h).status_code == 403
    assert client.get(f"/v1/passport/patients/{world['a_id']}",
                      headers=h).status_code == 403


# ============================================================== REVOCATION
def test_revoking_ends_access_on_the_very_next_request(client, world):
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200

    r = client.post(f"/v1/passport/sharing/{world['d1_id']}/revoke", headers=world["ha"])
    assert r.status_code == 200
    assert r.json()["status"] == "revoked"

    # Same doctor, same token, same request. The token did not need to expire.
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404
    assert client.get("/v1/reports", headers=world["h1"]).json()["count"] == 0
    assert client.get(f"/v1/passport/patients/{world['a_id']}",
                      headers=world["h1"]).status_code == 404
    assert client.post(f"/v1/reports/{SCAN_A}/review", json={"status": "confirmed"},
                       headers=world["h1"]).status_code == 404


def test_only_the_owner_can_revoke(client, world):
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    # Patient B tries to revoke a relationship that is not theirs.
    assert client.post(f"/v1/passport/sharing/{world['d1_id']}/revoke",
                       headers=world["hb"]).status_code == 404
    # A's sharing is untouched.
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200


def test_a_revoked_relationship_can_be_restored_by_sharing_again(client, world):
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    client.post(f"/v1/passport/sharing/{world['d1_id']}/revoke", headers=world["ha"])
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404

    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200


# ========================================================= PATIENT SHARING UX
def test_a_patient_can_mint_a_code_and_a_doctor_can_redeem_it(client, world):
    made = client.post("/v1/passport/sharing/codes", headers=world["ha"])
    assert made.status_code == 200
    code = made.json()["code"]

    # Before redemption the doctor has nothing.
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404

    r = client.post("/v1/passport/sharing/redeem", json={"code": code},
                    headers=world["h1"])
    assert r.status_code == 200
    assert r.json()["patient_id"] == world["a_id"]
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200


def test_a_share_code_works_exactly_once(client, world):
    code = client.post("/v1/passport/sharing/codes",
                       headers=world["ha"]).json()["code"]
    assert client.post("/v1/passport/sharing/redeem", json={"code": code},
                       headers=world["h1"]).status_code == 200
    # A second doctor cannot reuse it.
    second = client.post("/v1/passport/sharing/redeem", json={"code": code},
                         headers=world["h2"])
    assert second.status_code == 400
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h2"]).status_code == 404


def test_the_code_is_stored_hashed_and_never_returned_again(client, world):
    code = client.post("/v1/passport/sharing/codes",
                       headers=world["ha"]).json()["code"]
    raw = (client.passport.dir / "share_codes.json").read_text()
    assert code not in raw, "the plaintext share code reached the store"
    assert "code_hash" in raw
    # The patient's own view lists the code's id, never the code.
    listed = client.get("/v1/passport/sharing", headers=world["ha"]).json()
    assert code not in str(listed)
    assert listed["active_codes"][0]["code_id"]


def test_an_expired_code_is_refused(client, world):
    made = client.post("/v1/passport/sharing/codes", headers=world["ha"]).json()
    rows = client.passport._share_codes.read()
    for row in rows:
        row["expires_at"] = 0
    client.passport._share_codes.write(rows)

    r = client.post("/v1/passport/sharing/redeem", json={"code": made["code"]},
                    headers=world["h1"])
    assert r.status_code == 400
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404


def test_a_cancelled_code_is_refused(client, world):
    made = client.post("/v1/passport/sharing/codes", headers=world["ha"]).json()
    assert client.delete(f"/v1/passport/sharing/codes/{made['code_id']}",
                         headers=world["ha"]).status_code == 200
    assert client.post("/v1/passport/sharing/redeem", json={"code": made["code"]},
                       headers=world["h1"]).status_code == 400


def test_a_patient_cannot_cancel_another_patients_code(client, world):
    made = client.post("/v1/passport/sharing/codes", headers=world["ha"]).json()
    assert client.delete(f"/v1/passport/sharing/codes/{made['code_id']}",
                         headers=world["hb"]).status_code == 404
    # Still usable by its owner's intended doctor.
    assert client.post("/v1/passport/sharing/redeem", json={"code": made["code"]},
                       headers=world["h1"]).status_code == 200


def test_a_guessed_code_is_refused_and_says_nothing_useful(client, world):
    r = client.post("/v1/passport/sharing/redeem", json={"code": "AAAA-2222"},
                    headers=world["h1"])
    assert r.status_code == 400
    body = r.json()["detail"]["error"]
    # One answer for unknown / expired / used / cancelled — no oracle.
    assert body["code"] == "invalid_share_code"
    assert "expired" not in body["message"].lower()


def test_a_patient_cannot_redeem_a_code_to_grant_themselves_doctor_powers(client,
                                                                          world):
    code = client.post("/v1/passport/sharing/codes",
                       headers=world["hb"]).json()["code"]
    # Patient A is not a doctor, so redemption is refused on the role, not the code.
    assert client.post("/v1/passport/sharing/redeem", json={"code": code},
                       headers=world["ha"]).status_code == 403
    assert client.get("/v1/reports", headers=world["ha"]).status_code == 403


def test_the_patients_sharing_view_shows_who_holds_access(client, world):
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    body = client.get("/v1/passport/sharing", headers=world["ha"]).json()
    assert body["count"] == 1
    entry = body["shared_with"][0]
    assert entry["doctor_account_id"] == world["d1_id"]
    # A doctor's own claimed professional details, never a mobile number.
    assert "mobile" not in str(entry)
    assert DOCTOR_1 not in str(body)

    client.post(f"/v1/passport/sharing/{world['d1_id']}/revoke", headers=world["ha"])
    assert client.get("/v1/passport/sharing", headers=world["ha"]).json()["count"] == 0


# ================================================== FORGED IDS AND ROLE CLAIMS
def test_a_forged_patient_id_in_a_url_is_ignored(client, world):
    """There is no patient-facing endpoint that takes an account id, so the only place
    to forge one is the DOCTOR view — and it is checked against the grants."""
    for h in (world["h1"], world["h2"]):
        for target in (world["a_id"], world["b_id"], "acc_does_not_exist"):
            r = client.get(f"/v1/passport/patients/{target}", headers=h)
            assert r.status_code == 404, (target, r.status_code)


def test_a_forged_id_in_a_request_body_changes_nothing(client, world):
    """Bodies that carry an account id are ignored where one is not expected."""
    share_with_doctor(client, patient_account_id=world["a_id"],
                      doctor_account_id=world["d1_id"])
    r = client.post(f"/v1/reports/{SCAN_A}/review",
                    json={"status": "confirmed", "notes": "x",
                          "account_id": world["b_id"], "patient_id": world["b_id"],
                          "doctor_id": world["d2_id"]},
                    headers=world["h1"])
    assert r.status_code == 200
    # The review was recorded against the real reviewer, not the supplied doctor_id.
    assert r.json()["clinician_review"]["reviewed_by"] == world["d1_id"]
    # And doctor 2 gained nothing.
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h2"]).status_code == 404


def test_a_patient_cannot_promote_themselves_to_doctor(client, world, auth_store):
    """The role is stored, never claimed. Asking again changes nothing.

    This matters MORE now, not less: signing in is free, so the only thing standing
    between a visitor and the report queue is that the role comes from the account
    store rather than from the request. Every shape below is a client asking for a
    privilege, and every one of them is ignored.
    """
    for body in ({"role": "doctor"}, {"role": "admin"},
                 {"doctor_verified": True}, {"can_read_reports": True}):
        r = client.post("/v1/auth/sign-in",
                        json={"mobile": PATIENT_A, "intent": "login", **body})
        # `role: admin` is refused by the schema; the rest sign in and change nothing.
        assert r.status_code in (200, 422), body
        if r.status_code == 200:
            assert r.json()["account"]["role"] == "user", body
            assert r.json()["account"]["can_read_reports"] is False, body

    assert auth_store.get_by_mobile(PATIENT_A).role == "user"
    assert auth_store.get_by_mobile(PATIENT_A).doctor_verified is False
    assert client.get("/v1/reports", headers=world["ha"]).status_code == 403


def test_signing_up_again_as_a_doctor_does_not_upgrade_an_existing_account(
        client, world, auth_store):
    r = client.post("/v1/auth/sign-in",
                    json={"mobile": PATIENT_A, "intent": "signup", "role": "doctor",
                          "doctor_profile": {"doctor_name": "Not A Doctor",
                                             "registration_number": "FAKE-1",
                                             "hospital": "Nowhere"}})
    # Sign-in SUCCEEDS now — anyone may open a session — but it hands back the account
    # that already exists, with the role it already has. Replaying signup as a doctor is
    # not a promotion path.
    assert r.status_code == 200
    assert r.json()["account"]["role"] == "user"
    assert r.json()["account"]["doctor_verified"] is False
    assert auth_store.get_by_mobile(PATIENT_A).role == "user"
    # And it did not fork the person into a second record.
    assert len([a for a in auth_store.list_accounts() if a.mobile == PATIENT_A]) == 1


def test_a_doctor_cannot_grant_themselves_access_through_the_admin_endpoint(client,
                                                                            world):
    r = client.post("/v1/passport/access",
                    json={"account_id": world["a_id"],
                          "doctor_account_id": world["d1_id"]},
                    headers=world["h1"])
    assert r.status_code == 403
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404


def test_a_new_doctor_account_is_never_verified_at_creation(client, auth_store):
    body = signup(client, "+919700000077", "doctor")
    assert body["account"]["doctor_verified"] is False
    assert body["account"]["can_read_reports"] is False
    assert body["doctor_verification_pending"] is True
    stored = auth_store.get(body["account"]["account_id"])
    assert stored.role == "doctor" and stored.doctor_verified is False


# ======================================================== ADMINISTRATOR PATH
def test_an_administrator_can_assign_a_patient_to_a_doctor(client, auth_store, world,
                                                            monkeypatch):
    monkeypatch.setattr("src.auth.config.ADMIN_MOBILES", (ADMIN,))
    admin = signup(client, ADMIN, "user")
    assert admin["account"]["role"] == "admin"
    ha = auth_header(admin["token"])

    r = client.post("/v1/passport/access",
                    json={"account_id": world["a_id"],
                          "doctor_account_id": world["d1_id"]}, headers=ha)
    assert r.status_code == 200
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200


def test_a_patient_can_revoke_an_administrator_assignment(client, auth_store, world,
                                                           monkeypatch):
    """The patient's control is not weaker than the administrator's."""
    monkeypatch.setattr("src.auth.config.ADMIN_MOBILES", (ADMIN,))
    admin = signup(client, ADMIN, "user")
    client.post("/v1/passport/access",
                json={"account_id": world["a_id"],
                      "doctor_account_id": world["d1_id"]},
                headers=auth_header(admin["token"]))
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 200

    client.post(f"/v1/passport/sharing/{world['d1_id']}/revoke", headers=world["ha"])
    assert client.get(f"/v1/reports/{SCAN_A}", headers=world["h1"]).status_code == 404


# ============================================================= UNOWNED SCANS
def test_a_scan_nobody_owns_is_not_served_to_a_doctor(client, world):
    """There is no patient who could have authorised it, so nobody is authorised."""
    client.scan_store.save_scan(scan("sc_orphan_0001"))
    assert client.get("/v1/reports/sc_orphan_0001",
                      headers=world["h1"]).status_code == 404
    listed = client.get("/v1/reports", headers=world["h1"]).json()
    assert "sc_orphan_0001" not in str(listed)


# ============================================== THE SESSION IS THE ONLY IDENTITY
def test_every_isolation_endpoint_needs_a_session(client, world):
    # The signups in `world` left an HttpOnly `dr_session` cookie on this client, which
    # is a real authentication transport (see security._bearer) — so it has to be
    # cleared, or this would assert against a caller that IS signed in.
    client.cookies.clear()
    for method, path in [
        ("get", "/v1/passport"),
        ("get", "/v1/passport/sharing"),
        ("post", "/v1/passport/sharing/codes"),
        ("post", "/v1/passport/sharing/redeem"),
        ("post", f"/v1/passport/sharing/{world['d1_id']}/revoke"),
        ("get", "/v1/passport/patients"),
        ("get", f"/v1/passport/patients/{world['a_id']}"),
        ("get", "/v1/reports"),
        ("get", f"/v1/reports/{SCAN_A}"),
    ]:
        kwargs = {"json": {"code": "AAAA-2222"}} if method == "post" else {}
        r = getattr(client, method)(path, **kwargs)
        assert r.status_code == 401, f"{method.upper()} {path} -> {r.status_code}"
