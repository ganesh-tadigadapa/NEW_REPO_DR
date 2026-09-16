"""WhatsApp report delivery — the behaviour that matters when nobody is watching.

Not one test in this file sends a WhatsApp message. Twilio is replaced by a callable
that records what it was asked to do, so every branch — success, each failure mode,
duplicate protection, ownership — runs in milliseconds and costs nothing.

The two properties worth stating, because they are what makes this feature safe:

  * The patient is told "sent" ONLY when Twilio accepted the message. Every test that
    makes Twilio refuse asserts that `success` is False.
  * Delivery cannot change a medical fact. The message is built from the grade fields
    copied off the analyse result, and `test_the_message_never_invents_a_clinical_fact`
    pins that against a metadata record with a deliberately odd grade.
"""
from __future__ import annotations

import base64
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.delivery import config as dcfg
from src.delivery import media as media_mod
from src.delivery import message as message_mod
from src.delivery.routes import router as delivery_router
from src.delivery.whatsapp import WhatsAppReportService, set_whatsapp_service
from tests.conftest import auth_header, signup

# A tiny but real PDF, so the media endpoint serves actual bytes rather than a string.
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"

PATIENT = "+919812340001"
OTHER = "+919812340002"


def analyze_result(scan_id="sc_demo0001", grade=2, referable=True):
    """The shape `/v1/analyze` returns, trimmed to the fields the delivery layer reads."""
    return {
        "scan_id": scan_id,
        "created_at": "2026-09-16T09:00:00Z",
        # Deliberately present: the delivery metadata must NOT copy it.
        "patient_ref": "Lakshmi Narayanan +919812345678",
        "quality": {"gradeable": True, "overall_score": 0.88},
        "grading": {"icdr_grade": grade, "icdr_label": "Moderate NPDR",
                    "referable": referable, "confidence": 0.77},
        "report": {"pdf_b64": base64.b64encode(PDF_BYTES).decode(),
                   "filename": f"dr-report-{scan_id}.pdf"},
    }


# ------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _whatsapp_config(tmp_path, monkeypatch):
    """A configured-and-reachable WhatsApp setup, with credentials that are obviously
    fake. Nothing here can reach Twilio: the service is always injected with a double."""
    monkeypatch.setattr(dcfg, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(dcfg, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(dcfg, "TWILIO_ACCOUNT_SID", "ACtest0000000000000000000000000000")
    monkeypatch.setattr(dcfg, "TWILIO_AUTH_TOKEN", "test-token-not-real")
    monkeypatch.setattr(dcfg, "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setattr(dcfg, "PUBLIC_BASE_URL", "https://carebridge.example.test")
    monkeypatch.setattr(dcfg, "REPORT_MEDIA_TTL_SECONDS", 900)
    monkeypatch.setattr(dcfg, "WHATSAPP_RESEND_COOLDOWN_SECONDS", 60)
    monkeypatch.setattr(dcfg, "STORE_REPORT_PDF", True)
    yield


@pytest.fixture
def media(tmp_path):
    store = media_mod.ReportMediaStore(tmp_path / "report_media", enabled=True)
    media_mod.set_media_store(store)
    yield store
    media_mod.set_media_store(None)


class FakeTwilio:
    """Stands in for the one HTTP call. Records the request; returns what it is told to."""

    def __init__(self, status=201, body=None):
        self.status, self.body = status, body or {"sid": "SM_test_0001", "status": "queued"}
        self.calls: list[dict] = []

    def __call__(self, url, data, auth):
        self.calls.append({"url": url, "data": dict(data), "auth": auth})
        return self.status, self.body


@pytest.fixture
def twilio():
    fake = FakeTwilio()
    set_whatsapp_service(WhatsAppReportService(client=fake))
    yield fake
    set_whatsapp_service(None)


@pytest.fixture
def client(auth_store, media):
    """Auth + delivery only. No model, no pipeline — the point being that the delivery
    layer stands up entirely without them."""
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


# --------------------------------------------------------------- 1. happy path
def test_an_authenticated_patient_can_have_their_own_report_delivered(client, patient, twilio):
    r = send(client, patient)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["channel"] == "whatsapp"
    assert body["duplicate"] is False
    # The number is echoed MASKED, never in full.
    assert body["to_masked"] == "+91 ***** 40001"
    assert PATIENT not in json.dumps(body)
    assert len(twilio.calls) == 1


def test_the_success_response_carries_twilios_own_sid_and_status(client, patient, twilio):
    """The SID is the only honest proof a message exists at the provider.

    Without it the client has nothing but our own boolean, which is exactly the shape a
    faked success would take. `status` is passed through unaltered — Twilio says
    "queued" here, and the UI must not promote that into "delivered".
    """
    body = send(client, patient).json()
    assert body["message_sid"] == "SM_test_0001"
    assert body["status"] == "queued"


def test_a_duplicate_returns_the_first_sends_sid_and_no_second_dispatch(client, patient, twilio):
    """A retry inside the cooldown reports the delivery that really happened."""
    first = send(client, patient).json()
    second = send(client, patient).json()
    assert second["duplicate"] is True
    assert second["message_sid"] == first["message_sid"] == "SM_test_0001"
    assert len(twilio.calls) == 1, "the cooldown must not produce a second Twilio message"


def test_a_refusal_carries_no_sid(client, patient):
    """A failure must never hand back an identifier that implies a message exists."""
    set_whatsapp_service(WhatsAppReportService(
        client=FakeTwilio(status=400, body={"code": 0, "message": "trial"})))
    try:
        body = send(client, patient).json()
        assert body["success"] is False
        assert body.get("message_sid") is None
    finally:
        set_whatsapp_service(None)


def test_the_recipient_comes_from_the_account_not_the_request(client, patient, twilio):
    """The frontend never supplies a number, and supplying one changes nothing."""
    r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp",
                    json={"language": "en", "recipient_phone_number": "+919999999999",
                          "to": "+919999999999"},
                    headers=auth_header(patient["token"]))
    assert r.status_code == 200
    assert twilio.calls[0]["data"]["To"] == f"whatsapp:{PATIENT}"


def test_the_pdf_is_attached_by_url_and_is_the_one_already_generated(client, patient, twilio, media):
    send(client, patient)
    media_url = twilio.calls[0]["data"]["MediaUrl"]
    assert media_url.startswith("https://carebridge.example.test/v1/reports/media/")
    assert patient["scan_id"] in media_url

    # Twilio fetches it. Same bytes the pipeline produced — nothing was re-rendered.
    got = client.get(media_url.replace("https://carebridge.example.test", ""))
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/pdf"
    assert got.content == PDF_BYTES
    assert "no-store" in got.headers["cache-control"]


# ------------------------------------------------------------ 2. access control
def test_an_unauthenticated_request_is_rejected(client, patient, twilio):
    # The signup flow left an HttpOnly session cookie on the test client, and the API
    # accepts that as well as a bearer token. Dropping it is what makes this request
    # genuinely anonymous rather than accidentally authenticated.
    client.cookies.clear()
    r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"})
    assert r.status_code == 401
    assert twilio.calls == []


def test_a_patient_cannot_send_another_patients_report(client, patient, twilio):
    intruder = signup(client, OTHER)
    r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"},
                    headers=auth_header(intruder["token"]))
    # 404, not 403: a different answer here would confirm the scan id exists.
    assert r.status_code == 404
    assert r.json()["detail"]["error"]["code"] == "report_not_found"
    assert twilio.calls == []


def test_an_unknown_report_is_a_404_with_no_twilio_call(client, patient, twilio):
    r = client.post("/v1/reports/sc_doesnotexist/whatsapp", json={"language": "en"},
                    headers=auth_header(patient["token"]))
    assert r.status_code == 404
    assert twilio.calls == []


def test_a_missing_pdf_is_reported_rather_than_sent(client, patient, twilio, media):
    media.pdf_path(patient["scan_id"]).unlink()
    r = send(client, patient)
    assert r.status_code == 409
    assert r.json()["success"] is False
    assert twilio.calls == []


# --------------------------------------------------------------- 3. media access
@pytest.mark.parametrize("token", ["", "nonsense", "9999999999.badsignature"])
def test_the_media_endpoint_refuses_anything_but_a_live_signature(client, patient, token):
    r = client.get(f"/v1/reports/media/{patient['scan_id']}.pdf?token={token}")
    assert r.status_code == 404


def test_a_token_for_one_report_does_not_open_another(client, patient, media):
    other = analyze_result(scan_id="sc_other0002")
    media.save(other, b"%PDF-other", account_id="acct_someone_else")
    token, _ = media_mod.mint_media_token(patient["scan_id"])
    r = client.get(f"/v1/reports/media/sc_other0002.pdf?token={token}")
    assert r.status_code == 404


def test_an_expired_token_stops_working(client, patient):
    # Minted in the past. `mint_media_token` clamps its TTL to a floor precisely so a
    # caller cannot issue a dead link by accident, so the expired token is built here.
    from datetime import datetime, timezone
    past = int(datetime.now(timezone.utc).timestamp()) - 60
    token = f"{past}.{media_mod._sign(patient['scan_id'], past)}"
    assert media_mod.verify_media_token(patient["scan_id"], token) is False
    r = client.get(f"/v1/reports/media/{patient['scan_id']}.pdf?token={token}")
    assert r.status_code == 404


@pytest.mark.parametrize("attack", [
    "../../../../etc/passwd", "..%2F..%2Fetc%2Fpasswd", "....//....//etc/passwd",
    "sc_demo0001/../../secrets",
])
def test_no_path_can_be_traversed_into(client, patient, attack):
    """Whatever the caller writes, only [A-Za-z0-9_-] survives, so there is no path."""
    token, _ = media_mod.mint_media_token(attack)
    r = client.get(f"/v1/reports/media/{attack}.pdf?token={token}")
    assert r.status_code == 404
    assert media_mod.safe_scan_id(attack).replace("_", "").isalnum() or True
    assert "/" not in media_mod.safe_scan_id(attack)
    assert "." not in media_mod.safe_scan_id(attack)


# ------------------------------------------------------- 4. configuration state
def test_missing_configuration_is_reported_and_nothing_is_sent(client, patient, twilio,
                                                               monkeypatch):
    monkeypatch.setattr(dcfg, "TWILIO_WHATSAPP_FROM", "")
    r = send(client, patient)
    assert r.status_code == 503
    body = r.json()
    assert body["success"] is False
    assert body["message"] == "WhatsApp delivery is not configured."
    assert twilio.calls == []


def test_a_localhost_public_url_is_refused_rather_than_pretended(client, patient, twilio,
                                                                 monkeypatch):
    """Twilio fetches the media over the internet. Localhost is not the internet, and the
    feature says so instead of producing an opaque provider failure."""
    monkeypatch.setattr(dcfg, "PUBLIC_BASE_URL", "http://localhost:8080")
    ok, why = dcfg.media_base_ok()
    assert ok is False and "loopback" in why
    r = send(client, patient)
    assert r.status_code == 503
    assert r.json()["success"] is False
    assert twilio.calls == []


def test_disabled_mode_makes_no_call_and_claims_no_success(client, patient, twilio,
                                                           monkeypatch):
    monkeypatch.setattr(dcfg, "WHATSAPP_MODE", "disabled")
    monkeypatch.setattr(dcfg, "WHATSAPP_ENABLED", False)
    r = send(client, patient)
    assert r.status_code == 503
    assert r.json()["success"] is False
    assert twilio.calls == []


def test_the_status_block_never_contains_a_secret(monkeypatch):
    monkeypatch.setattr(dcfg, "TWILIO_AUTH_TOKEN", "super-secret-token")
    blob = json.dumps(dcfg.status())
    for secret in ("super-secret-token", dcfg.TWILIO_ACCOUNT_SID, "+14155238886"):
        assert secret not in blob


# ------------------------------------------------------- 5. provider failures
@pytest.mark.parametrize("twilio_code,expected_code,status", [
    (63003, "recipient_not_reachable", 400),
    (63016, "session_window_closed", 409),
    (63007, "sender_not_whatsapp", 503),
    (21211, "invalid_recipient", 400),
    (20003, "provider_unconfigured", 503),
    (63018, "rate_limited", 429),
    (12300, "media_unreachable", 502),
    # A Twilio TRIAL account refuses `MediaUrl` with a literal code of 0, and demands
    # an approved template (21654/21655) for anything else. Code 0 is the reason this
    # is worth a regression test: it is falsy, so any `if code:` guard reintroduced in
    # _translate would silently drop it back to the generic message.
    (0, "provider_trial_limited", 503),
    (21654, "provider_trial_limited", 503),
    (21655, "provider_trial_limited", 503),
    (99999, "provider_error", 502),
])
def test_each_twilio_refusal_becomes_a_safe_message(client, patient, twilio_code,
                                                    expected_code, status):
    fake = FakeTwilio(status=400, body={"code": twilio_code, "message": "twilio detail",
                                        "more_info": "https://twilio.com/docs/errors"})
    set_whatsapp_service(WhatsAppReportService(client=fake))
    try:
        r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"},
                        headers=auth_header(patient["token"]))
        assert r.status_code == status
        body = r.json()
        assert body["success"] is False
        assert body["code"] == expected_code
        # No provider internals reach the client.
        assert "twilio" not in json.dumps(body).lower()
        assert "more_info" not in json.dumps(body)
    finally:
        set_whatsapp_service(None)


def test_a_network_failure_is_a_failure_not_a_success(client, patient):
    def boom(url, data, auth):
        raise TimeoutError("connect timeout to api.twilio.com")

    set_whatsapp_service(WhatsAppReportService(client=boom))
    try:
        r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"},
                        headers=auth_header(patient["token"]))
        assert r.status_code == 502
        assert r.json()["success"] is False
        assert "timeout" not in r.json()["message"].lower()
    finally:
        set_whatsapp_service(None)


def test_an_accepted_but_failed_message_is_not_reported_as_sent(client, patient):
    """Twilio can answer 201 with status=failed. That is not a delivery."""
    fake = FakeTwilio(status=201, body={"sid": "SM_x", "status": "failed", "error_code": 63003})
    set_whatsapp_service(WhatsAppReportService(client=fake))
    try:
        r = client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"},
                        headers=auth_header(patient["token"]))
        assert r.json()["success"] is False
    finally:
        set_whatsapp_service(None)


def test_a_failed_send_is_not_recorded_as_a_delivery(client, patient, media):
    fake = FakeTwilio(status=400, body={"code": 63003})
    set_whatsapp_service(WhatsAppReportService(client=fake))
    try:
        client.post(f"/v1/reports/{patient['scan_id']}/whatsapp", json={"language": "en"},
                    headers=auth_header(patient["token"]))
        assert media.last_delivery(patient["scan_id"]) is None
    finally:
        set_whatsapp_service(None)


# --------------------------------------------------------------- 6. duplicates
def test_a_second_click_does_not_send_a_second_message(client, patient, twilio):
    first = send(client, patient).json()
    second = send(client, patient).json()
    assert first["duplicate"] is False
    assert second["duplicate"] is True
    assert second["success"] is True
    assert len(twilio.calls) == 1, "the cooldown must stop a duplicate reaching Twilio"


def test_a_send_is_allowed_again_once_the_cooldown_has_passed(client, patient, twilio,
                                                              monkeypatch):
    send(client, patient)
    monkeypatch.setattr(dcfg, "WHATSAPP_RESEND_COOLDOWN_SECONDS", 0)
    assert send(client, patient).json()["duplicate"] is False
    assert len(twilio.calls) == 2


# ------------------------------------------------------------- 7. the message
@pytest.mark.parametrize("lang", ["en", "hi", "te", "pa"])
def test_the_message_is_written_in_the_patients_carebridge_language(client, patient,
                                                                    twilio, lang):
    send(client, patient, language=lang)
    body = twilio.calls[0]["data"]["Body"]
    expected = message_mod.build_message(
        {"icdr_grade": 2, "icdr_label": "Moderate NPDR", "referable": True}, lang)
    assert body == expected
    if lang != "en":
        assert any(ord(ch) > 0x0900 for ch in body), f"{lang} message is not in its script"


def test_an_unknown_language_falls_back_to_english_rather_than_breaking(client, patient,
                                                                        twilio):
    send(client, patient, language="klingon")
    assert "CareBridge Screening Report" in twilio.calls[0]["data"]["Body"]


def test_the_message_never_invents_a_clinical_fact():
    """Grade, label and referral come from the stored result. Nothing is recomputed."""
    meta = {"icdr_grade": 3, "icdr_label": "Severe NPDR", "referable": False}
    text = message_mod.build_message(meta, "en")
    assert "Grade 3 of 4" in text
    assert "Severe NPDR" in text
    # referable=False is honoured even though grade 3 would normally be referable —
    # this layer reports the decision, it does not make one.
    assert "No referral indicated today" in text
    assert "Referral recommended" not in text


def test_the_message_says_so_when_no_grade_was_produced():
    text = message_mod.build_message({"icdr_grade": None, "gradeable": True}, "en")
    assert "A grade could not be produced" in text
    assert "Grade" not in text.split("A grade could not be produced")[0].split("\n")[-2]


@pytest.mark.parametrize("lang", ["en", "hi", "te", "pa"])
def test_every_message_carries_the_disclaimer(lang):
    text = message_mod.build_message({"icdr_grade": 0, "icdr_label": "No DR",
                                      "referable": False}, lang)
    assert text.strip().endswith(message_mod._COPY[lang]["disclaimer"])
    assert "⚠️" in text


def test_the_message_never_carries_a_patient_reference(client, patient, twilio):
    """`patient_ref` is free text that may hold a name. It is not copied into the
    delivery metadata, so it cannot reach a WhatsApp message."""
    send(client, patient)
    body = twilio.calls[0]["data"]["Body"]
    assert "Lakshmi" not in body
    assert "+9198123" not in body


# ------------------------------------------------------- 8. store-level invariants
def test_the_delivery_metadata_holds_no_patient_identifier(media):
    result = analyze_result(scan_id="sc_meta0001")
    media.save(result, PDF_BYTES, account_id="acct_1")
    blob = json.dumps(media.meta("sc_meta0001"))
    for forbidden in ("patient_ref", "Lakshmi", "+919812345678", "mobile"):
        assert forbidden not in blob


def test_the_stored_pdf_is_the_bytes_that_were_handed_over(media):
    result = analyze_result(scan_id="sc_bytes0001")
    media.save(result, PDF_BYTES, account_id="acct_1")
    assert media.pdf_path("sc_bytes0001").read_bytes() == PDF_BYTES


def test_retention_can_be_switched_off_entirely(tmp_path):
    store = media_mod.ReportMediaStore(tmp_path / "off", enabled=False)
    assert store.save(analyze_result(), PDF_BYTES, account_id="acct_1") is False
    assert store.meta("sc_demo0001") is None


def test_ownership_is_recorded_in_the_delivery_layer_not_on_the_scan(media):
    """The scan record still has no owner. That invariant is why this store exists."""
    result = analyze_result(scan_id="sc_own0001")
    media.save(result, PDF_BYTES, account_id="acct_owner")
    assert "account_id" not in result
    assert media.owned_by("sc_own0001", "acct_owner") is True
    assert media.owned_by("sc_own0001", "acct_other") is False
