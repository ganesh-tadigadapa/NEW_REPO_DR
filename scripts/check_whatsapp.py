#!/usr/bin/env python3
"""Verify the Twilio WhatsApp setup before involving the browser.

Two modes:

    scripts/check_whatsapp.py                        checks config, sends NOTHING
    scripts/check_whatsapp.py --to +91XXXXXXXXXX     sends ONE real WhatsApp message

This talks to Twilio directly, so it separates "is the WhatsApp channel configured"
from "is the app wired up correctly". Run it first; if it passes, any remaining problem
is in the app, not the account.

Twilio Verify working tells you nothing about this. They are different products on the
same account, and a trial number that can receive an OTP still cannot receive a WhatsApp
message until it has joined the sandbox. See docs/WHATSAPP.md.

No credential is printed. `--to` is echoed masked.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402

from src.auth.models import mask_mobile, normalise_mobile  # noqa: E402
from src.delivery import config as cfg  # noqa: E402
from src.delivery import media as media_mod  # noqa: E402
from src.delivery.whatsapp import WhatsAppReportService  # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
OK, BAD, WARN = f"{GREEN}  ok {RESET}", f"{RED} fail{RESET}", f"{YELLOW} warn{RESET}"


def _media_check() -> bool:
    """Shared by both providers: each one FETCHES the PDF from its own network, so a
    loopback PUBLIC_BASE_URL is equally fatal either way."""
    reachable, why = cfg.media_base_ok()
    print(f"[{OK if reachable else BAD}] media URL is publicly fetchable")
    if not reachable:
        print(f"       {why}")
        print(f"{DIM}       The provider fetches the PDF itself. Expose the API:\n"
              f"         scripts/dev_tunnel.sh      (or: ngrok http 8080)\n"
              f"       then set PUBLIC_BASE_URL to the https URL it prints.{RESET}")
    else:
        sample, _ = media_mod.media_url("sc_example")
        # The signature is truncated: this line goes in terminal scrollback and demo
        # recordings, and a live one would be a working capability for that report.
        print(f"       {sample.split('?')[0]}?token=…")
    return reachable


def _meta_preflight(args) -> int:
    """The Meta Cloud API path. Same shape of answer as the Twilio path below."""
    import httpx

    ok, why = cfg.meta_whatsapp_configured()
    have_creds = bool(cfg.META_WHATSAPP_ACCESS_TOKEN and cfg.META_WHATSAPP_PHONE_NUMBER_ID)
    print(f"[{OK if have_creds else BAD}] credentials present")
    if not have_creds:
        print(f"       {why}")
        print(f"\n{DIM}Set them in .env — see docs/WHATSAPP.md{RESET}\n")
        return 1
    # The id, not the token, and only its ends. The token is never printed at all.
    print(f"       phone number id  {cfg.META_WHATSAPP_PHONE_NUMBER_ID}")
    if not cfg.META_WHATSAPP_PHONE_NUMBER_ID.isdigit():
        print(f"[{BAD}] that is not a numeric Phone number ID")
        print("       Meta wants the ID shown under WhatsApp > API Setup, not the")
        print("       phone number itself.")
        return 1

    reachable = _media_check()

    # --- do the credentials actually work? -----------------------------------
    url = (f"{cfg.META_GRAPH_API_BASE}/{cfg.META_GRAPH_API_VERSION}/"
           f"{cfg.META_WHATSAPP_PHONE_NUMBER_ID}")
    try:
        r = httpx.get(url, params={"fields": "display_phone_number,verified_name,"
                                             "quality_rating,platform_type"},
                      headers={"Authorization": f"Bearer {cfg.META_WHATSAPP_ACCESS_TOKEN}"},
                      timeout=cfg.WHATSAPP_TIMEOUT_SECONDS)
    except Exception as e:                                  # noqa: BLE001
        print(f"[{BAD}] could not reach Meta: {type(e).__name__}")
        return 1
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        err = (body.get("error") or {})
        code = err.get("code")
        print(f"[{BAD}] Meta rejected the credentials (HTTP {r.status_code}, code {code})")
        if code == 190:
            # The single most common demo-day failure, so it gets named explicitly.
            print("       The access token is invalid or EXPIRED. A temporary token from")
            print("       WhatsApp > API Setup lasts only 24 hours — generate a permanent")
            print("       System User token (docs/WHATSAPP.md) before presenting.")
        return 1
    print(f"[{OK}] credentials accepted by Meta")
    print(f"       sender   {body.get('display_phone_number', '?')} "
          f"({body.get('verified_name', '?')})")
    print(f"       quality  {body.get('quality_rating', '?')}")
    print(f"{DIM}       While the app is in test mode every recipient must be added under\n"
          f"       WhatsApp > API Setup > 'To'. Numbers not on that list are refused\n"
          f"       with code 131030, and free-form documents need the patient to have\n"
          f"       messaged the business within the last 24h (code 131047).{RESET}")

    if not args.to:
        print(f"\n{DIM}No --to given, so nothing was sent.\n"
              f"To send one real message:  make whatsapp-check TO=+91XXXXXXXXXX{RESET}\n")
        return 0 if (ok and reachable) else 1

    if not reachable and not args.media:
        print(f"\n[{BAD}] refusing to send: Meta could not fetch the attachment")
        return 1

    to = normalise_mobile(args.to)
    media = args.media or media_mod.media_url("sc_preflight")[0]
    print(f"\nSending ONE real WhatsApp message to {mask_mobile(to)}…")
    result = WhatsAppReportService().send_report(
        to_mobile=to, media_url=media, filename="carebridge-preflight.pdf",
        body="CareBridge preflight. This is a configuration test, not a screening result.")
    if result.ok:
        print(f"[{OK}] Meta accepted the message (id {result.provider_message_id}, "
              f"status {result.status})")
        print(f"{DIM}       'Accepted' is not 'delivered'. Check the phone.{RESET}\n")
        return 0
    print(f"[{BAD}] Meta refused: {result.code} — {result.message}")
    print(f"{DIM}       Full detail is in the API server log.{RESET}\n")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--to", help="mobile number to send a REAL WhatsApp message to")
    ap.add_argument("--media", help="a publicly fetchable URL to attach instead of a report")
    args = ap.parse_args()

    print(f"\nWhatsApp preflight — provider: {cfg.WHATSAPP_PROVIDER}\n" + "-" * 58)

    # ------------------------------------------------------------- 1. the switch
    on = cfg.WHATSAPP_ENABLED
    print(f"[{OK if on else WARN}] delivery enabled (WHATSAPP_MODE={cfg.WHATSAPP_MODE})")
    if not on:
        print("       the app will report 'WhatsApp delivery is not configured'")

    # Everything below this point is vendor-specific.
    if cfg.WHATSAPP_PROVIDER == "meta":
        return _meta_preflight(args)
    if cfg.WHATSAPP_PROVIDER != "twilio":
        print(f"[{BAD}] WHATSAPP_PROVIDER={cfg.WHATSAPP_PROVIDER!r} is not a known "
              f"provider (expected 'meta' or 'twilio')")
        return 1

    # -------------------------------------------------------- 2. credentials
    missing = [n for n, v in (("TWILIO_ACCOUNT_SID", cfg.TWILIO_ACCOUNT_SID),
                              ("TWILIO_AUTH_TOKEN", cfg.TWILIO_AUTH_TOKEN),
                              ("TWILIO_WHATSAPP_FROM", cfg.TWILIO_WHATSAPP_FROM)) if not v]
    print(f"[{OK if not missing else BAD}] credentials and sender present")
    if missing:
        print(f"       missing {', '.join(missing)}")
        print(f"\n{DIM}Set them in .env — see docs/WHATSAPP.md{RESET}\n")
        return 1
    print(f"       account  {cfg.TWILIO_ACCOUNT_SID[:6]}…{cfg.TWILIO_ACCOUNT_SID[-4:]}")
    print(f"       sender   {cfg.whatsapp_from()}")
    # Applies to the classic sandbox number AND to the per-account sender that
    # Twilio's "Try out WhatsApp" onboarding assigns, so it is not number-specific.
    print(f"{DIM}       on a trial sender every recipient must have sent 'join <your-code>'\n"
          f"       to this number first, and the opt-in lapses after ~72h{RESET}")

    # ------------------------------------------- 3. can Twilio fetch our media?
    reachable, why = cfg.media_base_ok()
    print(f"[{OK if reachable else BAD}] media URL is publicly fetchable")
    if not reachable:
        print(f"       {why}")
        print(f"{DIM}       Twilio fetches the PDF itself. Expose the API:\n"
              f"         ngrok http 8080\n"
              f"       then set PUBLIC_BASE_URL to the https URL it prints.{RESET}")
    else:
        sample, _ = media_mod.media_url("sc_example")
        # The signature is truncated: this line goes in terminal scrollback and demo
        # recordings, and a live one would be a working capability for that report.
        print(f"       {sample.split('?')[0]}?token=…")

    # ------------------------------------------------- 4. can we reach Twilio?
    import httpx
    url = f"{cfg.TWILIO_MESSAGING_API_BASE}/Accounts/{cfg.TWILIO_ACCOUNT_SID}.json"
    try:
        r = httpx.get(url, auth=(cfg.TWILIO_ACCOUNT_SID, cfg.TWILIO_AUTH_TOKEN),
                      timeout=cfg.WHATSAPP_TIMEOUT_SECONDS)
    except Exception as e:                                  # noqa: BLE001
        print(f"[{BAD}] could not reach Twilio: {type(e).__name__}")
        return 1
    if r.status_code == 401:
        print(f"[{BAD}] Twilio rejected the credentials (HTTP 401)")
        return 1
    if r.status_code != 200:
        print(f"[{BAD}] Twilio answered HTTP {r.status_code}")
        return 1
    account = r.json()
    kind = account.get("type", "unknown")
    print(f"[{OK}] credentials accepted by Twilio (account type: {kind})")
    if kind == "Trial":
        # Verified against the live API on 2026-09-16, because the older advice here
        # ("it works through the Sandbox") is wrong and wastes an afternoon:
        #   MediaUrl        -> HTTP 400 code 0     "limited parameter access"
        #   Body (freeform) -> HTTP 400 code 21654 "ContentSid Required"  (window OPEN)
        #   Content API     -> HTTP 401 code 20003 "not available on a Trial account"
        # Same from the sandbox sender and the "Try out WhatsApp" sender, so it is an
        # account-tier gate, not a sender or session-window problem. No parameter
        # combination sends a PDF from a trial account.
        print(f"[{BAD}] this is a TRIAL account — it CANNOT send a PDF on WhatsApp")
        print(f"       Twilio refuses MediaUrl outright (code 0), refuses freeform")
        print(f"       Body without a template (21654), and blocks the Content API")
        print(f"       that would create that template (20003).")
        print(f"{DIM}       Everything else above is green, so upgrading the account at\n"
              f"       Console > Billing (add funds to leave trial) is the only\n"
              f"       remaining step. No code change is needed afterwards.{RESET}")

    if not args.to:
        print(f"\n{DIM}No --to given, so nothing was sent.\n"
              f"To send one real message:  make whatsapp-check TO=+91XXXXXXXXXX{RESET}\n")
        return 0 if reachable else 1

    # ------------------------------------------------------ 5. one real message
    if not reachable and not args.media:
        print(f"\n[{BAD}] refusing to send: Twilio could not fetch the attachment")
        return 1

    to = normalise_mobile(args.to)
    media = args.media or media_mod.media_url("sc_preflight")[0]
    print(f"\nSending ONE real WhatsApp message to {mask_mobile(to)}…")
    result = WhatsAppReportService().send_report(
        to_mobile=to, media_url=media,
        body="CareBridge preflight. This is a configuration test, not a screening result.")
    if result.ok:
        print(f"[{OK}] Twilio accepted the message (sid {result.provider_message_id}, "
              f"status {result.status})")
        print(f"{DIM}       'Accepted' is not 'delivered'. Check the phone, and check\n"
              f"       Twilio Console > Monitor > Logs > Messaging for the final status.{RESET}\n")
        return 0
    print(f"[{BAD}] Twilio refused: {result.code} — {result.message}")
    print(f"{DIM}       Full detail is in Twilio Console > Monitor > Logs > Messaging.{RESET}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
