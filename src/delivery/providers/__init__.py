"""WhatsApp providers. One interface, two implementations, chosen by configuration.

    WhatsAppReportService          the only caller (src/delivery/whatsapp.py)
        └── WhatsAppProvider       the interface (base.py)
              ├── MetaWhatsAppProvider     Meta WhatsApp Cloud API   (meta.py)
              └── TwilioWhatsAppProvider   Twilio Messages API       (twilio.py)

Neither provider knows what a scan, an account or a grade is. They are handed a number,
a URL, a caption and a filename, and they return a `SendResult`.
"""
from src.delivery.providers.base import (           # noqa: F401
    GENERIC_FAILURE, SendResult, WhatsAppProvider,
)
from src.delivery.providers.meta import MetaWhatsAppProvider      # noqa: F401
from src.delivery.providers.twilio import TwilioWhatsAppProvider  # noqa: F401

__all__ = ["SendResult", "WhatsAppProvider", "GENERIC_FAILURE",
           "MetaWhatsAppProvider", "TwilioWhatsAppProvider"]
