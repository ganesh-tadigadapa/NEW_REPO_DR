"""The two HTTP surfaces WhatsApp delivery needs, and nothing more.

    POST /v1/reports/{scan_id}/whatsapp     authenticated patient -> send my own report
    GET  /v1/reports/media/{scan_id}.pdf    signed token          -> Twilio fetches the PDF

The second one is the interesting one, so here is the whole reasoning in one place.

Twilio does not accept a file upload; it accepts a URL and fetches the media itself from
its own network. That rules out the session token (it cannot travel to Twilio) and it
rules out `http://localhost:8080/...` (Twilio cannot reach this machine). It very much
does NOT justify serving the reports directory.

So: the URL names ONE report and carries an HMAC signature over that id and an expiry
(default 15 minutes), minted only by the send path, for a report the caller has just
proved they own. There is no parameter anywhere in this module that takes a path, a
directory or a filename; `{scan_id}` is reduced to `[A-Za-z0-9_-]` before it is used,
and the file path is then built by the store. `..`, `/` and `\\` do not survive that
reduction, so traversal has nothing to traverse.

What the endpoint gives up, honestly: anyone holding the signed URL within its lifetime
can fetch that one PDF. That is inherent to "a third party must fetch the media" and is
the same trade every signed-object-storage URL makes. It is bounded to one report, to a
few minutes, and to a URL that only ever existed inside a Twilio API call.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from src.auth.models import Account, mask_mobile
from src.auth.security import current_account
from src.delivery import config as cfg
from src.delivery import media as media_mod
from src.delivery import message as message_mod
from src.delivery.whatsapp import get_whatsapp_service

log = logging.getLogger("dr-delivery.routes")

router = APIRouter(prefix="/v1/reports", tags=["delivery"])

CHANNEL = "whatsapp"

# Safe code -> HTTP status. Everything the patient sees is a translated sentence chosen
# from the code; the status is for clients and logs.
_STATUS = {
    "not_configured": 503,
    "provider_unconfigured": 503,
    "provider_trial_limited": 503,
    "provider_unreachable": 502,
    "provider_error": 502,
    "media_unreachable": 502,
    "rate_limited": 429,
    "invalid_recipient": 400,
    "recipient_not_reachable": 400,
    "recipient_opted_out": 400,
    # Meta-specific: the app is still in test mode and this number is not on its
    # allow-list. An operator action, not something the patient can retry into success.
    "recipient_not_allowed": 503,
    "sender_not_whatsapp": 503,
    "session_window_closed": 409,
    "report_not_ready": 409,
}

# One send at a time per report, per process. This is the cheap half of duplicate
# protection: it closes the double-click and browser-retry races without a queue, a
# broker or a table. The durable half is the cooldown check below, which survives a
# restart because it reads the delivery record on disk.
_IN_FLIGHT: set[str] = set()
_LOCK = threading.Lock()


class WhatsAppSendIn(BaseModel):
    """The ONLY thing a client may influence is which language the message is written in.

    There is deliberately no recipient field. The number is read from the authenticated
    account, so a caller cannot send a patient's report to a number of their choosing —
    the request does not have anywhere to put one.
    """
    language: str = Field(default=message_mod.DEFAULT_LANGUAGE, max_length=8)


def _fail(code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS.get(code, 502),
        content={"success": False, "channel": CHANNEL, "message": message,
                 "code": code, **extra},
    )


def _not_found() -> HTTPException:
    """One response for 'no such report' and 'not your report'.

    Deliberately indistinguishable: a different status for the second case would turn
    this endpoint into an oracle that confirms a scan id exists for some other patient.
    """
    return HTTPException(404, detail={"error": {
        "code": "report_not_found",
        "message": "That report is not available for your account."}})


@router.post("/{scan_id}/whatsapp")
def send_report_on_whatsapp(scan_id: str, body: WhatsAppSendIn,
                            account: Account = Depends(current_account)):
    """Deliver an ALREADY-GENERATED report to the caller's own registered number.

    Nothing is re-analysed, re-graded or re-rendered here. The PDF on disk is the one
    the browser was handed when the screening finished, and the message text is composed
    from the grade fields copied off that same result.
    """
    store = media_mod.get_media_store()
    sid = media_mod.safe_scan_id(scan_id)
    if not sid:
        raise _not_found()

    meta = store.meta(sid)
    # Ownership, then existence of the bytes. Both failures answer the same way.
    if meta is None or meta.get("account_id") != account.account_id:
        raise _not_found()
    # This endpoint composes SCREENING-REPORT wording (message.py) and may therefore only
    # attach a screening report. The store also holds Eye Health Passport comparison
    # PDFs, which have their own endpoint and their own words; asking for one here is
    # answered as "no such report" rather than sent with the wrong message around it.
    # Records written before `kind` existed have none, and are screening reports.
    if meta.get("kind", "screening_report") != "screening_report":
        raise _not_found()
    pdf = store.pdf_path(sid)
    if pdf is None:
        log.warning("whatsapp requested for %s but the PDF is missing", sid)
        return _fail("report_not_ready",
                     "The report file is no longer available. Run the screening again.")

    # --- duplicate protection, half one: a send already running for this report ------
    with _LOCK:
        if sid in _IN_FLIGHT:
            return JSONResponse(status_code=409, content={
                "success": False, "channel": CHANNEL, "code": "already_sending",
                "message": "This report is already being sent."})
        _IN_FLIGHT.add(sid)

    try:
        # --- duplicate protection, half two: it was sent a moment ago ---------------
        # A browser retry or a second tap inside the cooldown gets the FIRST delivery
        # back, truthfully marked as a duplicate. No second Twilio call, no second
        # message, and no false claim that something new was sent.
        previous = store.last_delivery(sid, CHANNEL)
        if previous and _within_cooldown(previous.get("sent_at")):
            return {"success": True, "channel": CHANNEL,
                    "message": "Report sent successfully",
                    "to_masked": previous.get("to_masked"),
                    # The FIRST send's identifiers. Nothing new was dispatched.
                    "message_sid": previous.get("provider_message_id"),
                    "status": previous.get("status"),
                    "sent_at": previous.get("sent_at"), "duplicate": True}

        service = get_whatsapp_service()
        ok, why = service.configured()
        if not ok:
            log.warning("whatsapp delivery unavailable: %s", why)
            return _fail("not_configured", "WhatsApp delivery is not configured.")

        media_url, _expires = media_mod.media_url(sid)
        text = message_mod.build_message(meta, body.language)

        # The recipient is read from the AUTHENTICATED ACCOUNT, never from the request
        # body — see WhatsAppSendIn, which has nowhere to put a number. `account.mobile`
        # is verified by construction: an account only exists once an OTP sent to that
        # exact number was confirmed (src/auth/service.py::verify_otp).
        result = service.send_report(
            to_mobile=account.mobile, media_url=media_url, body=text,
            # Meta shows this as the attachment name in the chat. Twilio ignores it and
            # derives the name from the URL path, which already ends in {scan_id}.pdf.
            filename=meta.get("filename") or f"dr-report-{sid}.pdf")
        if not result.ok:
            return _fail(result.code or "provider_error", result.message
                         or "Unable to send the report on WhatsApp")

        entry = store.record_delivery(
            sid, channel=CHANNEL, provider_message_id=result.provider_message_id,
            status=result.status, to_masked=mask_mobile(account.mobile))
        return {"success": True, "channel": CHANNEL,
                "message": "Report sent successfully",
                "to_masked": mask_mobile(account.mobile),
                # Twilio's own identifiers, passed through unaltered. `status` is
                # whatever Twilio said (queued/accepted/sent) — the UI must not upgrade
                # that into a claim that the patient has received anything.
                "message_sid": result.provider_message_id,
                "status": result.status,
                "sent_at": (entry or {}).get("sent_at"), "duplicate": False}
    finally:
        with _LOCK:
            _IN_FLIGHT.discard(sid)


def _within_cooldown(sent_at: str | None) -> bool:
    if not sent_at:
        return False
    try:
        then = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - then).total_seconds()
    return 0 <= age < cfg.WHATSAPP_RESEND_COOLDOWN_SECONDS


@router.api_route("/media/{scan_id}.pdf", methods=["GET", "HEAD"], include_in_schema=False)
def report_media(scan_id: str, request: Request, token: str = Query(default="")):
    """Serve ONE report to whoever holds a live signature for it. Twilio is the caller.

    Unauthenticated by necessity and capability-scoped by design: no token, wrong token,
    expired token or a token minted for a different scan id all get the same 404.
    """
    sid = media_mod.safe_scan_id(scan_id)
    if not sid or not token or not media_mod.verify_media_token(sid, token):
        # 404 rather than 401: an unauthorised fetch should not confirm that the report
        # exists, and there is no credential the caller could usefully be asked for.
        raise HTTPException(404, detail={"error": {
            "code": "not_found", "message": "not found"}})

    path = media_mod.get_media_store().pdf_path(sid)
    if path is None:
        raise HTTPException(404, detail={"error": {
            "code": "not_found", "message": "not found"}})

    meta = media_mod.get_media_store().meta(sid) or {}
    log.info("report media fetched for %s by %s", sid,
             request.headers.get("user-agent", "unknown")[:40])
    return FileResponse(
        path, media_type="application/pdf",
        filename=meta.get("filename") or f"dr-report-{sid}.pdf",
        headers={
            # A clinical document. It is not cached, not stored by an intermediary and
            # not indexed.
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "X-Content-Type-Options": "nosniff",
        },
    )


__all__ = ["router"]
