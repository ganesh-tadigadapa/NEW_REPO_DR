"""Twilio WhatsApp — one call to the Messages resource, and the translation of failures.

This is the ORIGINAL implementation, moved behind the provider interface unchanged. Its
behaviour, its error map and its logging rules are identical to before; only the class
name and the method name changed. Nothing about Twilio was "improved" while moving it,
because the point of the move was to add Meta without touching a working integration.

Why the REST API rather than the `twilio` SDK: the project already talks to Twilio Verify
with `httpx` for exactly this reason — one endpoint does not justify a dependency in the
serving image. The two integrations share nothing but the account credentials.

    Verify    POST verify.twilio.com/v2/Services/{VA...}/Verifications
    WhatsApp  POST api.twilio.com/2010-04-01/Accounts/{AC...}/Messages.json

Logging rules enforced here: the recipient is logged MASKED, the message body is never
logged (it contains a clinical result), and no credential is logged, returned or
included in an error message. The vendor's numeric error code IS logged, because it is
the one thing that makes a failed demo debuggable and it is not sensitive.
"""
from __future__ import annotations

import logging

from src.auth.models import mask_mobile
from src.delivery import config as cfg
from src.delivery.providers.base import GENERIC_FAILURE, SendResult

log = logging.getLogger("dr-delivery.whatsapp.twilio")


# Twilio errors worth turning into something a person can act on. Everything not listed
# becomes a generic failure — an unknown provider error must not leak through as text.
#
# These are the WhatsApp/Messages codes. They have nothing to do with the Verify codes in
# src/auth/verification.py, and the two maps must not be merged.
_TWILIO_ERRORS: dict[int, tuple[str, str]] = {
    20003: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    21211: ("invalid_recipient", "That mobile number cannot receive WhatsApp messages."),
    21606: ("sender_not_whatsapp", "WhatsApp delivery is not configured."),
    21610: ("recipient_opted_out", "This number has opted out of messages from us."),
    21614: ("invalid_recipient", "That number is not a mobile number."),
    # The trial/sandbox case, and by far the most likely one to hit in a demo: the
    # recipient has not joined the sandbox, so there is no WhatsApp channel to send to.
    63003: ("recipient_not_reachable",
            "This number has not opted in to receive WhatsApp messages from us yet."),
    63007: ("sender_not_whatsapp", "WhatsApp delivery is not configured."),
    # Outside the 24-hour customer-service window: freeform messages are not allowed and
    # an approved template would be required.
    63016: ("session_window_closed",
            "WhatsApp needs the patient to message us first before a report can be sent."),
    63018: ("rate_limited", "Too many messages at once. Try again in a moment."),
    63021: ("recipient_not_reachable", "That number is not on WhatsApp."),
    # Trial-account restrictions. A Twilio trial refuses `MediaUrl` outright (it
    # answers 400 with code 0, "limited parameter access") and demands an approved
    # template for anything else — while the Content API that would create that
    # template is itself closed on a trial. There is no parameter combination that
    # sends a PDF from a trial account, so this is reported as the billing problem it
    # is rather than as a transient failure the patient could retry into success.
    0: ("provider_trial_limited",
        "WhatsApp delivery is not available on this account. The report is still "
        "available to download."),
    21654: ("provider_trial_limited",
            "WhatsApp delivery is not available on this account. The report is still "
            "available to download."),
    21655: ("provider_trial_limited",
            "WhatsApp delivery is not available on this account. The report is still "
            "available to download."),
    # Media Twilio could not fetch — almost always a media URL it cannot reach.
    12300: ("media_unreachable", "The report could not be attached."),
    63005: ("media_unreachable", "The report could not be attached."),
    63032: ("media_unreachable", "The report could not be attached."),
}


class TwilioWhatsAppProvider:
    """Stateless. `client` is the test seam — it replaces the HTTP call and nothing else,
    so every branch below is exercised by the suite without a network."""

    name = "twilio"

    def __init__(self, client=None):
        self._client = client

    # ------------------------------------------------------------------ config
    def configured(self) -> tuple[bool, str]:
        return cfg.twilio_whatsapp_configured()

    # ------------------------------------------------------------------- send
    def _post(self, data: dict) -> tuple[int, dict]:
        url = (f"{cfg.TWILIO_MESSAGING_API_BASE}/Accounts/"
               f"{cfg.TWILIO_ACCOUNT_SID}/Messages.json")
        auth = (cfg.TWILIO_ACCOUNT_SID, cfg.TWILIO_AUTH_TOKEN)
        if self._client is not None:
            return self._client(url, data, auth)

        import httpx
        r = httpx.post(url, data=data, auth=auth,
                       timeout=cfg.WHATSAPP_TIMEOUT_SECONDS)
        try:
            body = r.json()
        except Exception:                                # noqa: BLE001
            body = {}
        return r.status_code, body

    @staticmethod
    def _translate(status: int, body: dict) -> tuple[str, str]:
        # An API-level refusal carries `code`; a message that was accepted and then
        # failed carries the same numbers under `error_code`. Both are read so the
        # patient gets the same actionable sentence either way.
        code = body.get("code", body.get("error_code"))
        if isinstance(code, str) and code.isdigit():
            code = int(code)
        if isinstance(code, int) and code in _TWILIO_ERRORS:
            return _TWILIO_ERRORS[code]
        if status == 429:
            return "rate_limited", "Too many messages at once. Try again in a moment."
        if status in (401, 403):
            return "provider_unconfigured", "WhatsApp delivery is not configured."
        return GENERIC_FAILURE

    def send_document(self, *, to_mobile: str, media_url: str, body: str,
                      filename: str = "") -> SendResult:
        """Send one report. Returns a SendResult; never raises for a provider failure.

        `ok=True` means Twilio ACCEPTED the message (it returned a message SID with a
        queued/sent/accepted status). It does NOT mean the patient has read it, and the
        UI must not claim more than that.

        `filename` is accepted for interface parity and ignored: Twilio names the
        attachment from the URL's path, which media.py already ends in `{scan_id}.pdf`.
        """
        to = to_mobile if to_mobile.startswith("whatsapp:") else f"whatsapp:{to_mobile}"
        payload = {
            "From": cfg.whatsapp_from(),
            "To": to,
            "Body": body,
            # The single most important line in this file: Twilio FETCHES this URL. It is
            # a short-lived signed URL for exactly one report — see media.py.
            "MediaUrl": media_url,
        }

        try:
            status, resp = self._post(payload)
        except Exception as e:                           # noqa: BLE001
            # Type name only. An httpx exception message can contain the full request URL.
            log.error("whatsapp send failed for %s: %s", mask_mobile(to_mobile),
                      type(e).__name__)
            return SendResult(False, code="provider_unreachable",
                              message="Could not reach the messaging service. Try again.")

        if status in (200, 201) and resp.get("sid"):
            msg_status = resp.get("status")
            # Twilio can return a 201 carrying a failure status rather than an HTTP error.
            if msg_status in ("failed", "undelivered"):
                code, message = self._translate(400, resp)
                log.warning("whatsapp accepted-then-failed for %s: status=%s code=%s",
                            mask_mobile(to_mobile), msg_status, resp.get("error_code"))
                return SendResult(False, code=code, message=message)
            log.info("whatsapp report queued for %s (sid=%s status=%s)",
                     mask_mobile(to_mobile), resp.get("sid"), msg_status)
            return SendResult(True, code="sent", message="Report sent successfully",
                              provider_message_id=resp.get("sid"), status=msg_status)

        code, message = self._translate(status, resp)
        log.warning("whatsapp send refused for %s: HTTP %s twilio_code=%s -> %s",
                    mask_mobile(to_mobile), status, resp.get("code"), code)
        return SendResult(False, code=code, message=message)


__all__ = ["TwilioWhatsAppProvider"]
