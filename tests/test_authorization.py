"""Role-based access control on the report endpoints.

The requirement these encode: the role that decides access is the one in the server's
account store. Nothing a client sends — a body field, a header, a query parameter, or a
tampered token — can change it.
"""
from __future__ import annotations

import base64
import json

from tests.conftest import SCAN_WITH_PII, auth_header, signup, patient_with_shared_scan

from src.auth import service
from src.auth.security import mint_token

USER = "+919876522001"
DOC = "+919876522002"
DOC2 = "+919876522003"


def verified_doctor(client, auth_store, mobile=DOC):
    body = signup(client, mobile, "doctor")
    service.approve_doctor(body["account"]["account_id"], approved=True, store=auth_store)
    return body


# ------------------------------------------------------------ unauthenticated
def test_reports_require_a_session(client):
    assert client.get("/v1/reports").status_code == 401
    assert client.get("/v1/reports/sc_x").status_code == 401
    assert client.post("/v1/reports/sc_x/review", json={"status": "confirmed"}).status_code == 401


def test_a_garbage_token_is_rejected(client):
    assert client.get("/v1/reports", headers=auth_header("not-a-token")).status_code == 401
    assert client.get("/v1/reports", headers=auth_header("a.b")).status_code == 401


def test_a_tampered_token_is_rejected(client, auth_store):
    """Forge a token for a real account id with a bogus signature."""
    body = verified_doctor(client, auth_store)
    payload = {"sub": body["account"]["account_id"], "jti": "x", "iat": 0, "exp": 9e9}
    forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    assert client.get("/v1/reports",
                      headers=auth_header(f"{forged}.deadbeef")).status_code == 401


def test_an_expired_token_is_rejected(client, auth_store):
    body = verified_doctor(client, auth_store)
    expired = mint_token(body["account"]["account_id"], ttl=-10).token
    assert client.get("/v1/reports", headers=auth_header(expired)).status_code == 401


def test_a_token_for_an_unknown_account_is_rejected(client):
    assert client.get("/v1/reports",
                      headers=auth_header(mint_token("acc_nonexistent").token)).status_code == 401


# --------------------------------------------------------------------- user
def test_a_user_cannot_list_reports(client):
    body = signup(client, USER, "user")
    r = client.get("/v1/reports", headers=auth_header(body["token"]))
    assert r.status_code == 403
    assert r.json()["detail"]["error"]["code"] == "doctor_access_required"
    assert r.json()["detail"]["error"]["message"] == "Doctor access required."


def test_a_user_cannot_read_or_review_a_single_report(client):
    body = signup(client, USER, "user")
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    h = auth_header(body["token"])
    assert client.get(f"/v1/reports/{SCAN_WITH_PII['scan_id']}", headers=h).status_code == 403
    assert client.post(f"/v1/reports/{SCAN_WITH_PII['scan_id']}/review",
                       json={"status": "confirmed"}, headers=h).status_code == 403


def test_a_user_cannot_reach_the_admin_endpoints(client):
    body = signup(client, USER, "user")
    h = auth_header(body["token"])
    assert client.get("/v1/auth/admin/doctors", headers=h).status_code == 403
    assert client.post("/v1/auth/admin/doctors/acc_x/verify",
                       json={"approved": True}, headers=h).status_code == 403


def test_a_doctor_cannot_approve_themselves_through_the_admin_api(client, auth_store):
    body = signup(client, DOC, "doctor")
    h = auth_header(body["token"])
    aid = body["account"]["account_id"]
    r = client.post(f"/v1/auth/admin/doctors/{aid}/verify", json={"approved": True}, headers=h)
    assert r.status_code == 403
    assert auth_store.get(aid).doctor_verified is False


# --------------------------------------------------------- unverified doctor
def test_an_unverified_doctor_cannot_list_reports(client):
    body = signup(client, DOC, "doctor")
    r = client.get("/v1/reports", headers=auth_header(body["token"]))
    assert r.status_code == 403
    err = r.json()["detail"]["error"]
    assert err["code"] == "doctor_verification_pending"
    assert err["message"] == "Doctor verification pending."


def test_an_unverified_doctor_can_still_sign_in(client):
    body = signup(client, DOC, "doctor")
    me = client.get("/v1/auth/me", headers=auth_header(body["token"]))
    assert me.status_code == 200
    assert me.json()["doctor_verification_pending"] is True


# ----------------------------------------------------------- verified doctor
def test_a_verified_doctor_can_list_reports(client, auth_store):
    body = verified_doctor(client, auth_store)
    r = client.get("/v1/reports", headers=auth_header(body["token"]))
    assert r.status_code == 200 and r.json()["anonymised"] is True


def test_a_verified_doctor_can_open_and_review_a_report(client, auth_store):
    """Verified AND authorised. The doctor role alone is not enough — see
    tests/test_data_isolation.py for the half that is refused."""
    body = verified_doctor(client, auth_store)
    client.scan_store.save_scan(dict(SCAN_WITH_PII))
    h = auth_header(body["token"])
    sid = SCAN_WITH_PII["scan_id"]
    patient_with_shared_scan(client, sid, body["account"]["account_id"])
    assert client.get(f"/v1/reports/{sid}", headers=h).status_code == 200
    assert client.post(f"/v1/reports/{sid}/review",
                       json={"status": "confirmed"}, headers=h).status_code == 200


def test_verification_applies_on_the_next_request_not_the_next_login(client, auth_store):
    """The role is read from the store per request, so an approval takes effect
    immediately for an already-issued token."""
    body = signup(client, DOC2, "doctor")
    h = auth_header(body["token"])
    assert client.get("/v1/reports", headers=h).status_code == 403
    service.approve_doctor(body["account"]["account_id"], approved=True, store=auth_store)
    assert client.get("/v1/reports", headers=h).status_code == 200


# ------------------------------------------- the frontend cannot override it
def test_a_client_cannot_claim_a_role_through_headers_or_body(client):
    """Every way a frontend might try to assert 'I am a doctor'."""
    body = signup(client, USER, "user")
    token = body["token"]
    attempts = [
        {"Authorization": f"Bearer {token}", "X-Role": "doctor"},
        {"Authorization": f"Bearer {token}", "X-User-Role": "admin"},
        {"Authorization": f"Bearer {token}", "Role": "doctor"},
        {"Authorization": f"Bearer {token}", "X-Doctor-Verified": "true"},
    ]
    for headers in attempts:
        assert client.get("/v1/reports", headers=headers).status_code == 403
    # query parameters too
    assert client.get("/v1/reports?role=doctor&doctor_verified=true",
                      headers=auth_header(token)).status_code == 403


def test_the_token_does_not_carry_the_role_at_all(client):
    """Nothing to tamper with: the payload holds an account id, not a privilege."""
    body = signup(client, USER, "user")
    blob = body["token"].split(".")[0]
    payload = json.loads(base64.urlsafe_b64decode(blob + "=" * (-len(blob) % 4)))
    assert set(payload) == {"sub", "jti", "iat", "exp"}
    assert "role" not in payload and "doctor_verified" not in payload


def test_a_suspended_account_loses_access(client, auth_store):
    body = verified_doctor(client, auth_store)
    h = auth_header(body["token"])
    assert client.get("/v1/reports", headers=h).status_code == 200
    auth_store.update(body["account"]["account_id"], status="suspended")
    assert client.get("/v1/reports", headers=h).status_code == 401
