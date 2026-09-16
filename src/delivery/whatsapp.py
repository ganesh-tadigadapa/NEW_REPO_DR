"""WhatsAppReportService — picks the configured provider and hands it one message.

This used to BE the Twilio integration. It is now the facade in front of two of them:

    WhatsAppReportService
        └── WhatsAppProvider              src/delivery/providers/base.py
              ├── MetaWhatsAppProvider    src/delivery/providers/meta.py
              └── TwilioWhatsAppProvider  src/delivery/providers/twilio.py

The Twilio code was moved, not rewritten — same request, same error map, same log lines.
Nothing above this file changed: `routes.py` still calls `configured()` and
`send_report()` with the same arguments and still receives a `SendResult`. That is the
whole point of the split. Swapping providers is `WHATSAPP_PROVIDER=meta`, not a diff.

Scope is unchanged and still deliberately narrow: this layer takes a recipient, a media
URL and finished text, causes ONE HTTP request, and returns a `SendResult`. It does not
read the database, does not know what a scan is, does not decide who may send anything,
and cannot see a grade.
"""
from __future__ import annotations

import logging

from src.delivery import config as cfg
from src.delivery.providers import (
    MetaWhatsAppProvider, SendResult, TwilioWhatsAppProvider, WhatsAppProvider,
)

log = logging.getLogger("dr-delivery.whatsapp")

# Re-exported so `from src.delivery.whatsapp import SendResult` keeps working for
# anything that imported it before the provider split.
__all__ = ["SendResult", "WhatsAppReportService", "get_whatsapp_service",
           "set_whatsapp_service", "build_provider"]


def build_provider(name: str | None = None) -> WhatsAppProvider:
    """The configured provider, or an explicitly named one.

    Resolved at CALL time rather than import time so that changing `WHATSAPP_PROVIDER`
    — in a test, or by restarting with a different .env — actually takes effect.
    """
    chosen = (name or cfg.WHATSAPP_PROVIDER or "").strip().lower()
    if chosen == "meta":
        return MetaWhatsAppProvider()
    # Twilio is the fallback for an unknown name as well as for "twilio". An unknown
    # value is still reported honestly: `cfg.whatsapp_configured()` refuses it by name,
    # so the endpoint answers "not configured" instead of silently using a provider the
    # operator did not ask for.
    return TwilioWhatsAppProvider()


class WhatsAppReportService:
    """Stateless. Holds a provider, or resolves one from configuration per call."""

    channel = "whatsapp"

    def __init__(self, client=None, provider: WhatsAppProvider | None = None):
        """`provider=` selects an implementation outright.

        `client=` is the ORIGINAL test seam and is kept working verbatim: it means "the
        Twilio provider, with this callable standing in for the HTTP POST". Every
        existing test that says `WhatsAppReportService(client=fake)` keeps its exact
        meaning, which is why none of them needed editing for the provider split.
        """
        if provider is not None:
            self._provider: WhatsAppProvider | None = provider
        elif client is not None:
            self._provider = TwilioWhatsAppProvider(client=client)
        else:
            self._provider = None          # resolved from config on each use

    # ------------------------------------------------------------------ config
    @property
    def provider(self) -> WhatsAppProvider:
        return self._provider or build_provider()

    def configured(self) -> tuple[bool, str]:
        """(ok, reason). `reason` names a missing VARIABLE, never its value."""
        return self.provider.configured()

    # ------------------------------------------------------------------- send
    def send_report(self, *, to_mobile: str, media_url: str, body: str,
                    filename: str = "") -> SendResult:
        """Send one report through the active provider.

        `ok=True` means the provider ACCEPTED the message and returned its own message
        id. It does NOT mean the patient has received it, and the UI must not claim more
        than that.

        The configuration check happens HERE, once, for every provider — so a
        misconfiguration is a clear message rather than a 401 from a vendor in front of
        a patient, and so no provider can forget to do it.
        """
        provider = self.provider
        ok, why = provider.configured()
        if not ok:
            # `why` names a missing variable or an unreachable base URL. It is logged for
            # the operator and deliberately NOT returned to the client.
            log.error("whatsapp send refused before dispatch (provider=%s): %s",
                      provider.name, why)
            return SendResult(False, code="not_configured",
                              message="WhatsApp delivery is not configured.")
        return provider.send_document(to_mobile=to_mobile, media_url=media_url,
                                      body=body, filename=filename)


_SERVICE: WhatsAppReportService | None = None


def get_whatsapp_service() -> WhatsAppReportService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = WhatsAppReportService()
    return _SERVICE


def set_whatsapp_service(service: WhatsAppReportService | None) -> None:
    """Test seam."""
    global _SERVICE
    _SERVICE = service
