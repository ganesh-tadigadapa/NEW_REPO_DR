"""Compare two screening results for the same patient.

READ THIS BEFORE EDITING, because the temptation in this file is to say more than the
data supports.

What this module does: it subtracts two ICDR grades that the model already decided and
NAMES the difference. That is all. There is no model here, no threshold, no probability,
no trend fit and no risk score.

What it must never say: that disease has progressed, worsened, improved or been cured.
Two screening results differing by one ICDR category is a fact about two screening
results. Between them sit a different day, a different camera, a different pupil, a
different photographer and a model with its own error rate. So every sentence this
module produces is phrased about the SCREENING RESULT:

    "The current screening result is one ICDR category higher than the previous
     screening."

and never about the eye. `statement()` is the only place these words are written, and
`tests/test_passport_longitudinal.py` asserts that no forbidden claim appears in them.

ICDR grade is an ORDINAL CATEGORY (0-4), not a measurement. A difference of one category
between grade 0 and 1 is not the same clinical quantity as one between 3 and 4, so
nothing here averages grades, plots a continuous line through them, or computes a rate
of change per month.
"""
from __future__ import annotations

from src.common.config import ICDR_LABELS
from src.passport.store import parse_iso, quality_status

# Ordinal distance -> the words for it. Bounded by the scale: the largest possible move
# on a 0-4 scale is four categories.
_MAGNITUDE = {1: "One", 2: "Two", 3: "Three", 4: "Four"}

# The sentence that may be said about each direction. Nothing outside this dict is ever
# printed as a change description.
_STATEMENTS = {
    "same": "The current screening result is in the same ICDR category as the previous screening.",
    "higher": "The current screening result is {magnitude} ICDR {categories} higher than the previous screening.",
    "lower": "The current screening result is {magnitude} ICDR {categories} lower than the previous screening.",
}

# Printed alongside every comparison, in the API, in the PDF and in the WhatsApp message.
NOT_A_DIAGNOSIS = (
    "This compares two screening results. It is not a diagnosis, and it is not by itself "
    "evidence that the disease has changed. Only an eye-care professional can say that."
)


def change_label(grade_change: int) -> str:
    """'+1 ICDR category' as words: 'One ICDR category higher'."""
    if grade_change == 0:
        return "Same ICDR category"
    magnitude = _MAGNITUDE.get(abs(grade_change), str(abs(grade_change)))
    categories = "category" if abs(grade_change) == 1 else "categories"
    direction = "higher" if grade_change > 0 else "lower"
    return f"{magnitude} ICDR {categories} {direction}"


def change_direction(grade_change: int) -> str:
    if grade_change > 0:
        return "higher"
    if grade_change < 0:
        return "lower"
    return "same"


def statement(grade_change: int) -> str:
    """The one sentence a patient reads about the difference. See the module docstring."""
    direction = change_direction(grade_change)
    if direction == "same":
        return _STATEMENTS["same"]
    return _STATEMENTS[direction].format(
        magnitude=_MAGNITUDE.get(abs(grade_change), str(abs(grade_change))).lower(),
        categories="category" if abs(grade_change) == 1 else "categories")


def is_comparable(rec: dict | None) -> bool:
    """A screening can be one half of a comparison only if it was actually graded."""
    return bool(rec and rec.get("gradeable") is True and rec.get("icdr_grade") is not None)


def _side(rec: dict, review: dict | None) -> dict:
    grade = rec.get("icdr_grade")
    return {
        "screening_id": rec.get("screening_id"),
        "date": rec.get("created_at"),
        "icdr_grade": grade,
        "severity_label": (rec.get("severity_label")
                           or (ICDR_LABELS.get(grade) if grade is not None else None)),
        "referable": rec.get("referable"),
        "confidence": rec.get("confidence"),
        "quality_status": rec.get("quality_status") or quality_status(rec.get("gradeable")),
        "report_available": bool(rec.get("report_available")),
        # The clinician's recorded opinion on THIS screening, when one exists. A sibling
        # fact, never a replacement for the AI grade above it.
        "clinician_review_status": (review or {}).get("status", "pending"),
        "clinician_grade": (review or {}).get("clinician_grade"),
        "clinician_reviewed_at": (review or {}).get("reviewed_at"),
    }


def _interval_days(previous: dict, current: dict) -> int | None:
    a, b = parse_iso(previous.get("created_at")), parse_iso(current.get("created_at"))
    if a is None or b is None:
        return None
    return max(0, (b - a).days)


def compare(previous: dict | None, current: dict, *,
            previous_review: dict | None = None,
            current_review: dict | None = None) -> dict | None:
    """The comparison object, or None when there is nothing valid to compare.

    None is a real answer and the callers render it as one:
      * the patient's FIRST screening has no previous result, and
      * an UNGRADEABLE current screening produced no result to compare.

    Neither case invents a comparison, and neither is an error.
    """
    if not is_comparable(current):
        return None
    if not is_comparable(previous):
        return None

    prev_grade = int(previous["icdr_grade"])
    curr_grade = int(current["icdr_grade"])
    grade_change = curr_grade - prev_grade

    prev_side = _side(previous, previous_review)
    curr_side = _side(current, current_review)

    return {
        "available": True,
        "previous": prev_side,
        "current": curr_side,
        # --- the comparison itself: one subtraction, named ------------------
        "previous_grade": prev_grade,
        "current_grade": curr_grade,
        "grade_change": grade_change,
        "change_direction": change_direction(grade_change),
        "change_label": change_label(grade_change),
        "statement": statement(grade_change),
        # --- the other things that changed between the two visits -----------
        "quality_change": {
            "previous": prev_side["quality_status"],
            "current": curr_side["quality_status"],
            "changed": prev_side["quality_status"] != curr_side["quality_status"],
        },
        "referral_change": {
            "previous": prev_side["referable"],
            "current": curr_side["referable"],
            # "newly_referable" is the operationally important transition: a patient who
            # was below the referral threshold last time and is above it now.
            "newly_referable": bool(curr_side["referable"]) and not bool(prev_side["referable"]),
            "no_longer_referable": bool(prev_side["referable"]) and not bool(curr_side["referable"]),
        },
        "clinician_review_change": {
            "previous": prev_side["clinician_review_status"],
            "current": curr_side["clinician_review_status"],
        },
        "interval_days": _interval_days(previous, current),
        "disclaimer": NOT_A_DIAGNOSIS,
    }


def unavailable(reason: str) -> dict:
    """The explicit 'no comparison' answer, so a client never has to guess from a null."""
    return {"available": False, "reason": reason, "disclaimer": NOT_A_DIAGNOSIS}


# Reasons, as codes, so the UI can choose its own sentence in the patient's language.
NO_PREVIOUS = "no_previous_screening"
CURRENT_UNGRADEABLE = "current_screening_ungradeable"

__all__ = ["compare", "unavailable", "change_label", "change_direction", "statement",
           "is_comparable", "NOT_A_DIAGNOSIS", "NO_PREVIOUS", "CURRENT_UNGRADEABLE"]
