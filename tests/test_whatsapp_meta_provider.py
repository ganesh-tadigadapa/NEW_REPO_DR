"""The Meta WhatsApp Cloud API provider, and the provider-selection layer above it.

Not one test here reaches Meta. The single HTTP call is replaced by a callable that
records the exact JSON payload, so the wire format — which is where a Cloud API
integration actually goes wrong — is asserted rather than hoped for.

What this file is really protecting:

  * **The recipient comes from the session, never the request.** The endpoint has
    nowhere to put a phone number, and the number it uses is verified by construction
    (an account only exists after an OTP to that number was confirmed). Both are pinned
    below, because "send a medical report to an attacker-supplied number" is the worst
    bug this feature could have.
  * **"Sent" means Meta returned a wamid.** Every refusal test asserts `success` is
    False and that no message id comes back with it.
  * **Swapping providers is configuration.** The same endpoint, the same route code and
    the same response shape work for either vendor; only `WHATSAPP_PROVIDER` differs.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.delivery import config as dcfg
from src.delivery import media as media_mod
from src.delivery.providers.meta import MetaWhatsAppProvider
from src.delivery.routes import router as delivery_router
from src.delivery.whatsapp import (
    WhatsAppReportService, build_provider, set_whatsapp_service,
)
from tests.conftest import auth_header, signup

PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

PATIENT = "+919812340001"
OTHER = "+919812340002"

# Obviously fake, and shaped like the real thing: the phone number ID is numeric (it is
# an id, not a phone number) and the token is a bearer string.
FAKE_TOKEN = "EAAtest-not-a-real-token"
FAKE_PHONE_ID = "123456789012345"


def analyze_result(scan_id="sc_meta0001", grade=2, referable=True):
    return {
        "scan_id": scan_id,
        "created_at": "2026-09-16T09:00:00Z",
        "patient_ref": "Lakshmi Narayanan +919812345678",
        "quality": {"gradeable": True, "overall_score": 0.88},
        "grading": {"icdr_grade": grade, "icdr_label": "Moderate NPDR",
                    "referable": referable, "confidence": 0.77},
        "report": {"pdf_b64": base64.b64encode(PDF_BYTES).decode(),
                   "filename": f"dr-report-{scan_id}.pdf"},
    }


# ------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _meta_config(monkeypatch):
    """A configured-and-reachable Meta setup. Nothing here can reach Meta: the provider
    is always injected with a double."""
    monkeypatch.setattr(dcfg, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(dcfg, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(dcfg, "WHATSAPP_PROVIDER", "meta")
    monkeypatch.setattr(dcfg, "META_WHATSAPP_ACCESS_TOKEN", FAKE_TOKEN)
    monkeypatch.setattr(dcfg, "META_WHATSAPP_PHONE_NUMBER_ID", FAKE_PHONE_ID)
    monkeypatch.setattr(dcfg, "META_GRAPH_API_BASE", "https://graph.facebook.test")
    monkeypatch.setattr(dcfg, "META_GRAPH_API_VERSION", "v21.0")
    monkeypatch.setattr(dcfg, "PUBLIC_BASE_URL", "https://carebridge.example.test")
    monkeypatch.setattr(dcfg, "REPORT_MEDIA_TTL_SECONDS", 900)
    monkeypatch.setattr(dcfg, "WHATSAPP_RESEND_COOLDOWN_SECONDS", 60)
    monkeypatch.setattr(dcfg, "STORE_REPORT_PDF", True)
    yield


class FakeMeta:
    """Stands in for the one Graph API call. Records it; returns what it is told to."""

    ACCEPTED = {"messaging_product": "whatsapp",
                "contacts": [{"input": "919812340001", "wa_id": "919812340001"}],
                "messages": [{"id": "wamid.TEST0001", "message_status": "accepted"}]}

    def __init__(self, status=200, body=None):
        self.status, self.body = status, body if body is not None else self.ACCEPTED
        self.calls: list[dict] = []

    def __call__(self, url, payload, headers):
        self.calls.append({"url": url, "payload": payload, "headers": headers})
        return self.status, self.body


def meta_error(code, subcode=None):
    err = {"message": "vendor detail that must not reach a patient",
           "type": "OAuthException", "code": code, "fbtrace_id": "Axxxx"}
    if subcode is not None:
        err["error_subcode"] = subcode
    return {"error": err}


@pytest.fixture
def media(tmp_path):
    store = media_mod.ReportMediaStore(tmp_path / "report_media", enabled=True)
    media_mod.set_media_store(store)
    yield store
    media_mod.set_media_store(None)


@pytest.fixture
def meta():
    fake = FakeMeta()
    set_whatsapp_service(WhatsAppReportService(provider=MetaWhatsAppProvider(client=fake)))
    yield fake
    set_whatsapp_service(None)


@pytest.fixture
def client(auth_store, media):
    from src.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(delivery_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def patient(client, media):
    """A signed-in patient who has completed one screening."""
    session = signup(client, PATIENT)
    result = analyze_result()
    media.save(result, PDF_BYTES, account_id=session["account"]["account_id"])
    return {"token": session["token"], "account": session["account"],
            "scan_id": result["scan_id"]}


def send(client, patient, language="en"):
    return client.post(f"/v1/reports/{patient['scan_id']}/whatsapp",
                       json={"language": language}, headers=auth_header(patient["token"]))


def fail_with(body, status=400):
    set_whatsapp_service(WhatsAppReportService(
        provider=MetaWhatsAppProvider(client=FakeMeta(status=status, body=body))))


# ------------------------------------------------- 6. Meta provider success
def test_meta_accepts_the_report_and_the_wamid_is_returned(client, patient, meta):
    """The wamid is the only honest proof a message exists at Meta."""
    r = send(client, patient)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["message_sid"] == "wamid.TEST0001"
    assert body["status"] == "accepted"
    assert body["duplicate"] is False
    assert len(meta.calls) == 1


def test_the_request_meta_receives_is_a_document_pointing_at_the_signed_pdf(client, patient, meta):
    """The wire format, asserted field by field — this is where Cloud API calls go wrong."""
    send(client, patient)
    payload = meta.calls[0]["payload"]

    assert payload["messaging_product"] == "whatsapp"
    assert payload["type"] == "document"
    # Meta wants bare digits. A leading '+' here is silently accepted by some endpoints
    # and rejected by others, so it is normalised rather than passed through.
    assert payload["to"] == "919812340001"
    assert "+" not in payload["to"]

    doc = payload["document"]
    # The REAL report, via the existing signed short-lived media URL. Not a placeholder,
    # not a link to the website, not a regenerated file.
    assert doc["link"].startswith("https://carebridge.example.test/v1/reports/media/")
    assert "token=" in doc["link"], "the media URL must be signed, not a bare path"
    assert f"{patient['scan_id']}.pdf" in doc["link"]
    # The patient sees a report filename in the chat, not a URL fragment.
    assert doc["filename"] == f"dr-report-{patient['scan_id']}.pdf"
    assert doc["caption"]


def test_the_credential_travels_in_the_header_and_never_in_the_response(client, patient, meta):
    send(client, patient)
    call = meta.calls[0]
    assert call["headers"]["Authorization"] == f"Bearer {FAKE_TOKEN}"
    # The token, the phone number id and the patient's full number are all absent from
    # anything the browser receives.
    body = json.dumps(send(client, patient).json())
    assert FAKE_TOKEN not in body
    assert FAKE_PHONE_ID not in body
    assert PATIENT not in body


# ------------------------------------------------- 7/8. Meta provider failures
@pytest.mark.parametrize("meta_code,expected_code,status", [
    # invalid / expired access token — the commonest Cloud API failure by far
    (190, "provider_unconfigured", 503),
    (133010, "provider_unconfigured", 503),
    # the app is still in test mode and this number is not on its allow-list
    (131030, "recipient_not_allowed", 503),
    (131026, "recipient_not_reachable", 400),
    (131021, "invalid_recipient", 400),
    # outside the 24-hour window, only a template may be sent
    (131047, "session_window_closed", 409),
    # Meta could not fetch our PDF — nearly always a dead tunnel
    (131052, "media_unreachable", 502),
    (131053, "media_unreachable", 502),
    (130429, "rate_limited", 429),
    (131042, "provider_trial_limited", 503),
    # anything unmapped stays deliberately opaque
    (999999, "provider_error", 502),
])
def test_each_meta_refusal_becomes_a_safe_application_error(client, patient,
                                                            meta_code, expected_code, status):
    fail_with(meta_error(meta_code))
    try:
        r = send(client, patient)
        assert r.status_code == status
        body = r.json()
        assert body["success"] is False
        assert body["code"] == expected_code
        # No vendor internals reach the client.
        blob = json.dumps(body)
        assert "OAuthException" not in blob
        assert "fbtrace_id" not in blob
        assert "vendor detail" not in blob
        # A refusal must never carry an identifier implying a message exists.
        assert not body.get("message_sid")
    finally:
        set_whatsapp_service(None)


def test_an_error_subcode_is_preferred_over_the_generic_code(client, patient):
    """Graph puts the useful number in `error_subcode`; `code` is often a generic 100."""
    fail_with(meta_error(100, subcode=131030))
    try:
        body = send(client, patient).json()
        assert body["code"] == "recipient_not_allowed"
    finally:
        set_whatsapp_service(None)


def test_a_200_without_a_wamid_is_not_treated_as_success(client, patient):
    """Absence of an id means we have no evidence a message exists, whatever the status."""
    fail_with({"messaging_product": "whatsapp", "messages": []}, status=200)
    try:
        r = send(client, patient)
        assert r.json()["success"] is False
        assert not r.json().get("message_sid")
    finally:
        set_whatsapp_service(None)


def test_an_unreachable_meta_is_a_retryable_error_not_a_crash(client, patient):
    def boom(url, payload, headers):
        raise RuntimeError("connection reset")

    set_whatsapp_service(WhatsAppReportService(provider=MetaWhatsAppProvider(client=boom)))
    try:
        r = send(client, patient)
        assert r.status_code == 502
        assert r.json()["code"] == "provider_unreachable"
    finally:
        set_whatsapp_service(None)


# --------------------------------------------------- Meta configuration gate
@pytest.mark.parametrize("attr,value,label", [
    ("META_WHATSAPP_ACCESS_TOKEN", "", "missing token"),
    ("META_WHATSAPP_PHONE_NUMBER_ID", "", "missing phone number id"),
    # The classic setup mistake: the display phone number pasted where the numeric id
    # belongs. Caught by us, because Graph's own answer points nowhere near the cause.
    ("META_WHATSAPP_PHONE_NUMBER_ID", "+919812340001", "phone number instead of id"),
])
def test_incomplete_meta_configuration_refuses_before_any_network_call(
        client, patient, monkeypatch, attr, value, label):
    monkeypatch.setattr(dcfg, attr, value)
    fake = FakeMeta()
    set_whatsapp_service(WhatsAppReportService(provider=MetaWhatsAppProvider(client=fake)))
    try:
        r = send(client, patient)
        assert r.status_code == 503, label
        assert r.json()["code"] == "not_configured"
        assert fake.calls == [], "must not call Meta when configuration is incomplete"
        # The operator-facing reason names a VARIABLE; it must not reach the patient.
        assert "META_WHATSAPP" not in json.dumps(r.json())
    finally:
        set_whatsapp_service(None)


def test_a_loopback_public_base_url_is_refused_for_meta_too(client, patient, monkeypatch):
    """Meta fetches the PDF from the public internet exactly like Twilio does."""
    monkeypatch.setattr(dcfg, "PUBLIC_BASE_URL", "http://localhost:8080")
    fake = FakeMeta()
    set_whatsapp_service(WhatsAppReportService(provider=MetaWhatsAppProvider(client=fake)))
    try:
        assert send(client, patient).json()["code"] == "not_configured"
        assert fake.calls == []
    finally:
        set_whatsapp_service(None)


# ------------------------------------------------------- 9. WhatsApp disabled
def test_whatsapp_switched_off_refuses_without_calling_meta(client, patient, monkeypatch):
    monkeypatch.setattr(dcfg, "WHATSAPP_ENABLED", False)
    fake = FakeMeta()
    set_whatsapp_service(WhatsAppReportService(provider=MetaWhatsAppProvider(client=fake)))
    try:
        r = send(client, patient)
        assert r.status_code == 503
        assert r.json()["code"] == "not_configured"
        assert fake.calls == []
    finally:
        set_whatsapp_service(None)


# -------------------------------------------------- provider selection layer
def test_the_env_variable_chooses_the_provider(monkeypatch):
    monkeypatch.setattr(dcfg, "WHATSAPP_PROVIDER", "meta")
    assert build_provider().name == "meta"
    monkeypatch.setattr(dcfg, "WHATSAPP_PROVIDER", "twilio")
    assert build_provider().name == "twilio"


def test_an_unknown_provider_name_is_refused_rather_than_guessed(client, patient, monkeypatch):
    """Silently falling back to a provider the operator did not ask for would be worse
    than failing: it could send a patient's report through an unintended vendor."""
    monkeypatch.setattr(dcfg, "WHATSAPP_PROVIDER", "carrier-pigeon")
    ok, why = dcfg.whatsapp_configured()
    assert ok is False
    assert "carrier-pigeon" in why


def test_the_twilio_provider_is_still_intact_and_selectable(monkeypatch):
    """The Meta work must not have removed or degraded the Twilio path."""
    from src.delivery.providers.twilio import TwilioWhatsAppProvider

    monkeypatch.setattr(dcfg, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(dcfg, "TWILIO_ACCOUNT_SID", "ACtest0000000000000000000000000000")
    monkeypatch.setattr(dcfg, "TWILIO_AUTH_TOKEN", "test-token-not-real")
    monkeypatch.setattr(dcfg, "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    provider = build_provider()
    assert isinstance(provider, TwilioWhatsAppProvider)
    assert provider.configured()[0] is True


# ------------------------------------- 1/2/3. the recipient identity invariant
def test_the_recipient_is_the_session_account_and_the_body_cannot_override_it(client, patient, meta):
    """The endpoint has NOWHERE to put a caller-supplied number.

    This is the structural defence against sending a medical report to an arbitrary
    destination: `WhatsAppSendIn` carries a language and nothing else, so an injected
    number is dropped by the schema rather than trusted.
    """
    r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp",
                    json={"language": "en", "mobile": OTHER, "to": OTHER,
                          "to_mobile": OTHER},
                    headers=auth_header(patient["token"]))
    assert r.status_code == 200, r.text
    # The attacker-supplied number appears nowhere in what Meta was asked to do.
    payload = meta.calls[0]["payload"]
    assert payload["to"] == "919812340001"
    assert "919812340002" not in json.dumps(meta.calls[0])


def test_the_recipient_is_the_accounts_number_and_nothing_else(client):
    """The recipient comes from the ACCOUNT, and the request cannot override it.

    This test used to be called `..._is_verified_by_construction` and asserted that an
    Account could only exist after an OTP confirmed that exact number. **That is no
    longer true**: sign-in takes a mobile number as claimed, with no verification, so
    the number on an account is what somebody typed.

    What survives — and what this test now pins — is the OWNERSHIP rule, which is the
    part the delivery layer actually depends on: `WhatsAppSendIn` has no recipient
    field, so a caller cannot direct a report at a number of their choosing. It goes to
    the account's own number, whatever that number's provenance.
    """
    from src.auth.models import Account
    from src.delivery.routes import WhatsAppSendIn

    # Still no duplicate flag: there is one number per account and it is Account.mobile.
    assert not hasattr(Account("a", "+919812340001"), "mobile_verified")

    # The send body accepts a language and nothing else — there is nowhere to put a
    # recipient, which is what makes "sends to someone else's number" unreachable.
    assert set(WhatsAppSendIn.model_fields) == {"language"}

    # And with no session there is no account, so there is no recipient at all.
    client.cookies.clear()
    assert client.post("/v1/reports/sc_x/whatsapp", json={}).status_code == 401


def test_an_anonymous_caller_cannot_send_anything(client, patient, meta):
    """Note the explicit cookie clear.

    `/v1/auth/verify-otp` sets an HttpOnly `dr_session` cookie and `current_account`
    accepts it as well as a bearer header, so a TestClient that has just completed a
    signup is NOT anonymous — its cookie jar still holds a live session. Dropping the
    jar is what makes this test actually test the thing it claims to.
    """
    client.cookies.clear()
    r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"})
    assert r.status_code in (401, 403)
    assert meta.calls == []


# ------------------------------------------- 4. cross-patient report access
def test_a_patient_cannot_send_another_patients_report(client, patient, media, meta):
    """IDOR. The answer is the same 404 as a report that does not exist, so the endpoint
    cannot be used to confirm that someone else's scan id is real."""
    intruder = signup(client, OTHER)
    r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp",
                    json={"language": "en"},
                    headers=auth_header(intruder["token"]))
    assert r.status_code == 404
    assert meta.calls == [], "no message may be dispatched for a report the caller does not own"


# ------------------------------- 14. a delivery failure is not a screening failure
def test_a_meta_failure_leaves_the_report_downloadable(client, patient, media):
    """WhatsApp is an optional channel. The PDF on disk is untouched by a refusal."""
    fail_with(meta_error(131030))
    try:
        assert send(client, patient).json()["success"] is False
    finally:
        set_whatsapp_service(None)
    assert media.pdf_path(patient["scan_id"]) is not None
    assert media.pdf_path(patient["scan_id"]).read_bytes() == PDF_BYTES


# ---------------------------------------------- 10. duplicate-click protection
def test_a_second_click_inside_the_cooldown_does_not_send_twice(client, patient, meta):
    first = send(client, patient).json()
    second = send(client, patient).json()
    assert second["duplicate"] is True
    assert second["message_sid"] == first["message_sid"] == "wamid.TEST0001"
    assert len(meta.calls) == 1, "the cooldown must not produce a second Meta message"


# ------------------------------------------------ E.164 handling, no guessing
@pytest.mark.parametrize("stored,expected", [
    ("+919812340001", "919812340001"),     # India
    ("+14155550123", "14155550123"),       # US — must NOT acquire a +91
    ("+442071838750", "442071838750"),     # UK
])
def test_any_stored_e164_number_is_converted_without_assuming_a_country(stored, expected):
    from src.delivery.providers.meta import _to_digits

    assert _to_digits(stored) == expected
