"""The HTTP surface of the Eye Health Passport.

Three audiences, three authorisation rules, and they are not the same rule:

    PATIENT   /v1/passport, /v1/passport/screenings/...     own record only
    DOCTOR    /v1/passport/patients/{account_id}            verified doctor AND a grant
    ADMIN     /v1/passport/access                           administrator only

**The patient rule is ownership, not role.** Every patient endpoint below resolves the
record and then compares `account_id` against the CALLER's account. There is no endpoint
here that takes an account id from a patient-facing request, so a patient cannot ask for
somebody else's timeline by editing a URL: the only id they can supply names a screening,
and a screening that is not theirs answers 404.

**The doctor rule is a care relationship, not a role.** A verified doctor can already
read the anonymised report collection. A longitudinal record is a different kind of
object — it links several screenings to one person over time — so it additionally needs
an access grant, created when that doctor records a clinician review on that patient's
screening, or by an administrator. See `store.grant_access`.

**SHARING IS THE PATIENT'S DECISION.** A doctor reaches a patient they have never met
only because that patient gave them a code. `/v1/passport/sharing` is the patient's own
control panel for that: mint a code, see who currently holds access, take it back. A
revocation is effective on the very next request — `store.has_access` re-reads the grant
on every call and there is no cached authorisation anywhere to outlive it.

**404, not 403, for a record that is not yours.** A different status for "exists but not
yours" would turn these endpoints into an oracle confirming that a screening id or an
account id exists. The two cases are deliberately indistinguishable.
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.auth.models import Account, mask_mobile
from src.auth.security import current_account, require_admin, require_report_access
from src.delivery import media as delivery_media
from src.delivery import message as delivery_message
from src.delivery.whatsapp import get_whatsapp_service
from src.passport import config as cfg
from src.passport import media as passport_media
from src.passport import message as passport_message
from src.passport import service as passport_service
from src.passport.comparison import NOT_A_DIAGNOSIS
from src.passport.store import get_passport_store, normalise_share_code, safe_id

log = logging.getLogger("dr-passport.routes")

router = APIRouter(prefix="/v1/passport", tags=["passport"])

CHANNEL = "whatsapp"

# Mirrors the delivery layer's map exactly, because it is the same provider answering.
_STATUS = {
    "not_configured": 503, "provider_unconfigured": 503, "provider_trial_limited": 503,
    "provider_unreachable": 502, "provider_error": 502, "media_unreachable": 502,
    "rate_limited": 429, "invalid_recipient": 400, "recipient_not_reachable": 400,
    "recipient_opted_out": 400, "recipient_not_allowed": 503,
    "sender_not_whatsapp": 503, "session_window_closed": 409,
    "comparison_not_available": 409,
}

# One send at a time per comparison, per process — the cheap half of duplicate
# protection, exactly as `src/delivery/routes.py` does it for the screening report.
_IN_FLIGHT: set[str] = set()
_LOCK = threading.Lock()


def _not_found(what: str = "record") -> HTTPException:
    return HTTPException(404, detail={"error": {
        "code": "not_found",
        "message": f"That {what} is not available for your account."}})


def _fail(code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(status_code=_STATUS.get(code, 502),
                        content={"success": False, "channel": CHANNEL,
                                 "message": message, "code": code, **extra})


# ============================================================== PATIENT
@router.get("")
def my_passport(account: Account = Depends(current_account)):
    """The caller's own Eye Health Passport: timeline, latest comparison, follow-up."""
    return passport_service.passport_for(account.account_id)


@router.get("/status")
def my_status(account: Account = Depends(current_account)):
    """The small answer the screening page asks BEFORE an upload.

    It is what makes "Your previous screening is available." true rather than decorative:
    the page does not guess from local state whether this person has been here before.
    """
    return passport_service.status_for(account.account_id)


@router.get("/screenings/{screening_id}/comparison")
def my_comparison(screening_id: str, account: Account = Depends(current_account)):
    """The comparison for one of the caller's screenings.

    `available: false` with a reason is a normal answer, not an error — a first
    screening and an ungradeable screening both legitimately have no comparison.
    """
    result = passport_service.comparison_for(account.account_id, screening_id)
    if result is None:
        raise _not_found("screening")
    return result


@router.get("/screenings/{screening_id}/comparison.pdf")
def my_comparison_pdf(screening_id: str, account: Account = Depends(current_account)):
    """Download the comparison report.

    This is the promise the WhatsApp card makes good on when delivery fails: the PDF is
    reachable from the website whatever the messaging provider did. It is served through
    the session (not the signed media URL) because the browser already has a session and
    a capability URL would be a second way in for no gain.
    """
    made = passport_media.comparison_pdf_bytes(account.account_id, screening_id)
    if made is None:
        raise _not_found("comparison")
    pdf, filename = made
    return Response(
        content=pdf, media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "X-Robots-Tag": "noindex, nofollow, noarchive",
            "X-Content-Type-Options": "nosniff",
        },
    )


class ComparisonSendIn(BaseModel):
    """The only thing a client may influence is the language.

    There is deliberately no recipient field, for the same reason `WhatsAppSendIn` has
    none: the number is read from the authenticated account, so a caller has nowhere to
    put somebody else's.
    """
    language: str = Field(default=delivery_message.DEFAULT_LANGUAGE, max_length=8)


@router.post("/screenings/{screening_id}/comparison/whatsapp")
def send_comparison_on_whatsapp(screening_id: str, body: ComparisonSendIn,
                                account: Account = Depends(current_account)):
    """Deliver the comparison report to the caller's own verified number.

    Uses the EXISTING WhatsAppReportService and its provider abstraction — this endpoint
    knows nothing about Twilio or Meta, and adding a third provider would not touch it.

    `success: true` means the provider ACCEPTED the message and returned its own id. It
    does not mean the patient has received it, and nothing here upgrades acceptance into
    receipt.
    """
    store = get_passport_store()
    rec = store.get_screening(screening_id)
    if rec is None or rec.get("account_id") != account.account_id:
        raise _not_found("screening")

    made = passport_media.ensure_comparison_pdf(account.account_id, screening_id)
    if made is None:
        # No comparison exists to send. A first screening is the usual reason, and it is
        # not a failure — the screening report itself is still deliverable.
        return _fail("comparison_not_available",
                     "There is no comparison for this screening yet.")
    media_id, comparison = made

    with _LOCK:
        if media_id in _IN_FLIGHT:
            return JSONResponse(status_code=409, content={
                "success": False, "channel": CHANNEL, "code": "already_sending",
                "message": "This comparison is already being sent."})
        _IN_FLIGHT.add(media_id)

    try:
        media_store = delivery_media.get_media_store()
        previous = media_store.last_delivery(media_id, CHANNEL)
        if previous and _within_cooldown(previous.get("sent_at")):
            # A double tap or a browser retry gets the FIRST delivery back, truthfully
            # marked as a duplicate. No second provider call, no second message.
            return {"success": True, "channel": CHANNEL,
                    "message": "Comparison report sent successfully",
                    "to_masked": previous.get("to_masked"),
                    "message_sid": previous.get("provider_message_id"),
                    "status": previous.get("status"),
                    "sent_at": previous.get("sent_at"), "duplicate": True}

        service = get_whatsapp_service()
        ok, why = service.configured()
        if not ok:
            log.warning("comparison delivery unavailable: %s", why)
            return _fail("not_configured", "WhatsApp delivery is not configured.")

        url, _expires = delivery_media.media_url(media_id)
        follow_up = passport_media._follow_up_for(account.account_id, screening_id)
        text = passport_message.build_comparison_message(comparison, follow_up, body.language)
        meta = media_store.meta(media_id) or {}

        result = service.send_report(
            to_mobile=account.mobile, media_url=url, body=text,
            filename=meta.get("filename") or f"{media_id}.pdf")
        if not result.ok:
            return _fail(result.code or "provider_error",
                         result.message or "Unable to send the comparison on WhatsApp")

        entry = media_store.record_delivery(
            media_id, channel=CHANNEL, provider_message_id=result.provider_message_id,
            status=result.status, to_masked=mask_mobile(account.mobile))
        return {"success": True, "channel": CHANNEL,
                "message": "Comparison report sent successfully",
                "to_masked": mask_mobile(account.mobile),
                "message_sid": result.provider_message_id,
                "status": result.status,
                "sent_at": (entry or {}).get("sent_at"), "duplicate": False}
    finally:
        with _LOCK:
            _IN_FLIGHT.discard(media_id)


def _within_cooldown(sent_at: str | None) -> bool:
    if not sent_at:
        return False
    try:
        then = datetime.fromisoformat(str(sent_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    age = (datetime.now(timezone.utc) - then).total_seconds()
    return 0 <= age < cfg.COMPARISON_RESEND_COOLDOWN_SECONDS


# ------------------------------------------------------------- the reminder
@router.get("/follow-up")
def my_follow_up(account: Account = Depends(current_account)):
    """The plan in force, plus whether it has come due. The RETURN half of the loop."""
    store = get_passport_store()
    due = passport_service.due_follow_ups(account.account_id)
    return {
        "follow_up": store.active_follow_up(account.account_id),
        "due": due,
        "is_due": bool(due),
        "history": store.follow_ups(account.account_id),
        "disclaimer": NOT_A_DIAGNOSIS,
    }


@router.post("/follow-up/{follow_up_id}/reminder")
def send_reminder(follow_up_id: str, body: ComparisonSendIn,
                  account: Account = Depends(current_account)):
    """Send the follow-up reminder that brings this SAME ACCOUNT back for a screening.

    It goes out through the EXISTING `WhatsAppReportService.send_report`, unchanged and
    unextended — the provider abstraction sends a document with a message around it, so
    the reminder is that message and the attachment is the patient's own most recent
    report. That is not a workaround: a person being asked to come back for a repeat
    screening is exactly the person who wants last time's result in the same chat.

    The reminder status is recorded as "sent" only when the provider accepted it. There
    is no path in this module that marks a reminder sent without a provider id, and a
    failure leaves the reminder visible on the website with an honest status.
    """
    store = get_passport_store()
    plan = store.get_follow_up(follow_up_id)
    if plan is None or plan.get("account_id") != account.account_id:
        raise _not_found("follow-up")

    attachment = _reminder_attachment(account.account_id, plan)
    if attachment is None:
        passport_service.mark_reminder(follow_up_id, status="failed",
                                       detail="no_report_to_attach")
        return _fail("report_not_ready",
                     "The report for this screening is no longer available.")
    media_id, filename = attachment

    service = get_whatsapp_service()
    ok, why = service.configured()
    if not ok:
        # `why` names a missing VARIABLE. It is logged for the operator and deliberately
        # not returned to the client.
        log.warning("follow-up reminder unavailable: %s", why)
        passport_service.mark_reminder(follow_up_id, status="failed",
                                       detail="provider_not_configured")
        return _fail("not_configured", "WhatsApp delivery is not configured.")

    url, _expires = delivery_media.media_url(media_id)
    text = passport_message.build_reminder_message(plan, body.language)
    result = service.send_report(to_mobile=account.mobile, media_url=url,
                                 body=text, filename=filename)
    if not result.ok:
        passport_service.mark_reminder(follow_up_id, status="failed",
                                       detail=result.code or "provider_error")
        return _fail(result.code or "provider_error",
                     result.message or "Unable to send the reminder on WhatsApp")

    delivery_media.get_media_store().record_delivery(
        media_id, channel=CHANNEL, provider_message_id=result.provider_message_id,
        status=result.status, to_masked=mask_mobile(account.mobile))
    passport_service.mark_reminder(follow_up_id, status="sent",
                                   detail=result.provider_message_id)
    return {"success": True, "channel": CHANNEL,
            "message": "Reminder sent successfully",
            "to_masked": mask_mobile(account.mobile),
            "message_sid": result.provider_message_id,
            "status": result.status,
            "window": plan.get("recommended_window") or {}}


def _reminder_attachment(account_id: str, plan: dict) -> tuple[str, str] | None:
    """(media_id, filename) for the PDF that travels with a reminder, or None.

    The comparison report when one exists — it is the more useful document, because it
    shows the patient why they are being asked back — otherwise the screening report for
    the same visit. Ownership is re-checked on the media metadata even though the plan
    was already matched to the caller: two independent checks on a file that leaves the
    building is the right number.
    """
    store = delivery_media.get_media_store()
    screening_id = plan.get("screening_id") or ""
    made = passport_media.ensure_comparison_pdf(account_id, screening_id)
    candidates = []
    if made is not None:
        candidates.append(made[0])
    candidates.append(safe_id(screening_id))
    for media_id in candidates:
        if not media_id:
            continue
        meta = store.meta(media_id)
        if meta is None or meta.get("account_id") != account_id:
            continue
        if store.pdf_path(media_id) is None:
            continue
        return media_id, meta.get("filename") or f"{media_id}.pdf"
    return None


# ====================================================== PATIENT -> DOCTOR SHARING
class ShareCodeIn(BaseModel):
    """Nothing. Deliberately.

    The patient is the authenticated caller, so there is no account id to supply, and
    the doctor is whoever redeems the code, so there is no doctor id to supply either.
    A request body with nowhere to put someone else's identifier cannot be used to
    share someone else's record.
    """


@router.post("/sharing/codes")
def create_share_code(account: Account = Depends(current_account)):
    """Mint a one-time code the patient can give to a doctor.

    The plaintext is returned HERE AND NOWHERE ELSE — only the hash is stored, so it
    cannot be looked up again, re-sent, or recovered from the store. A patient who
    loses it mints another.
    """
    made = get_passport_store().create_share_code(account_id=account.account_id)
    if made is None:
        raise HTTPException(429, detail={"error": {
            "code": "too_many_share_codes",
            "message": ("You already have the maximum number of unused sharing codes. "
                        "Cancel one, or wait for it to expire.")}})
    record, code = made
    log.info("share code minted by %s (id=%s)", account.account_id, record["code_id"])
    return {
        "ok": True,
        "code_id": record["code_id"],
        # The one and only time this value exists outside the patient's screen.
        "code": code,
        "expires_at": record["expires_at"],
        "expires_in": cfg.SHARE_CODE_TTL_SECONDS,
        "note": ("Give this code to your doctor. It works once, and only until it "
                 "expires. You can take the access back at any time."),
    }


@router.get("/sharing")
def my_sharing(account: Account = Depends(current_account)):
    """Who can see my record, and which of my codes are still unused.

    The doctor entries carry an account id and the claimed professional details of a
    doctor this patient has ALREADY chosen to share with — never a mobile number, and
    never anything about a doctor they have not shared with.
    """
    store = get_passport_store()
    from src.auth.storage import get_auth_store

    accounts = get_auth_store()
    shared = []
    for g in store.grants_for_patient(account.account_id):
        doctor = accounts.get(g.get("doctor_account_id", ""))
        profile = (doctor.doctor_profile or {}) if doctor else {}
        shared.append({
            "doctor_account_id": g.get("doctor_account_id"),
            "doctor_name": profile.get("doctor_name") or "",
            "hospital": profile.get("hospital") or "",
            "granted_at": g.get("granted_at"),
            "reason": g.get("reason"),
        })
    codes = [{"code_id": c["code_id"], "created_at": c["created_at"],
              "expires_at": c["expires_at"]}
             for c in store.active_share_codes(account.account_id)]
    return {
        "shared_with": shared,
        "count": len(shared),
        "active_codes": codes,
        "note": ("Only the doctors listed here can open your screening history. "
                 "Revoking takes effect immediately."),
    }


@router.delete("/sharing/codes/{code_id}")
def cancel_share_code(code_id: str, account: Account = Depends(current_account)):
    """Cancel a code that has not been used yet."""
    if not get_passport_store().cancel_share_code(
            account_id=account.account_id, code_id=code_id):
        raise _not_found("sharing code")
    return {"ok": True, "code_id": safe_id(code_id), "status": "cancelled"}


@router.post("/sharing/{doctor_account_id}/revoke")
def revoke_sharing(doctor_account_id: str, account: Account = Depends(current_account)):
    """Take a doctor's access back.

    `store.has_access` is consulted on every doctor-facing read and re-reads the grant
    from disk, so the next request that doctor makes is refused. There is no session to
    expire and no cache to wait out.
    """
    revoked = get_passport_store().revoke_access(
        account_id=account.account_id,
        doctor_account_id=safe_id(doctor_account_id),
        revoked_by=account.account_id)
    if revoked is None:
        raise _not_found("sharing")
    log.info("patient %s revoked access for doctor %s",
             account.account_id, safe_id(doctor_account_id))
    return {"ok": True, "doctor_account_id": safe_id(doctor_account_id),
            "status": "revoked", "revoked_at": revoked.get("revoked_at")}


class RedeemCodeIn(BaseModel):
    """The code, and nothing else.

    There is no patient id here on purpose: the code names the patient. A doctor who
    could supply both would be able to try a code against an account of their choosing.
    """
    code: str = Field(min_length=4, max_length=32)


@router.post("/sharing/redeem")
def redeem_share_code(body: RedeemCodeIn,
                      doctor: Account = Depends(require_report_access)):
    """A doctor redeems a patient's code, which creates the care relationship.

    Verified doctors only — the code is the patient's half of the decision, and the
    doctor role is the programme's half. Both are required.
    """
    store = get_passport_store()
    record = store.redeem_share_code(code=normalise_share_code(body.code),
                                     doctor_account_id=doctor.account_id)
    if record is None:
        # One answer for unknown / expired / already used / cancelled. Distinguishing
        # them would help somebody guessing codes and helps nobody else.
        raise HTTPException(400, detail={"error": {
            "code": "invalid_share_code",
            "message": "That sharing code is not valid. Ask the patient for a new one."}})

    grant = store.grant_access(
        account_id=record["account_id"], doctor_account_id=doctor.account_id,
        reason="patient_shared_code", granted_by=record["account_id"])
    log.info("doctor %s redeemed a share code for patient %s",
             doctor.account_id, record["account_id"])
    return {"ok": True, "patient_id": record["account_id"],
            "granted_at": grant.get("granted_at"),
            "note": "You can now open this patient's screening history."}


# =============================================================== DOCTOR
def _doctor_patient(account_id: str, doctor: Account) -> str:
    """Resolve and authorise one patient for one doctor, or raise.

    An administrator is allowed through without a grant — the admin role is how grants
    are created in the first place, and an administrator who could not see a record
    could not assign it either.
    """
    aid = str(account_id or "")
    if doctor.is_admin:
        return aid
    if not get_passport_store().has_access(account_id=aid,
                                           doctor_account_id=doctor.account_id):
        # Same answer as "no such patient". See the module docstring.
        raise _not_found("patient record")
    return aid


@router.get("/patients")
def my_patients(doctor: Account = Depends(require_report_access)):
    """The patients this doctor is authorised for. Ids only, no contact details.

    This is the ONLY patient-listing endpoint in the application, and it is scoped to
    the caller's own grants. There is no route anywhere that lists every patient.
    """
    store = get_passport_store()
    ids = store.granted_patients(doctor.account_id)
    return {
        "patients": [{"patient_id": pid,
                      "history_count": len(store.history(pid)),
                      "latest": passport_service.timeline_point(store.history(pid)[-1])
                      if store.history(pid) else None}
                     for pid in ids],
        "count": len(ids),
        "anonymised": True,
    }


@router.get("/patients/{account_id}")
def patient_history(account_id: str, doctor: Account = Depends(require_report_access)):
    """One patient's longitudinal record, for a doctor authorised to see it."""
    aid = _doctor_patient(account_id, doctor)
    return passport_service.patient_history_for_doctor(aid)


@router.get("/by-scan/{scan_id}")
def patient_history_by_scan(scan_id: str, doctor: Account = Depends(require_report_access)):
    """The same record, reached from a report the doctor is looking at.

    This is the route the doctor UI actually uses: from one scan it answers "what else
    do we know about this person over time?" — and refuses unless the doctor holds a
    grant for them, which recording a review on any of their screenings creates.
    """
    rec = get_passport_store().get_screening(scan_id)
    if rec is None or not rec.get("account_id"):
        raise _not_found("patient record")
    aid = _doctor_patient(rec["account_id"], doctor)
    return passport_service.patient_history_for_doctor(aid)


class ClinicianFollowUpIn(BaseModel):
    """A doctor's explicit follow-up recommendation.

    It sets the follow-up PLAN and nothing else. The AI grade, the referral decision and
    the comparison are untouched by this call, which is the property
    `tests/test_passport_longitudinal.py` pins.
    """
    screening_id: str = Field(min_length=1, max_length=64)
    follow_up_months: int = Field(ge=0, le=60)
    reason: str = Field(default="", max_length=500)
    priority: str | None = Field(default=None, pattern="^(routine|soon|prompt|urgent)$")


@router.post("/patients/{account_id}/follow-up")
def set_follow_up(account_id: str, body: ClinicianFollowUpIn,
                  doctor: Account = Depends(require_report_access)):
    """Record a clinician follow-up. It takes precedence over the guideline window."""
    aid = _doctor_patient(account_id, doctor)
    plan = passport_service.set_clinician_follow_up(
        account_id=aid, screening_id=body.screening_id,
        months=body.follow_up_months, reason=body.reason, priority=body.priority,
        clinician_account_id=doctor.account_id)
    if plan is None:
        raise _not_found("screening")
    rec = get_passport_store().get_screening(body.screening_id) or {}
    return {
        "ok": True,
        "follow_up": plan,
        # Echoed back so a caller can see for itself that nothing clinical moved.
        "ai_grade_unchanged": rec.get("icdr_grade"),
        "ai_referable_unchanged": rec.get("referable"),
    }


# ================================================================ ADMIN
class AccessGrantIn(BaseModel):
    account_id: str = Field(min_length=1, max_length=64)
    doctor_account_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(default="administrator_assignment", max_length=200)


@router.post("/access")
def grant_access(body: AccessGrantIn, admin: Account = Depends(require_admin)):
    """Assign a patient's longitudinal record to a doctor. Administrators only."""
    from src.auth.storage import get_auth_store
    doctor = get_auth_store().get(safe_id(body.doctor_account_id))
    if doctor is None or not doctor.is_verified_doctor:
        raise HTTPException(400, detail={"error": {
            "code": "not_a_verified_doctor",
            "message": "Longitudinal access can only be granted to a verified doctor."}})
    entry = get_passport_store().grant_access(
        account_id=body.account_id, doctor_account_id=body.doctor_account_id,
        reason=body.reason, granted_by=admin.account_id)
    return {"ok": True, "grant": entry}


__all__ = ["router"]
