"""Account creation and the doctor verification state machine."""
from __future__ import annotations

from tests.conftest import auth_header, signup

from src.auth import config as cfg
from src.auth import service
from src.auth.storage import LocalAuthStore

USER = "+919876511001"
DOC = "+919876511002"


def test_user_signup_creates_an_active_user_account(client):
    body = signup(client, USER, "user")
    acc = body["account"]
    assert body["created"] is True
    assert acc["role"] == "user"
    assert acc["doctor_verified"] is False
    assert acc["status"] == "active"
    assert acc["created_at"]
    assert body["next"] == "/screen"


def test_no_password_is_ever_stored(client, auth_store):
    signup(client, USER, "user")
    raw = (auth_store.dir / "accounts.json").read_text().lower()
    for forbidden in ("password", "passwd", "pwd", "hash_pw"):
        assert forbidden not in raw


def test_doctor_signup_is_created_pending_verification(client):
    body = signup(client, DOC, "doctor")
    acc = body["account"]
    assert acc["role"] == "doctor"
    assert acc["doctor_verified"] is False          # the whole point
    assert body["doctor_verification_pending"] is True
    assert body["next"] == "/screen"                # not /reports
    assert acc["doctor_profile"]["registration_number"] == "TN-12345"


def test_choosing_doctor_cannot_grant_the_privilege(client, auth_store):
    """The security requirement, stated as a test: selecting 'Doctor' at signup and
    completing OTP gives you a pending account and nothing more."""
    body = signup(client, DOC, "doctor")
    stored = auth_store.get_by_mobile(DOC)
    assert stored.doctor_verified is False
    assert stored.can_read_reports is False
    r = client.get("/v1/reports", headers=auth_header(body["token"]))
    assert r.status_code == 403


def test_doctor_verified_cannot_be_set_through_the_signup_payload(client, auth_store):
    """Extra fields in the request body are ignored by the model, so this is belt and
    braces — but it is the exact attack the requirement names."""
    r = client.post("/v1/auth/sign-in", json={
        "mobile": DOC, "intent": "signup", "role": "doctor",
        "doctor_verified": True, "can_read_reports": True,
        "doctor_profile": {"doctor_name": "Dr X", "registration_number": "X-11",
                           "hospital": "Rural PHC"},
    })
    v = r
    assert v.json()["account"]["doctor_verified"] is False
    assert auth_store.get_by_mobile(DOC).doctor_verified is False


def test_admin_approval_makes_a_doctor_verified(client, auth_store):
    body = signup(client, DOC, "doctor")
    account_id = body["account"]["account_id"]
    assert client.get("/v1/reports", headers=auth_header(body["token"])).status_code == 403

    service.approve_doctor(account_id, approved=True, by="test", store=auth_store)

    assert auth_store.get(account_id).doctor_verified is True
    # The same token now works: authorisation is re-read from the store per request.
    assert client.get("/v1/reports", headers=auth_header(body["token"])).status_code == 200


def test_approval_can_be_revoked(client, auth_store):
    body = signup(client, DOC, "doctor")
    aid = body["account"]["account_id"]
    service.approve_doctor(aid, approved=True, store=auth_store)
    service.approve_doctor(aid, approved=False, reason="registration not found",
                           store=auth_store)
    assert auth_store.get(aid).doctor_verified is False
    assert client.get("/v1/reports", headers=auth_header(body["token"])).status_code == 403


def test_a_user_account_cannot_be_approved_as_a_doctor(client, auth_store):
    body = signup(client, USER, "user")
    assert service.approve_doctor(body["account"]["account_id"], store=auth_store) is None


def test_signing_in_with_an_unknown_number_creates_the_account(client):
    """Was `test_login_requires_an_existing_account`, which asserted a 404.

    Sign-in no longer distinguishes login from signup at the gate: there is no
    verification step to fail, so an unknown number simply gets an account. `intent`
    survives only so each screen can word itself correctly.
    """
    r = client.post("/v1/auth/sign-in", json={"mobile": USER, "intent": "login"})
    assert r.status_code == 200
    body = r.json()
    assert body["created"] is True
    assert body["account"]["mobile"] == USER
    assert body["account"]["role"] == "user"      # never anything more, by default
    assert body["token"]


def test_signing_up_on_an_existing_number_returns_that_account(client):
    """Was `..._is_refused`, which asserted a 409.

    One verified mobile used to be one account because signup refused a duplicate. One
    mobile is STILL one account, but for a different reason: `store.create` returns the
    existing record rather than forking the person into two. The guarantee that matters
    downstream — a number maps to exactly one account_id — is unchanged.
    """
    first = signup(client, USER, "user")
    r = client.post("/v1/auth/sign-in", json={"mobile": USER, "intent": "signup"})
    assert r.status_code == 200
    assert r.json()["created"] is False
    assert r.json()["account"]["account_id"] == first["account"]["account_id"]


def test_login_returns_the_same_account(client, auth_store):
    first = signup(client, USER, "user")
    second = client.post("/v1/auth/sign-in",
                         json={"mobile": USER, "intent": "login"}).json()
    assert second["created"] is False
    assert second["account"]["account_id"] == first["account"]["account_id"]


def test_the_same_number_in_different_formats_is_one_account(client):
    first = signup(client, "+919876511009", "user")
    # Spaced, and bare 10-digit: both normalise to the same E.164 number.
    for typed in ("98765 11009", "9876511009", "+91 98765 11009"):
        r = client.post("/v1/auth/sign-in", json={"mobile": typed, "intent": "login"})
        assert r.status_code == 200, typed
        assert r.json()["account"]["account_id"] == first["account"]["account_id"], typed


def test_admin_mobiles_are_provisioned_as_admin(tmp_path, monkeypatch):
    monkeypatch.setattr(cfg, "ADMIN_MOBILES", ("+919000000001",))
    store = LocalAuthStore(tmp_path / "auth")
    # even asking for the doctor role, the allow-list wins
    acc = store.create("+919000000001", "doctor")
    assert acc.role == "admin" and acc.is_admin
    other = store.create("+919000000002", "doctor")
    assert other.role == "doctor"


def test_me_returns_the_stored_role_and_permissions(client):
    body = signup(client, USER, "user")
    me = client.get("/v1/auth/me", headers=auth_header(body["token"])).json()
    assert me["authenticated"] is True
    assert me["account"]["role"] == "user"
    assert me["permissions"]["can_read_reports"] is False
    assert me["permissions"]["can_screen"] is True


def test_me_requires_a_session(client):
    assert client.get("/v1/auth/me").status_code == 401


def test_logout_invalidates_the_token(client):
    body = signup(client, USER, "user")
    h = auth_header(body["token"])
    assert client.get("/v1/auth/me", headers=h).status_code == 200
    assert client.post("/v1/auth/logout", headers=h).status_code == 200
    assert client.get("/v1/auth/me", headers=h).status_code == 401


def test_session_endpoint_is_safe_when_signed_out(client):
    r = client.get("/v1/auth/session")
    assert r.status_code == 200 and r.json()["authenticated"] is False

