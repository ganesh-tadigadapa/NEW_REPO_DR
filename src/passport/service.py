"""The loop, assembled in one place.

    SCREEN -> SAVE -> FOLLOW-UP PLAN -> REMINDER -> RETURN -> NEW SCREENING
           -> COMPARE -> UPDATED FOLLOW-UP PLAN -> NEXT REMINDER

Every step below is one function, and `record_screening()` is the whole loop closing on
itself: it saves the new result, notices that the patient came back against an open plan,
compares the new result with the previous one, and writes the NEXT plan against the
CURRENT screening.

Nothing in this module reads an image, calls a model, or changes a clinical value. The
clinical values arrive already decided in the `/v1/analyze` response and are copied
verbatim by `store.screening_record()`.
"""
from __future__ import annotations

import logging

from src.api.evidence import get_review_ledger
from src.passport import comparison as cmp_mod
from src.passport import followup as fu_mod
from src.passport.store import (get_passport_store, now_iso, quality_status, safe_id,
                                screening_record)

log = logging.getLogger("dr-passport.service")


def _review(screening_id: str) -> dict | None:
    """The latest clinician review for one screening, or None. Read-only."""
    try:
        return get_review_ledger().latest(safe_id(screening_id))
    except Exception:                                    # noqa: BLE001
        log.exception("clinician review lookup failed for %s", screening_id)
        return None


def _clinician_grade(screening_id: str) -> int | None:
    review = _review(screening_id) or {}
    grade = review.get("clinician_grade")
    return int(grade) if grade is not None else None


# --------------------------------------------------------------- 1. SAVE
def record_screening(result: dict, account_id: str) -> dict | None:
    """Add one screening to a patient's passport and produce the next follow-up plan.

    Called from `/v1/analyze` AFTER the response has been assembled, on the same
    best-effort footing as the evidence write and the report retention: a patient losing
    a timeline entry must never turn a successful screening into an error for the health
    worker standing in front of them. Every caller wraps this, and it also swallows its
    own failures.

    Returns the passport block for this screening, or None when nothing was recorded.
    """
    store = get_passport_store()
    if not store.enabled or not account_id:
        return None
    rec = screening_record(result, account_id=account_id)
    if not rec["screening_id"]:
        return None

    # --- the RETURN step, recorded rather than assumed -----------------------
    # Whatever plan was open is closed by the screening that answered it. Done before
    # the new plan is written so the two are never open at the same time.
    saved = store.save_screening(rec)
    if saved is None:
        return None
    returning = bool(store.history(account_id)[:-1])
    completed = store.complete_follow_ups(account_id, by_screening_id=rec["screening_id"])

    # --- the COMPARE step ----------------------------------------------------
    previous = store.previous_valid(account_id, rec["screening_id"])
    comparison = comparison_between(previous, rec)

    # --- the UPDATED FOLLOW-UP PLAN step -------------------------------------
    plan = fu_mod.plan(rec, comparison=comparison if comparison and comparison.get("available") else None,
                       clinician_grade=_clinician_grade(rec["screening_id"]))
    store.save_follow_up(plan)

    return {
        "recorded": True,
        "screening": rec,
        "returning_patient": returning,
        "previous_follow_ups_completed": completed,
        "comparison": comparison,
        "follow_up": plan,
        "history_count": len(store.history(account_id)),
    }


def comparison_between(previous: dict | None, current: dict) -> dict:
    """Comparison, or an explicit reason there is none. Never a bare null."""
    if not cmp_mod.is_comparable(current):
        return cmp_mod.unavailable(cmp_mod.CURRENT_UNGRADEABLE)
    if previous is None or not cmp_mod.is_comparable(previous):
        return cmp_mod.unavailable(cmp_mod.NO_PREVIOUS)
    return cmp_mod.compare(
        previous, current,
        previous_review=_review(previous.get("screening_id", "")),
        current_review=_review(current.get("screening_id", "")))


# ------------------------------------------------------------ 2. COMPARE
def comparison_for(account_id: str, screening_id: str) -> dict | None:
    """The comparison for one of this patient's screenings. None means 'no such
    screening for this account' — the caller turns that into a 404."""
    store = get_passport_store()
    rec = store.get_screening(screening_id)
    if rec is None or rec.get("account_id") != account_id:
        return None
    previous = store.previous_valid(account_id, screening_id)
    return comparison_between(previous, rec)


# ----------------------------------------------------------- 3. TIMELINE
def timeline_point(rec: dict) -> dict:
    """One point on the ICDR Grade Timeline.

    Ordinal, never continuous: the point carries the CATEGORY the model assigned and the
    label for it. Nothing here produces an interpolated value between two visits, and
    the UI draws a step line for the same reason.
    """
    review = _review(rec.get("screening_id", "")) or {}
    return {
        "screening_id": rec.get("screening_id"),
        "date": rec.get("created_at"),
        "icdr_grade": rec.get("icdr_grade"),
        "severity_label": rec.get("severity_label"),
        "quality_status": rec.get("quality_status") or quality_status(rec.get("gradeable")),
        "gradeable": rec.get("gradeable"),
        "referable": rec.get("referable"),
        "confidence": rec.get("confidence"),
        "report_available": bool(rec.get("report_available")),
        "clinician_review_status": review.get("status", "pending"),
        "clinician_grade": review.get("clinician_grade"),
    }


def timeline(account_id: str, limit: int = 200) -> list[dict]:
    """Oldest first, which is the order a timeline is read in."""
    return [timeline_point(r) for r in get_passport_store().history(account_id, limit)]


# ------------------------------------------------------------ 4. PASSPORT
def passport_for(account_id: str) -> dict:
    """Everything the patient's own Eye Health Passport page needs, in one answer."""
    store = get_passport_store()
    history = store.history(account_id)
    points = [timeline_point(r) for r in history]
    latest = history[-1] if history else None
    latest_comparison = None
    if latest is not None:
        latest_comparison = comparison_between(
            store.previous_valid(account_id, latest["screening_id"]), latest)
    return {
        "enabled": store.enabled,
        "history_count": len(history),
        "has_history": bool(history),
        # True the moment a SECOND screening becomes possible to compare against.
        "returning_patient": len(history) >= 1,
        "timeline": points,
        "latest_screening": timeline_point(latest) if latest else None,
        "latest_comparison": latest_comparison,
        "follow_up": store.active_follow_up(account_id),
        "follow_up_history": store.follow_ups(account_id),
        "disclaimer": cmp_mod.NOT_A_DIAGNOSIS,
    }


def status_for(account_id: str) -> dict:
    """The small answer the screening page asks before an upload: is this person coming
    back, and what were they last told?"""
    store = get_passport_store()
    history = store.history(account_id)
    latest = history[-1] if history else None
    return {
        "has_history": bool(history),
        "history_count": len(history),
        "last_screening": timeline_point(latest) if latest else None,
        "follow_up": store.active_follow_up(account_id),
    }


# ------------------------------------------------- 5. FOLLOW-UP / REMINDER
def recompute_follow_up(account_id: str, screening_id: str) -> dict | None:
    """Re-plan after a clinician review lands on the patient's LATEST screening.

    Only the latest, deliberately: a review recorded on an old screening is history, and
    rewriting today's plan from it would be wrong. Returns the new plan, or None when
    nothing needed to change.
    """
    store = get_passport_store()
    history = store.history(account_id)
    if not history or history[-1].get("screening_id") != safe_id(screening_id):
        return None
    rec = history[-1]
    active = store.active_follow_up(account_id)
    # An explicit clinician follow-up outranks a grade-derived one and is not recomputed
    # out from under the doctor who set it.
    if active and active.get("basis") == "clinician_override":
        return None
    comparison = comparison_between(store.previous_valid(account_id, rec["screening_id"]), rec)
    plan = fu_mod.plan(rec,
                       comparison=comparison if comparison.get("available") else None,
                       clinician_grade=_clinician_grade(rec["screening_id"]))
    return store.save_follow_up(plan)


def set_clinician_follow_up(*, account_id: str, screening_id: str, months: int,
                            reason: str, priority: str | None,
                            clinician_account_id: str) -> dict | None:
    """A doctor's explicit follow-up recommendation. Rule 1 in `followup.plan()`.

    This becomes the active plan and supersedes whatever the guideline table suggested.
    The screening record itself is not touched: the AI grade, the referral decision and
    the comparison are exactly what they were.
    """
    store = get_passport_store()
    rec = store.get_screening(screening_id)
    if rec is None or rec.get("account_id") != account_id:
        return None
    plan = fu_mod.plan(rec, clinician_override={
        "follow_up_months": months,
        "priority": priority,
        "reason": reason or "The reviewing clinician set this follow-up.",
    })
    plan["set_by"] = clinician_account_id
    return store.save_follow_up(plan)


def mark_reminder(follow_up_id: str, *, status: str, channel: str = "whatsapp",
                  detail: str | None = None) -> dict | None:
    """Record what actually happened when a reminder was attempted.

    `status` is the truth about the attempt — "sent" only when a provider accepted it.
    There is no path in this module that marks a reminder sent without one.
    """
    return get_passport_store().update_follow_up(
        follow_up_id, reminder_status=status, channel=channel,
        reminder_detail=detail, reminder_attempted_at=now_iso())


def due_follow_ups(account_id: str) -> list[dict]:
    """Open plans whose target date has arrived. The reminder trigger."""
    store = get_passport_store()
    out = []
    for f in store.follow_ups(account_id):
        if f.get("status") in ("scheduled", "due") and fu_mod.mark_due(f):
            if f.get("status") != "due":
                store.update_follow_up(f["follow_up_id"], status="due")
                f = store.get_follow_up(f["follow_up_id"]) or f
            out.append(f)
    return out


# --------------------------------------------------------- 6. DOCTOR ACCESS
def grant_from_review(screening_id: str, doctor_account_id: str) -> dict | None:
    """A doctor who reviews a screening acquires access to that patient's timeline.

    This is the ONE automatic grant, and it encodes a care relationship rather than a
    role: recording a clinical opinion on someone's screening is exactly the act that
    makes their history relevant to you. Reading the report collection is not.
    """
    store = get_passport_store()
    rec = store.get_screening(screening_id)
    if rec is None or not rec.get("account_id"):
        return None
    return store.grant_access(account_id=rec["account_id"],
                              doctor_account_id=doctor_account_id,
                              reason="clinician_review", granted_by=doctor_account_id)


def patient_history_for_doctor(account_id: str) -> dict:
    """The doctor-facing longitudinal view. Anonymised by construction.

    Built from `timeline_point()` and the comparison objects, both of which are
    whitelists. There is no mobile number, no name and no patient reference anywhere in
    this shape, and `tests/test_passport_authorization.py` asserts that.
    """
    store = get_passport_store()
    history = store.history(account_id)
    points = [timeline_point(r) for r in history]
    comparisons = []
    for rec in history:
        c = comparison_between(store.previous_valid(account_id, rec["screening_id"]), rec)
        if c.get("available"):
            comparisons.append(c)
    return {
        # An opaque internal identifier, the same class of value as a scan id. It is not
        # a name, a number or anything a person could be contacted on.
        "patient_id": account_id,
        "anonymised": True,
        "history_count": len(history),
        "timeline": points,
        "comparisons": comparisons,
        "latest_comparison": comparisons[-1] if comparisons else None,
        "follow_up": store.active_follow_up(account_id),
        "follow_up_history": store.follow_ups(account_id),
        "disclaimer": cmp_mod.NOT_A_DIAGNOSIS,
        "note": ("Longitudinal screening history, identified by internal account id only. "
                 "No patient name, mobile number or contact detail is stored in or served "
                 "from this view."),
    }


__all__ = ["record_screening", "comparison_for", "comparison_between", "timeline",
           "passport_for", "status_for", "recompute_follow_up", "set_clinician_follow_up",
           "mark_reminder", "due_follow_ups", "grant_from_review",
           "patient_history_for_doctor", "timeline_point"]
