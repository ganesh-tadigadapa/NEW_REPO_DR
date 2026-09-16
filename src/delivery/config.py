"""Configuration for WhatsApp report delivery.

Read from the environment, never from a request, and never returned by an API.

Two things are worth stating up front, because getting either wrong is the usual way a
feature like this goes bad:

  1. **Twilio Verify and Twilio WhatsApp are different capabilities.** They share an
     account (so `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` are the same two secrets the
     OTP layer already uses) and nothing else. Verify has a Service SID and a
     `verify.twilio.com` host; WhatsApp has a sender and the `api.twilio.com` Messages
     resource. A working Verify setup tells you nothing about whether WhatsApp works —
     see docs/WHATSAPP.md.

  2. **Twilio fetches the media itself.** It is a server on the public internet, so the
     media URL has to be one it can reach. `PUBLIC_BASE_URL` is the only place that is
     declared, and `media_base_ok()` refuses a loopback address rather than letting the
     send fail as an opaque Twilio error. We never pretend localhost is reachable.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlparse

# Imported for its side effect as much as its values: src.auth.config loads `.env` from
# the repo root, and it owns AUTH_SECRET, which signs the short-lived media URLs.
from src.auth import config as auth_cfg
from src.common.config import REPO_ROOT

log = logging.getLogger("dr-delivery")


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# ------------------------------------------------------------------ mode
# "live"     -> a real Twilio WhatsApp API call is made
# "disabled" -> no call is made and the UI is told delivery is unavailable
#
# There is deliberately no "mock" or "demo" mode that reports success. A patient being
# told their report was sent when nothing was sent is the one failure this feature must
# not have, so the code to produce it does not exist.
WHATSAPP_MODE = os.getenv("WHATSAPP_MODE", "live").strip().lower()
WHATSAPP_ENABLED = _flag("WHATSAPP_ENABLED", "1") and WHATSAPP_MODE == "live"

# ------------------------------------------------------------------ provider
# Which implementation actually carries the message: "meta" or "twilio".
#
# This is the ONLY switch. There is deliberately no second META_WHATSAPP_ENABLED /
# TWILIO_WHATSAPP_ENABLED pair, because two flags that can contradict each other
# ("provider=meta, meta_enabled=false") is a configuration bug waiting to happen and
# there would be no obvious answer for which one wins. One variable, one meaning.
#
# The default stays "twilio" so an existing deployment that sets none of the Meta
# variables keeps behaving exactly as it did before this provider layer existed.
WHATSAPP_PROVIDER = os.getenv("WHATSAPP_PROVIDER", "twilio").strip().lower()

# ------------------------------------------------------------------ Meta Cloud API
# Backend only, exactly like the Twilio pair: never sent to the browser, never logged,
# never returned by any endpoint. The token in particular is a bearer credential for the
# whole WhatsApp Business account.
META_WHATSAPP_ACCESS_TOKEN = os.getenv("META_WHATSAPP_ACCESS_TOKEN", "").strip()
# The *phone number id* from the Meta console — a numeric id, NOT the phone number.
META_WHATSAPP_PHONE_NUMBER_ID = os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "").strip()
# Not needed to send a message; kept because the console shows it next to the number id
# and operators reliably confuse the two. Surfacing it by name makes setup checkable.
META_WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv(
    "META_WHATSAPP_BUSINESS_ACCOUNT_ID", "").strip()
META_GRAPH_API_BASE = os.getenv(
    "META_GRAPH_API_BASE", "https://graph.facebook.com").rstrip("/")
META_GRAPH_API_VERSION = os.getenv("META_GRAPH_API_VERSION", "v21.0").strip()

# ------------------------------------------------------------------ Twilio
# The same account credentials as Twilio Verify. Backend only: they are never sent to
# the browser, never logged, and never returned by any endpoint.
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "").strip()

# The WhatsApp sender. Either the Twilio sandbox number or an approved WhatsApp sender.
# Accepted with or without the "whatsapp:" prefix; `whatsapp_from()` normalises it.
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()

# Messages API host. Separate from TWILIO_API_BASE (which is Verify's) on purpose.
TWILIO_MESSAGING_API_BASE = os.getenv(
    "TWILIO_MESSAGING_API_BASE", "https://api.twilio.com/2010-04-01").rstrip("/")
WHATSAPP_TIMEOUT_SECONDS = float(os.getenv("WHATSAPP_TIMEOUT_SECONDS", "15"))

# ------------------------------------------------------------------ media
# Where Twilio reaches this API from the public internet. In development this is an
# ngrok/cloudflared tunnel; in deployment it is the Cloud Run URL.
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")

# How long a signed media URL stays valid. Twilio fetches within seconds; 15 minutes is
# slack for a retry, not a window anyone browses in.
REPORT_MEDIA_TTL_SECONDS = int(os.getenv("REPORT_MEDIA_TTL_SECONDS", "900"))

# The PDF the pipeline already generated, kept so it can be delivered without being
# generated a second time. Off => the WhatsApp endpoint has nothing to send and says so.
STORE_REPORT_PDF = _flag("STORE_REPORT_PDF", "1")
REPORT_MEDIA_DIR = Path(
    os.getenv("REPORT_MEDIA_DIR", str(REPO_ROOT / "data" / "interim" / "report_media")))

# Duplicate protection. A second request for the same report inside this window returns
# the first delivery instead of sending again — see routes.py.
WHATSAPP_RESEND_COOLDOWN_SECONDS = int(os.getenv("WHATSAPP_RESEND_COOLDOWN_SECONDS", "60"))

# Hosts that are NOT reachable from Twilio's network, whatever the rest of the URL says.
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "[::1]", ""}


def whatsapp_from() -> str:
    """The sender in the form the Messages API wants: `whatsapp:+1...`."""
    raw = TWILIO_WHATSAPP_FROM
    if not raw:
        return ""
    return raw if raw.startswith("whatsapp:") else f"whatsapp:{raw}"


def media_base_ok() -> tuple[bool, str]:
    """Whether PUBLIC_BASE_URL is something Twilio could actually fetch.

    This check exists because the alternative is worse: without it, a developer running
    on localhost gets a generic Twilio media error minutes into a demo, with nothing
    pointing at the cause.
    """
    if not PUBLIC_BASE_URL:
        return False, ("PUBLIC_BASE_URL is not set. Twilio fetches the PDF over the "
                       "public internet and cannot reach this API without it.")
    parsed = urlparse(PUBLIC_BASE_URL)
    if parsed.scheme not in ("http", "https"):
        return False, "PUBLIC_BASE_URL must start with http:// or https://"
    host = (parsed.hostname or "").lower()
    if host in _LOOPBACK_HOSTS or host.endswith(".local"):
        return False, (f"PUBLIC_BASE_URL points at {host!r}, which is this machine. "
                       "Twilio cannot fetch media from a loopback address — expose the "
                       "API with a tunnel (see docs/WHATSAPP.md) and set the public URL.")
    return True, "ok"


def twilio_whatsapp_configured() -> tuple[bool, str]:
    """Every precondition for a real send, checked in one place.

    Called at startup for the log line AND before each send, so a misconfiguration is a
    clear message rather than a 401 from Twilio in front of a patient.
    """
    if not WHATSAPP_ENABLED:
        return False, f"WhatsApp delivery is switched off (WHATSAPP_MODE={WHATSAPP_MODE})"
    missing = [n for n, v in (("TWILIO_ACCOUNT_SID", TWILIO_ACCOUNT_SID),
                              ("TWILIO_AUTH_TOKEN", TWILIO_AUTH_TOKEN),
                              ("TWILIO_WHATSAPP_FROM", TWILIO_WHATSAPP_FROM)) if not v]
    if missing:
        return False, f"missing {', '.join(missing)}"
    if not TWILIO_ACCOUNT_SID.startswith("AC"):
        return False, "TWILIO_ACCOUNT_SID should start with 'AC'"
    if not whatsapp_from().startswith("whatsapp:+"):
        return False, ("TWILIO_WHATSAPP_FROM should be the WhatsApp sender in E.164 "
                       "form, e.g. whatsapp:+14155238886")
    return media_base_ok()


def meta_whatsapp_configured() -> tuple[bool, str]:
    """The same contract as `twilio_whatsapp_configured`, for the Meta Cloud API.

    Note the last line is the identical `media_base_ok()` call: Meta fetches the PDF
    from the public internet exactly like Twilio does, so a loopback PUBLIC_BASE_URL is
    just as fatal here and is caught in the same place rather than becoming an opaque
    "media download error" (131052) minutes into a demo.
    """
    if not WHATSAPP_ENABLED:
        return False, f"WhatsApp delivery is switched off (WHATSAPP_MODE={WHATSAPP_MODE})"
    missing = [n for n, v in (
        ("META_WHATSAPP_ACCESS_TOKEN", META_WHATSAPP_ACCESS_TOKEN),
        ("META_WHATSAPP_PHONE_NUMBER_ID", META_WHATSAPP_PHONE_NUMBER_ID)) if not v]
    if missing:
        return False, f"missing {', '.join(missing)}"
    # The commonest setup mistake by far: pasting the display phone number where the
    # console wanted its numeric id. Caught here because the Graph API's own answer for
    # it ("Unsupported post request") points nowhere near the real cause.
    if not META_WHATSAPP_PHONE_NUMBER_ID.isdigit():
        return False, ("META_WHATSAPP_PHONE_NUMBER_ID should be the numeric Phone number "
                       "ID from the Meta console, not the phone number itself")
    return media_base_ok()


def whatsapp_configured() -> tuple[bool, str]:
    """Whichever provider is actually selected. The one function the rest of the code
    asks, so adding a provider never means editing a caller."""
    if WHATSAPP_PROVIDER == "meta":
        return meta_whatsapp_configured()
    if WHATSAPP_PROVIDER == "twilio":
        return twilio_whatsapp_configured()
    return False, (f"WHATSAPP_PROVIDER={WHATSAPP_PROVIDER!r} is not a known provider "
                   "(expected 'meta' or 'twilio')")


def signing_secret() -> str:
    """The key for media-URL signatures. Same secret as the session tokens, with the
    purpose mixed into the signed string (see media.py) so a token from one scheme can
    never be replayed as the other."""
    return auth_cfg.AUTH_SECRET


def status() -> dict:
    """Safe, non-secret summary for /health and the frontend capability probe.

    No SID, no token, no sender number, no base URL. Only whether it would work.
    """
    ok, reason = whatsapp_configured()
    return {
        "enabled": WHATSAPP_ENABLED,
        "mode": WHATSAPP_MODE,
        # The provider NAME is safe to publish — it is not a credential, and knowing the
        # demo runs on Meta rather than Twilio tells an attacker nothing they could use.
        "provider": WHATSAPP_PROVIDER,
        "configured": ok,
        # `reason` names the missing VARIABLE, never its value.
        "reason": None if ok else reason,
        "report_pdf_retained": STORE_REPORT_PDF,
    }
