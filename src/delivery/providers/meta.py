"""Meta WhatsApp Cloud API — send the report PDF as a WhatsApp *document*.

Why this provider exists: Twilio's trial tier refuses `MediaUrl` at parameter validation
(code 0), so on an un-upgraded Twilio account a PDF cannot be delivered by any parameter
combination. Meta's Cloud API has a free tier that does send documents, so it is the
provider that makes the demo possible. Both are kept; `WHATSAPP_PROVIDER` chooses.

The wire call, in full:

    POST {graph}/{version}/{PHONE_NUMBER_ID}/messages
    Authorization: Bearer {ACCESS_TOKEN}
    {"messaging_product": "whatsapp", "recipient_type": "individual",
     "to": "919876543210",                      <- E.164 digits, NO leading '+'
     "type": "document",
     "document": {"link": "https://…/sc_x.pdf", "filename": "…", "caption": "…"}}

Two differences from Twilio that matter and are handled here rather than by the caller:

  1. **The recipient format.** Twilio wants `whatsapp:+91…`; Meta wants bare digits. The
     account stores one canonical E.164 string and each provider adapts it.
  2. **The filename is ours to set.** Meta shows `document.filename` as the attachment
     name in the chat, so the patient sees `dr-report-….pdf` rather than a URL fragment.
     Twilio derives it from the URL path instead, which is why the interface passes it.

Meta still fetches `link` from the public internet exactly like Twilio does, so the
signed short-lived media URL in media.py is reused unchanged — no new media mechanism.

Logging rules are identical to the Twilio provider: recipient MASKED, body never logged,
no credential logged or returned, vendor numeric code logged because it is what makes a
failure debuggable.
"""
from __future__ import annotations

import logging

from src.auth.models import mask_mobile
from src.delivery import config as cfg
from src.delivery.providers.base import GENERIC_FAILURE, SendResult

log = logging.getLogger("dr-delivery.whatsapp.meta")


# Meta's numeric codes -> the shared vocabulary in base.py. Anything unlisted becomes the
# generic failure; a raw Graph API message must never reach a patient.
_META_ERRORS: dict[int, tuple[str, str]] = {
    # --- credentials / app configuration ------------------------------------
    0: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    3: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    10: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    # The classic one: the access token expired. A Cloud API *temporary* token lasts 24
    # hours, which is exactly long enough to work in rehearsal and fail during the demo.
    190: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    131005: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    133010: ("provider_unconfigured", "WhatsApp delivery is not configured."),
    # --- account tier / billing ---------------------------------------------
    131042: ("provider_trial_limited",
             "WhatsApp delivery is not available on this account. The report is still "
             "available to download."),
    131031: ("provider_trial_limited",
             "WhatsApp delivery is not available on this account. The report is still "
             "available to download."),
    # --- recipient ------------------------------------------------------------
    # 131030 is the Meta equivalent of Twilio's sandbox join: an app still in test mode
    # may only message numbers added to its allow-list in the Meta console. This is the
    # single most likely failure in a demo, so it gets its own code and its own sentence
    # rather than being folded into "not reachable".
    131030: ("recipient_not_allowed",
             "This number is not on the WhatsApp test recipient list yet."),
    131026: ("recipient_not_reachable", "That number is not on WhatsApp."),
    131021: ("invalid_recipient", "That mobile number cannot receive WhatsApp messages."),
    131009: ("invalid_recipient", "That mobile number cannot receive WhatsApp messages."),
    # --- the 24-hour customer-service window ---------------------------------
    # Outside it, only an approved template may be sent. Free-form documents are refused.
    131047: ("session_window_closed",
             "WhatsApp needs the patient to message us first before a report can be sent."),
    131051: ("session_window_closed",
             "WhatsApp needs the patient to message us first before a report can be sent."),
    # --- our media URL --------------------------------------------------------
    # Meta could not fetch or accept the PDF. Nearly always an unreachable PUBLIC_BASE_URL
    # (tunnel down) rather than anything about the file itself.
    131052: ("media_unreachable", "The report could not be attached."),
    131053: ("media_unreachable", "The report could not be attached."),
    # --- throttling ------------------------------------------------------------
    130429: ("rate_limited", "Too many messages at once. Try again in a moment."),
    131048: ("rate_limited", "Too many messages at once. Try again in a moment."),
    131049: ("rate_limited", "Too many messages at once. Try again in a moment."),
    # --- transient -------------------------------------------------------------
    131016: ("provider_error", "Unable to send the report on WhatsApp."),
    131000: ("provider_error", "Unable to send the report on WhatsApp."),
}


def _to_digits(mobile: str) -> str:
    """`+919876543210` -> `919876543210`. Meta wants the country code with no '+'."""
    return "".join(ch for ch in str(mobile) if ch.isdigit())


class MetaWhatsAppProvider:
    """Stateless. `client` is the test seam — it replaces the single HTTP call, so every
    branch below is exercised without a network."""

    name = "meta"

    def __init__(self, client=None):
        self._client = client

    # ------------------------------------------------------------------ config
    def configured(self) -> tuple[bool, str]:
        return cfg.meta_whatsapp_configured()

    # ------------------------------------------------------------------- send
    def _post(self, payload: dict) -> tuple[int, dict]:
        url = (f"{cfg.META_GRAPH_API_BASE}/{cfg.META_GRAPH_API_VERSION}/"
               f"{cfg.META_WHATSAPP_PHONE_NUMBER_ID}/messages")
        # The token travels in a header and appears nowhere else — not in the URL, not in
        # a log line, not in a SendResult.
        headers = {"Authorization": f"Bearer {cfg.META_WHATSAPP_ACCESS_TOKEN}",
                   "Content-Type": "application/json"}
        if self._client is not None:
            return self._client(url, payload, headers)

        import httpx
        r = httpx.post(url, json=payload, headers=headers,
                       timeout=cfg.WHATSAPP_TIMEOUT_SECONDS)
        try:
            body = r.json()
        except Exception:                                # noqa: BLE001
            body = {}
        return r.status_code, body

    @staticmethod
    def _translate(status: int, body: dict) -> tuple[str, str]:
        """Graph errors nest under `error`; `error_subcode` is more specific than `code`
        when present, so it is preferred."""
        err = body.get("error") or {}
        for key in ("error_subcode", "code"):
            code = err.get(key)
            if isinstance(code, str) and code.isdigit():
                code = int(code)
            if isinstance(code, int) and code in _META_ERRORS:
                return _META_ERRORS[code]
        if status == 429:
            return "rate_limited", "Too many messages at once. Try again in a moment."
        if status in (401, 403):
            return "provider_unconfigured", "WhatsApp delivery is not configured."
        return GENERIC_FAILURE

    def send_document(self, *, to_mobile: str, media_url: str, body: str,
                      filename: str = "") -> SendResult:
        """Send one report as a WhatsApp document.

        `ok=True` means Meta ACCEPTED the message and returned a `wamid`. It does NOT
        mean the patient has received it, and the UI must not claim more than that.
        """
        document: dict = {"link": media_url}
        if filename:
            document["filename"] = filename
        if body:
            # Meta allows a caption on a document; it is the same sentence Twilio sends
            # as Body, so the patient reads identical wording whichever provider is live.
            document["caption"] = body
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": _to_digits(to_mobile),
            "type": "document",
            "document": document,
        }

        try:
            status, resp = self._post(payload)
        except Exception as e:                           # noqa: BLE001
            # Type name only. An httpx exception message can contain the full request URL.
            log.error("whatsapp send failed for %s: %s", mask_mobile(to_mobile),
                      type(e).__name__)
            return SendResult(False, code="provider_unreachable",
                              message="Could not reach the messaging service. Try again.")

        messages = resp.get("messages") or []
        if status == 200 and messages:
            wamid = (messages[0] or {}).get("id")
            # Meta reports acceptance, not delivery. `message_status` is usually absent;
            # when present on a Cloud API response it reads "accepted".
            msg_status = (messages[0] or {}).get("message_status") or "accepted"
            if wamid:
                log.info("whatsapp report accepted for %s (wamid=%s status=%s)",
                         mask_mobile(to_mobile), wamid, msg_status)
                return SendResult(True, code="sent", message="Report sent successfully",
                                  provider_message_id=wamid, status=msg_status)

        code, message = self._translate(status, resp)
        log.warning("whatsapp send refused for %s: HTTP %s meta_code=%s subcode=%s -> %s",
                    mask_mobile(to_mobile), status,
                    (resp.get("error") or {}).get("code"),
                    (resp.get("error") or {}).get("error_subcode"), code)
        return SendResult(False, code=code, message=message)


__all__ = ["MetaWhatsAppProvider"]
