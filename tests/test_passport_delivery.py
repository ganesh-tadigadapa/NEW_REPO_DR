"""The comparison report on WhatsApp — every branch, and not one real message.

The provider is replaced by a callable that records what it was asked to do, exactly as
`tests/test_whatsapp_delivery.py` does for the screening report, so success, each
failure mode, duplicate protection and ownership all run in milliseconds and cost
nothing. Nothing in this file can reach Twilio, Meta or a phone.

The two properties that make this safe are the same two the screening report has, and
they are asserted here for the comparison as well:

  * the patient is told "sent" ONLY when the provider accepted the message, and
  * a delivery failure costs nothing — the comparison is still on the website and the
    PDF is still downloadable, which is what `test_the_pdf_is_still_downloadable_*`
    pins.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.delivery import config as dcfg
from src.delivery import media as media_mod
from src.delivery.routes import router as delivery_router
from src.delivery.whatsapp import WhatsAppReportService, set_whatsapp_service
from src.passport import service as passport_service
from src.passport.routes import router as passport_router
from tests.conftest import auth_header, signup
from tests.test_passport_longitudinal import analyze_result

PATIENT = "+919812360001"
OTHER = "+919812360002"
PDF_BYTES = b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"


@pytest.fixture(autouse=True)
def _whatsapp_config(monkeypatch):
    """A configured-and-reachable setup with credentials that are obviously fake."""
    monkeypatch.setattr(dcfg, "WHATSAPP_MODE", "live")
    monkeypatch.setattr(dcfg, "WHATSAPP_ENABLED", True)
    monkeypatch.setattr(dcfg, "WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(dcfg, "TWILIO_ACCOUNT_SID", "ACtest0000000000000000000000000000")
    monkeypatch.setattr(dcfg, "TWILIO_AUTH_TOKEN", "test-token-not-real")
    monkeypatch.setattr(dcfg, "TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    monkeypatch.setattr(dcfg, "PUBLIC_BASE_URL", "https://carebridge.example.test")
    monkeypatch.setattr(dcfg, "REPORT_MEDIA_TTL_SECONDS", 900)
    monkeypatch.setattr(dcfg, "STORE_REPORT_PDF", True)
    yield


@pytest.fixture
def media(tmp_path):
    store = media_mod.ReportMediaStore(tmp_path / "report_media", enabled=True)
    media_mod.set_media_store(store)
    yield store
    media_mod.set_media_store(None)


class FakeTwilio:
    """Stands in for the one HTTP call. Records the request; returns what it is told."""

    def __init__(self, status=201, body=None):
        self.status = status
        self.body = body or {"sid": "SM_cmp_0001", "status": "queued"}
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
def client(auth_store, evidence, passport, media):
    """Auth + passport + delivery. Still no model and no pipeline."""
    from src.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(passport_router)
    app.include_router(delivery_router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def patient(client, passport, media):
    """A signed-in patient with TWO screenings — grade 1, then grade 2."""
    session = signup(client, PATIENT)
    account_id = session["account"]["account_id"]
    for scan_id, grade, when in [("sc_p1", 1, "2026-09-16T09:00:00Z"),
                                 ("sc_p2", 2, "2027-03-16T09:00:00Z")]:
        result = analyze_result(scan_id, grade=grade, created_at=when)
        passport_service.record_screening(result, account_id)
        media.save(result, PDF_BYTES, account_id=account_id)
    return {"token": session["token"], "account": session["account"],
            "account_id": account_id, "scan_id": "sc_p2"}


def send(client, patient, language="en", scan_id=None):
    sid = scan_id or patient["scan_id"]
    return client.post(f"/v1/passport/screenings/{sid}/comparison/whatsapp",
                       json={"language": language}, headers=auth_header(patient["token"]))


# --------------------------------------------------- 13. the comparison report
def test_a_comparison_report_is_generated_and_delivered(client, patient, twilio):
    r = send(client, patient)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["success"] is True
    assert body["channel"] == "whatsapp"
    assert body["duplicate"] is False
    assert body["message_sid"] == "SM_cmp_0001"
    assert body["status"] == "queued"
    # The number is echoed MASKED, never in full.
    assert body["to_masked"] == "+91 ***** 60001"
    assert PATIENT not in json.dumps(body)
    assert len(twilio.calls) == 1


def test_the_message_carries_the_comparison_and_the_follow_up(client, patient, twilio):
    """Requirement 10, checked in the text the patient actually receives."""
    send(client, patient)
    text = twilio.calls[0]["data"]["Body"]
    assert "CareBridge Eye Health Passport" in text
    assert "16 Sep 2026" in text and "16 Mar 2027" in text     # both dates
    assert "Grade 1 of 4" in text and "Grade 2 of 4" in text   # both grades
    assert "Mild NPDR" in text and "Moderate NPDR" in text     # both severities
    assert "1 → 2" in text                                     # the category change
    assert "one ICDR category higher" in text
    assert "Suggested follow-up" in text                       # the follow-up window
    assert "not a medical diagnosis" in text                   # the disclaimer
    # And nothing stronger than the comparison supports.
    assert "worsened" not in text.lower() and "progressed" not in text.lower()


def test_the_message_is_written_in_the_patients_carebridge_language(client, patient, twilio):
    send(client, patient, language="te")
    text = twilio.calls[0]["data"]["Body"]
    assert "కేర్‌బ్రిడ్జ్" in text
    assert "ఐసీడీఆర్ వర్గం" in text
    # The ICDR labels stay as the scale defines them, as everywhere else in the product.
    assert "Moderate NPDR" in text


def test_the_attached_pdf_is_the_comparison_report_not_the_screening_report(
        client, patient, twilio, media):
    send(client, patient)
    media_url = twilio.calls[0]["data"]["MediaUrl"]
    assert "/v1/reports/media/cmp_sc_p2.pdf" in media_url

    # The provider fetches it over the signed URL, exactly as it fetches a report.
    got = client.get(media_url.replace("https://carebridge.example.test", ""))
    assert got.status_code == 200
    assert got.headers["content-type"] == "application/pdf"
    assert got.content.startswith(b"%PDF")
    assert got.content != PDF_BYTES, "this must be the comparison PDF, not the report"


def test_the_recipient_comes_from_the_account_not_the_request(client, patient, twilio):
    r = client.post("/v1/passport/screenings/sc_p2/comparison/whatsapp",
                    json={"language": "en", "to": "+919999999999",
                          "recipient_phone_number": "+919999999999"},
                    headers=auth_header(patient["token"]))
    assert r.status_code == 200
    assert twilio.calls[0]["data"]["To"] == f"whatsapp:{PATIENT}"


def test_a_duplicate_send_returns_the_first_delivery_and_does_not_dispatch_again(
        client, patient, twilio):
    first = send(client, patient).json()
    second = send(client, patient).json()
    assert second["duplicate"] is True
    assert second["message_sid"] == first["message_sid"]
    assert len(twilio.calls) == 1


# ------------------------------------------------- 14. the provider refuses
@pytest.mark.parametrize("status,body,expected_code", [
    (400, {"code": 63003}, "recipient_not_reachable"),
    (400, {"code": 21610}, "recipient_opted_out"),
    (400, {"code": 0}, "provider_trial_limited"),
    (400, {"code": 63016}, "session_window_closed"),
    (401, {}, "provider_unconfigured"),
    (429, {}, "rate_limited"),
])
def test_a_provider_failure_is_reported_honestly(client, patient, status, body,
                                                 expected_code):
    set_whatsapp_service(WhatsAppReportService(client=FakeTwilio(status=status, body=body)))
    try:
        r = send(client, patient)
        payload = r.json()
        assert payload["success"] is False
        assert payload["code"] == expected_code
        # A failure must never hand back an identifier implying a message exists.
        assert payload.get("message_sid") is None
    finally:
        set_whatsapp_service(None)


def test_an_unreachable_provider_is_not_reported_as_sent(client, patient):
    class Exploding:
        def __call__(self, *a, **k):
            raise ConnectionError("no network")

    set_whatsapp_service(WhatsAppReportService(client=Exploding()))
    try:
        payload = send(client, patient).json()
        assert payload["success"] is False
        assert payload["code"] == "provider_unreachable"
    finally:
        set_whatsapp_service(None)


def test_an_unconfigured_provider_says_so_rather_than_failing_at_the_vendor(
        client, patient, monkeypatch):
    monkeypatch.setattr(dcfg, "TWILIO_WHATSAPP_FROM", "")
    set_whatsapp_service(WhatsAppReportService())
    try:
        r = send(client, patient)
        assert r.status_code == 503
        assert r.json()["code"] == "not_configured"
    finally:
        set_whatsapp_service(None)


# -------------------------- 15. the report survives a delivery failure
def test_the_pdf_is_still_downloadable_when_whatsapp_fails(client, patient):
    """The promise the UI makes when delivery fails, asserted rather than assumed."""
    set_whatsapp_service(WhatsAppReportService(
        client=FakeTwilio(status=400, body={"code": 63003})))
    try:
        assert send(client, patient).json()["success"] is False
    finally:
        set_whatsapp_service(None)

    pdf = client.get("/v1/passport/screenings/sc_p2/comparison.pdf",
                     headers=auth_header(patient["token"]))
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_the_comparison_is_still_readable_when_whatsapp_fails(client, patient):
    set_whatsapp_service(WhatsAppReportService(
        client=FakeTwilio(status=400, body={"code": 63003})))
    try:
        assert send(client, patient).json()["success"] is False
    finally:
        set_whatsapp_service(None)

    r = client.get("/v1/passport/screenings/sc_p2/comparison",
                   headers=auth_header(patient["token"]))
    assert r.status_code == 200
    assert r.json()["change_label"] == "One ICDR category higher"


def test_nothing_is_sent_when_there_is_no_comparison_yet(client, patient, twilio):
    """A first screening has nothing to compare. That is a refusal, not a message."""
    r = send(client, patient, scan_id="sc_p1")
    assert r.status_code == 409
    assert r.json()["code"] == "comparison_not_available"
    assert twilio.calls == []


# ------------------------------------------------------------- the reminder
def test_a_follow_up_reminder_is_sent_and_recorded(client, patient, passport, twilio):
    plan = passport.active_follow_up(patient["account_id"])
    r = client.post(f"/v1/passport/follow-up/{plan['follow_up_id']}/reminder",
                    json={"language": "en"}, headers=auth_header(patient["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    text = twilio.calls[0]["data"]["Body"]
    assert "follow-up reminder" in text.lower()
    # A reminder names no grade and no referral status: it is read on a lock screen.
    assert "Grade" not in text and "NPDR" not in text
    assert passport.get_follow_up(plan["follow_up_id"])["reminder_status"] == "sent"


def test_a_failed_reminder_is_recorded_as_failed_not_as_sent(client, patient, passport):
    plan = passport.active_follow_up(patient["account_id"])
    set_whatsapp_service(WhatsAppReportService(
        client=FakeTwilio(status=400, body={"code": 63003})))
    try:
        r = client.post(f"/v1/passport/follow-up/{plan['follow_up_id']}/reminder",
                        json={"language": "en"}, headers=auth_header(patient["token"]))
        assert r.json()["success"] is False
    finally:
        set_whatsapp_service(None)
    assert passport.get_follow_up(plan["follow_up_id"])["reminder_status"] == "failed"


def test_a_reminder_for_someone_elses_follow_up_is_not_found(client, patient, passport,
                                                             twilio):
    other = signup(client, OTHER)
    passport_service.record_screening(
        analyze_result("sc_o1", grade=1, created_at="2026-09-16T09:00:00Z"),
        other["account"]["account_id"])
    theirs = passport.active_follow_up(other["account"]["account_id"])

    r = client.post(f"/v1/passport/follow-up/{theirs['follow_up_id']}/reminder",
                    json={"language": "en"}, headers=auth_header(patient["token"]))
    assert r.status_code == 404
    assert twilio.calls == []


# ------------------------------------- the two documents are not interchangeable
def test_the_screening_report_endpoint_refuses_to_send_a_comparison_pdf(
        client, patient, twilio):
    """The comparison PDF shares the media store, and only the media store.

    Asking the screening-report endpoint for `cmp_...` would attach the comparison to
    screening-report wording. It answers "no such report" instead.
    """
    send(client, patient)              # creates cmp_sc_p2 in the media store
    twilio.calls.clear()
    r = client.post("/v1/reports/cmp_sc_p2/whatsapp", json={"language": "en"},
                    headers=auth_header(patient["token"]))
    assert r.status_code == 404
    assert twilio.calls == []


def test_the_screening_report_endpoint_still_works_for_a_real_report(client, patient,
                                                                     twilio):
    """The guard above must not have broken the feature it sits in front of."""
    r = client.post("/v1/reports/sc_p2/whatsapp", json={"language": "en"},
                    headers=auth_header(patient["token"]))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True
    media_url = twilio.calls[0]["data"]["MediaUrl"]
    assert "/v1/reports/media/sc_p2.pdf?token=" in media_url
    assert "cmp_" not in media_url
