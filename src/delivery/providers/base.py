"""What every WhatsApp provider must look like, and the one shape they all return.

`WhatsAppReportService` is the only caller. It knows this interface and nothing about
Twilio or Meta, which is what lets the active provider be an environment variable
instead of a code change.

A provider has exactly three jobs:

  1. say whether it COULD send (`configured`), without making a network call,
  2. send one already-generated PDF to one number (`send_document`),
  3. translate its own vendor errors into the shared `SendResult` codes below.

Rule 3 is the important one. A vendor error string must never reach a patient — it
leaks provider internals and is written in one language for engineers. Each provider
maps its own numeric codes to the SAME vocabulary of `code` values, so the frontend has
one lookup table regardless of who actually carried the message.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class SendResult:
    """What the route is allowed to know. Nothing in here is a raw exception, a stack
    trace, a credential or a provider URL."""
    ok: bool
    # A stable machine code from the shared vocabulary below. The frontend maps it to a
    # sentence in the patient's language; it is never shown raw.
    code: str = ""
    # English fallback, safe to display. Never contains provider detail.
    message: str = ""
    provider_message_id: str | None = None
    status: str | None = None


# The shared vocabulary. Adding a provider means mapping onto THESE, not inventing new
# ones — every value here already has a translated sentence in web/lib/i18n and an HTTP
# status in routes.py, so an unmapped code would surface as the generic error.
#
#   not_configured          operator has not finished setup (missing env, bad base URL)
#   provider_unconfigured   the vendor rejected our credentials
#   provider_trial_limited  the account tier cannot send this message at all
#   recipient_not_allowed   sender is in test/sandbox mode and this number is not on it
#   recipient_not_reachable the number is not on WhatsApp / has not opted in
#   recipient_opted_out     the number asked us to stop
#   invalid_recipient       not a usable mobile number
#   session_window_closed   outside the 24h window; a template would be required
#   media_unreachable       the provider could not fetch the PDF
#   rate_limited            too many messages
#   provider_unreachable    we could not reach the vendor at all
#   provider_error          anything else — deliberately opaque
GENERIC_FAILURE = ("provider_error", "Unable to send the report on WhatsApp.")


class WhatsAppProvider(Protocol):
    """Implemented by TwilioWhatsAppProvider and MetaWhatsAppProvider."""

    #: Short lowercase id, matching the WHATSAPP_PROVIDER env value. Logged, never shown.
    name: str

    def configured(self) -> tuple[bool, str]:
        """(ok, reason). `reason` names a missing VARIABLE, never its value, and is for
        the operator log only — it is never returned to a browser."""
        ...

    def send_document(self, *, to_mobile: str, media_url: str, body: str,
                      filename: str) -> SendResult:
        """Send ONE PDF. Must not raise for a provider failure — a delivery problem is a
        `SendResult(ok=False)`, because the screening result on the page must survive it.

        `to_mobile` is E.164 with the leading '+', exactly as stored on the account.
        Each provider applies its own wire format (Twilio wants `whatsapp:+91...`,
        Meta wants `91...`), so callers never do that themselves.
        """
        ...


__all__ = ["SendResult", "WhatsAppProvider", "GENERIC_FAILURE"]
