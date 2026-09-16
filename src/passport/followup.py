"""Guideline-informed follow-up windows.

READ THIS BEFORE EDITING. The system is screening/decision-support software. It does not
prescribe, and the language it uses says so: every window it produces is a **suggested
follow-up**, never an instruction. The words are in `WINDOW_COPY` and nowhere else.

Three rules, in strict precedence order, and `plan()` applies them in this order:

  1. **An explicit clinician recommendation wins outright.** If a doctor has recorded a
     follow-up for this screening, that is the plan. The guideline table is not consulted.
  2. **A clinician's own grade replaces the model's** as the input to the table. A doctor
     who reviewed the image and graded it 3 where the model said 2 gets the grade-3
     window, because the clinician's grade is the better fact.
  3. **Otherwise the configured guideline table decides**, from the grade the model
     produced, tightened one step when the screening category has gone up.

There is deliberately NO single universal interval. `GUIDELINE_WINDOWS` is a table keyed
by ICDR grade, held in one place so a programme can retune it to its own protocol without
touching a route, a UI or a test of the comparison logic.

Provenance of the default numbers: they are the commonly published screening intervals
for each ICDR category (no DR / mild / moderate / severe / proliferative), and grades 3
and 4 are expressed as PROMPT SPECIALIST REFERRAL rather than as a long-term reminder —
a severe or proliferative result is not something to put a date on months away. They are
defaults for a demo, they are labelled as such in `basis_note`, and a deployment is
expected to replace them with its own programme's protocol.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from src.passport.store import now_iso, parse_iso

# Priority vocabulary, most relaxed to most urgent. The UI colours from this; it never
# derives urgency from the number of months.
PRIORITIES = ("routine", "soon", "prompt", "urgent")

# ---------------------------------------------------------------- the table
# grade -> (min_months, max_months, priority). Configuration, not a calculation.
GUIDELINE_WINDOWS: dict[int, tuple[int, int, str]] = {
    0: (12, 24, "routine"),
    1: (12, 12, "routine"),
    2: (6, 6, "soon"),
    3: (1, 3, "prompt"),
    4: (0, 1, "urgent"),
}

# An image the gate refused is not a result, so it does not get a screening interval. It
# gets a re-photograph, promptly, and the timeline records the visit without a grade.
RECAPTURE_WINDOW = (0, 1, "prompt")

# Grades at or above this are handled as referrals needing specialist assessment rather
# than as routine long-term reminders. Same threshold the pipeline already uses.
from src.common.config import REFERABLE_MIN_GRADE  # noqa: E402

URGENT_MIN_GRADE = 3

WINDOW_COPY = {
    "routine": "Suggested follow-up screening",
    "soon": "Suggested follow-up screening",
    "prompt": "Prompt specialist assessment suggested",
    "urgent": "Urgent specialist assessment suggested",
}

BASIS_LABELS = {
    "guideline": "Guideline-informed follow-up window",
    "guideline_escalated": "Guideline-informed follow-up window, brought forward",
    "clinician_grade": "Guideline-informed window, using the clinician's grade",
    "clinician_override": "Follow-up recommended by the reviewing clinician",
    "quality_recapture": "Repeat photograph suggested",
}


def _months_label(lo: int, hi: int) -> str:
    if lo == hi == 0:
        return "as soon as possible"
    if lo == 0:
        return f"within {hi} month" if hi == 1 else f"within {hi} months"
    if lo == hi:
        return f"in about {lo} month" if lo == 1 else f"in about {lo} months"
    return f"in {lo}–{hi} months"


def _tighten(window: tuple[int, int, str]) -> tuple[int, int, str]:
    """Bring a window forward one step because the screening category went up.

    Halving rather than jumping to a fixed interval keeps the table the single source of
    the numbers: a programme that retunes GUIDELINE_WINDOWS retunes this too.
    """
    lo, hi, priority = window
    step = PRIORITIES.index(priority)
    tighter = PRIORITIES[min(step + 1, len(PRIORITIES) - 1)]
    return max(0, lo // 2), max(1, hi // 2), tighter


def _due_at(from_iso: str | None, months: int) -> str | None:
    """A target date, or None when the suggestion is 'as soon as possible'.

    Months are approximated as 30-day steps. This is a reminder date for a screening
    programme, not a clinical calculation, and calling it approximate is more honest than
    implying calendar precision the guideline itself does not have.
    """
    start = parse_iso(from_iso)
    if start is None or months <= 0:
        return None
    return (start + timedelta(days=30 * months)).isoformat().replace("+00:00", "Z")


def window_for_grade(grade: int | None, *, gradeable: bool = True,
                     escalated: bool = False) -> tuple[tuple[int, int, str], str]:
    """(window, basis). The table lookup, and nothing else."""
    if gradeable is False:
        return RECAPTURE_WINDOW, "quality_recapture"
    if grade is None:
        # The gate passed but no model grade exists. There is no result to schedule
        # against, so the patient is asked to come back at the most cautious routine
        # interval rather than being given a number that means nothing.
        return GUIDELINE_WINDOWS[1], "guideline"
    base = GUIDELINE_WINDOWS.get(int(grade), GUIDELINE_WINDOWS[1])
    # Severe and proliferative are already specialist referrals; there is nothing to
    # bring forward and no honest way to make "as soon as possible" sooner.
    if escalated and int(grade) < URGENT_MIN_GRADE:
        return _tighten(base), "guideline_escalated"
    return base, "guideline"


def plan(screening: dict, *, comparison: dict | None = None,
         clinician_override: dict | None = None,
         clinician_grade: int | None = None,
         channel: str = "whatsapp") -> dict:
    """The follow-up record for one screening. Precedence is the module docstring's.

    `screening` is a passport row. `comparison` is the comparison object for this
    screening, or None. Neither is modified.
    """
    grade = screening.get("icdr_grade")
    gradeable = screening.get("gradeable")
    escalated = bool(comparison and comparison.get("grade_change", 0) > 0)

    # ---- rule 1: an explicit clinician recommendation wins outright ---------
    if clinician_override:
        months = int(clinician_override.get("follow_up_months", 0))
        lo = hi = max(0, months)
        priority = clinician_override.get("priority") or (
            "urgent" if months == 0 else "soon" if months <= 3 else "routine")
        basis = "clinician_override"
        reason = (clinician_override.get("reason")
                  or "The reviewing clinician set this follow-up.")
    else:
        # ---- rule 2: the clinician's grade, when they recorded one ----------
        effective_grade = clinician_grade if clinician_grade is not None else grade
        (lo, hi, priority), basis = window_for_grade(
            effective_grade, gradeable=gradeable, escalated=escalated)
        if clinician_grade is not None and basis == "guideline":
            basis = "clinician_grade"
        # ---- rule 3: the table, with a reason a person can read -------------
        reason = _reason(effective_grade, gradeable, escalated, basis)

    referral = bool(screening.get("referable")) or (
        grade is not None and int(grade) >= REFERABLE_MIN_GRADE)

    return {
        "follow_up_id": "fu_" + uuid.uuid4().hex[:16],
        "account_id": screening.get("account_id"),
        "screening_id": screening.get("screening_id"),
        "created_at": now_iso(),
        # --- the window ------------------------------------------------------
        "recommended_window": {
            "min_months": lo,
            "max_months": hi,
            "label": _months_label(lo, hi),
            "priority": priority,
            "headline": WINDOW_COPY[priority],
        },
        "due_at": _due_at(screening.get("created_at"), hi),
        # --- where it came from ----------------------------------------------
        "basis": basis,
        "basis_label": BASIS_LABELS[basis],
        "basis_note": ("Guideline-informed suggestion from this programme's configured "
                       "follow-up table. It is not a prescription, and a clinician's "
                       "recommendation takes precedence over it."),
        "reason": reason,
        "clinician_override": basis in ("clinician_override", "clinician_grade"),
        # --- state -----------------------------------------------------------
        "status": "scheduled",
        "reminder_status": "pending",
        "channel": channel,
        "priority": priority,
        "referral_indicated": referral,
        # Severe/proliferative and refused images are not "come back in N months" cases.
        "specialist_referral": priority in ("prompt", "urgent"),
    }


def _reason(grade: int | None, gradeable: bool | None, escalated: bool, basis: str) -> str:
    if gradeable is False:
        return ("The photograph could not be graded, so a repeat photograph is suggested "
                "rather than a screening interval.")
    if grade is None:
        return ("No grade was produced for this screening, so the routine screening "
                "interval is suggested.")
    g = int(grade)
    if g >= URGENT_MIN_GRADE:
        return ("This screening result indicates referral, so prompt assessment by an eye "
                "specialist is suggested rather than a long-term reminder.")
    base = f"Suggested from the configured follow-up window for ICDR grade {g}."
    if escalated:
        return (base + " The window has been brought forward because this screening "
                       "result is in a higher ICDR category than the previous one.")
    if basis == "clinician_grade":
        return f"Suggested from the configured follow-up window for the clinician's grade {g}."
    return base


def mark_due(follow_up: dict, *, at_iso: str | None = None) -> bool:
    """Whether this plan's target date has arrived. Pure; the caller writes the status."""
    due = parse_iso(follow_up.get("due_at"))
    now = parse_iso(at_iso) if at_iso else parse_iso(now_iso())
    if due is None or now is None:
        return False
    return now >= due


__all__ = ["plan", "window_for_grade", "mark_due", "GUIDELINE_WINDOWS", "WINDOW_COPY",
           "BASIS_LABELS", "PRIORITIES", "RECAPTURE_WINDOW"]
