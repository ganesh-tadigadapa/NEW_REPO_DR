"""Doctor-facing report access. Verified doctors only, and anonymised by construction.

Anonymisation here is a WHITELIST, not a blacklist: `_row()` and `_detail()` build a new
dictionary containing exactly the fields named in them. A field added to the scan record
later — including a patient name, a phone number, or a free-text note containing either —
cannot leak into this API by default, because nothing copies the record wholesale.

`patient_ref` is the field this matters most for. The v1 contract says it is free text
with no PII enforced by us, so in practice it may well contain a name. It is therefore
never returned by any endpoint in this module, and `tests/test_reports_privacy.py`
asserts that against a record that deliberately contains a name and a mobile number.

**ANONYMISED IS NOT THE SAME AS PUBLIC, AND THIS MODULE USED TO CONFUSE THE TWO.**
Every endpoint here once served every scan in the system to any verified doctor. The
records carried no name — but they were still one identifiable person's clinical
results, and "a doctor" is not the same claim as "this patient's doctor". So
authorisation here is now the SAME rule the Eye Health Passport uses: a verified doctor
role, PLUS an active care relationship with the patient who owns that scan.

Ownership is resolved through the passport layer (`_owner_of`), because that is where
`account_id` lives — deliberately never on the medical scan record, so that a screening
result does not depend on who uploaded the image. A scan with no owner at all is not
served to anyone but an administrator: there is no patient to have authorised it.

The relationship is created by the patient sharing a code, by an administrator, or by a
doctor who already has access recording a review. It is destroyed the moment the patient
revokes, and the next request is refused.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.evidence import (REVIEW_STATUSES, ClinicianReviewLedger, EvidenceStore,
                              get_evidence_store, get_review_ledger)
from src.auth.models import Account
from src.auth.security import require_report_access
from src.common.config import ICDR_LABELS

log = logging.getLogger("dr-api.reports")

router = APIRouter(prefix="/v1/reports", tags=["reports"])

# Fields that must never appear in a response from this module, whatever the scan record
# happens to hold. Asserted by the privacy tests.
FORBIDDEN_FIELDS = ("patient_ref", "patient_name", "patient_mobile", "mobile",
                    "name", "contact", "address")


# The scan store is injected so the router can be mounted in tests without the model.
def get_scan_store():                                 # pragma: no cover - overridden
    from src.api.store import get_store
    return get_store()


# ------------------------------------------------------------------ authorisation
def _passport():
    """The longitudinal store, imported lazily.

    Lazy on purpose: this router has to stay mountable on its own (tests/conftest.py
    assembles an app from auth + reports alone) and must not import the passport package
    at module scope.
    """
    from src.passport.store import get_passport_store

    return get_passport_store()


def _owner_of(scan_id: str | None) -> str | None:
    """Which account this scan belongs to, or None if nothing claims it.

    The scan record itself has no owner field, and that is deliberate — see the module
    docstring. Ownership is recorded in the passport layer when the screening is saved.
    """
    if not scan_id:
        return None
    try:
        rec = _passport().get_screening(scan_id)
    except Exception:                                 # noqa: BLE001
        log.exception("ownership lookup failed for %s; treating as unauthorised", scan_id)
        return None
    return (rec or {}).get("account_id") or None


def _may_read(scan_id: str | None, doctor: Account) -> bool:
    """May THIS doctor read THIS scan?

    Fails closed in every uncertain case: an unknown scan, an unowned scan, a lookup
    error and a revoked relationship all answer False.
    """
    if doctor.is_admin:
        # An administrator grants and audits relationships; one who could not see a
        # record could not assign or investigate it either.
        return True
    owner = _owner_of(scan_id)
    if owner is None:
        return False
    try:
        return _passport().has_access(account_id=owner,
                                      doctor_account_id=doctor.account_id)
    except Exception:                                 # noqa: BLE001
        log.exception("access check failed for %s; refusing", scan_id)
        return False


def _authorised_owners(doctor: Account) -> set[str] | None:
    """The patients this doctor may read, or None meaning 'no restriction' (admin)."""
    if doctor.is_admin:
        return None
    try:
        return set(_passport().granted_patients(doctor.account_id))
    except Exception:                                 # noqa: BLE001
        log.exception("granted-patient lookup failed; showing nothing")
        return set()


def _not_found(scan_id: str) -> HTTPException:
    """One answer for 'no such scan' and 'not your patient'.

    Deliberately indistinguishable, exactly as the passport layer does it: a different
    status for the second case would confirm that a scan id exists for somebody else.
    """
    return HTTPException(404, detail={"error": {
        "code": "unknown_scan",
        "message": "That report is not available for your account."}})


def _quality_status(row: dict) -> str:
    if row.get("gradeable") is True:
        return "pass"
    if row.get("gradeable") is False:
        return "refused"
    return "unknown"


def _row(rec: dict, review: dict | None) -> dict:
    """One anonymised line for the doctor's report table.

    Built field by field. There is no `**rec` anywhere in this function, and there must
    not be.
    """
    grade = rec.get("icdr_grade")
    return {
        # The scan id IS the identifier. It is generated by the pipeline from a random
        # UUID and has no relationship to any patient identity.
        "scan_id": rec.get("scan_id"),
        "created_at": rec.get("created_at"),

        # --- what the AI said (never modified by a review) ------------------
        "ai_grade": grade,
        "ai_label": ICDR_LABELS.get(grade) if grade is not None else None,
        "referable": rec.get("referable"),
        "confidence": rec.get("confidence"),

        # --- independent evidence -------------------------------------------
        "rule_grade": rec.get("rule_grade"),
        "rule_flag": rec.get("rule_flag"),
        "escalated": bool(rec.get("rule_flag")),

        # --- image quality ---------------------------------------------------
        "quality_status": _quality_status(rec),
        "quality_score": rec.get("quality_score"),
        "recapture_instruction": rec.get("recapture_instruction"),

        # --- explanation availability ---------------------------------------
        "explanation_available": _evidence_available(rec.get("scan_id")),

        # --- review state (two separate things) ------------------------------
        # screening_review: the fast in-session sign-off from /review
        "screening_reviewed": bool(rec.get("review")),
        # clinician_review: the doctor's recorded opinion, from the separate ledger
        "review_status": (review or {}).get("status", "pending"),
        "review_status_label": (review or {}).get("status_label", "Pending"),
        "reviewed_at": (review or {}).get("reviewed_at"),
    }


def _evidence_available(scan_id: str | None) -> bool:
    if not scan_id:
        return False
    return get_evidence_store().load(scan_id) is not None


@router.get("")
def list_reports(
    limit: int = Query(default=100, ge=1, le=500),
    referable: bool | None = None,
    status: str | None = Query(default=None, pattern="^(pending|reviewed|needs_further_review|confirmed|disagreed)$"),
    doctor: Account = Depends(require_report_access),
    store=Depends(get_scan_store),
):
    """The reports of the patients THIS doctor is authorised for. Anonymised.

    Not every report in the system. The filtering happens here, server-side, from the
    care relationships on record — a client cannot widen it, because there is no
    parameter that selects a patient.
    """
    allowed = _authorised_owners(doctor)
    rows = store.list_scans(limit)
    if allowed is not None:
        rows = [r for r in rows if _owner_of(r.get("scan_id")) in allowed]
    latest = get_review_ledger().latest_by_scan()
    out = [_row(r, latest.get(r.get("scan_id"))) for r in rows]
    if referable is not None:
        out = [r for r in out if r["referable"] is referable]
    if status is not None:
        out = [r for r in out if r["review_status"] == status]
    return {
        "reports": out,
        "count": len(out),
        "anonymised": True,
        # What the caller is actually looking at, stated rather than implied.
        "scope": "all" if allowed is None else "authorised_patients",
        "patient_count": None if allowed is None else len(allowed),
        "note": ("Reports are identified by internal scan id only. No patient name, "
                 "mobile number or contact detail is stored in or served from this "
                 "view. Only patients who have shared their record with you appear "
                 "here."),
    }


def _detail(rec: dict, evidence: dict | None, history: list[dict]) -> dict:
    """The full evidence for one scan, still anonymised.

    Note the shape: `ai`, `rule_engine`, `screening_recommendation` and
    `clinician_review` are four sibling keys. A clinician review adds to this document;
    it never edits `ai`.
    """
    ev = evidence or {}
    grading = ev.get("grading") or {}
    rule = ev.get("rule_check") or {}
    quality = ev.get("quality") or {}
    explain = ev.get("explain") or {}
    grade = grading.get("icdr_grade", rec.get("icdr_grade"))
    latest = history[-1] if history else None

    return {
        "scan_id": rec.get("scan_id"),
        "created_at": rec.get("created_at"),
        "model_id": rec.get("model_id"),
        "synthetic_demo_model": ev.get("synthetic_demo_model"),
        "disclaimer": ev.get("disclaimer"),
        "evidence_available": evidence is not None,
        "timing_ms": rec.get("timing_ms"),

        # ---------------------------------------------------------------- 1. AI
        "ai": {
            "icdr_grade": grade,
            "icdr_label": ICDR_LABELS.get(grade) if grade is not None else None,
            "referable": grading.get("referable", rec.get("referable")),
            "confidence": grading.get("confidence", rec.get("confidence")),
            "confidence_calibrated": grading.get("confidence_calibrated"),
            "per_grade_probability": grading.get("per_grade_probability"),
            "ordinal_score": grading.get("ordinal_score"),
            "threshold_set": grading.get("threshold_set"),
            "unavailable_reason": ev.get("grading_unavailable_reason"),
        },

        # ------------------------------------------------- 2. clinical evidence
        "quality": {
            "gradeable": quality.get("gradeable", rec.get("gradeable")),
            "overall_score": quality.get("overall_score", rec.get("quality_score")),
            "checks": quality.get("checks"),
            "enhanced": quality.get("enhanced"),
            "recapture_instruction": quality.get("recapture_instruction"),
        },
        "lesions": ev.get("lesions", rec.get("lesions")),
        "explain": {
            "gradcam_available": explain.get("gradcam_available", False),
            "gradcam_unavailable_reason": explain.get("gradcam_unavailable_reason"),
            "attention_summary": explain.get("attention_summary"),
            "overlay_png_b64": explain.get("overlay_png_b64"),
            "gradcam_png_b64": explain.get("gradcam_png_b64"),
            "lesion_overlay_png_b64": explain.get("lesion_overlay_png_b64"),
        },

        # --------------------------------------------- 3. rule-engine opinion
        "rule_engine": {
            "rule_grade": rule.get("rule_grade", rec.get("rule_grade")),
            "rule_label": rule.get("rule_label"),
            "rule_referable": rule.get("rule_referable"),
            "criteria_fired": rule.get("criteria_fired"),
            "four_two_one": rule.get("four_two_one"),
            "agrees_with_cnn": rule.get("agrees_with_cnn"),
            "referable_agrees": rule.get("referable_agrees"),
            "flag": rule.get("flag", rec.get("rule_flag")),
            "flag_message": rule.get("flag_message"),
            "limitations": rule.get("limitations"),
        },

        # ------------------------------- 4. final screening recommendation
        "screening_recommendation": {
            "referral": grading.get("referable", rec.get("referable")),
            "recommendation": rule.get("recommendation"),
            "escalated": bool(rule.get("flag", rec.get("rule_flag"))),
            "escalation_reason": rule.get("flag_message"),
        },

        # ------------------------------------------------ 5. clinician review
        # Separate field, separate store, full history. Adding one of these does not
        # change anything above it.
        "clinician_review": {
            "status": (latest or {}).get("status", "pending"),
            "status_label": (latest or {}).get("status_label", "Pending"),
            "clinician_grade": (latest or {}).get("clinician_grade"),
            "notes": (latest or {}).get("notes"),
            "reviewed_at": (latest or {}).get("reviewed_at"),
        },
        "clinician_review_history": history,
    }


@router.get("/{scan_id}")
def get_report(scan_id: str,
               doctor: Account = Depends(require_report_access),
               store=Depends(get_scan_store)):
    """One report, for a doctor with an active care relationship with its owner."""
    rec = next((r for r in store.list_scans(500) if r.get("scan_id") == scan_id), None)
    # Authorisation before existence, and the same answer either way.
    if rec is None or not _may_read(scan_id, doctor):
        raise _not_found(scan_id)
    evidence = get_evidence_store().load(scan_id)
    history = get_review_ledger().history(scan_id)
    return _detail(rec, evidence, history)


class ClinicianReviewIn(BaseModel):
    status: str = Field(pattern="^(reviewed|needs_further_review|confirmed|disagreed)$")
    notes: str = Field(default="", max_length=2000)
    # Optional. Recorded alongside — never instead of — the AI grade.
    clinician_grade: int | None = Field(default=None, ge=0, le=4)


@router.post("/{scan_id}/review")
def review_report(scan_id: str, body: ClinicianReviewIn,
                  doctor: Account = Depends(require_report_access),
                  store=Depends(get_scan_store)):
    """Record a clinician review.

    This writes ONE new row to the review ledger. It does not touch the scan record, so
    the AI grade, the rule-engine grade and the referral decision are exactly what they
    were before this call — which is the property `tests/test_doctor_review.py` pins.

    Requires an active care relationship with the scan's owner. Reviewing used to be
    the act that CREATED that relationship, which meant any verified doctor could
    self-grant access to any patient by reviewing one of their scans. It now requires
    the relationship to exist first.
    """
    rec = next((r for r in store.list_scans(500) if r.get("scan_id") == scan_id), None)
    if rec is None or not _may_read(scan_id, doctor):
        raise _not_found(scan_id)

    entry = get_review_ledger().record(
        scan_id, status=body.status, reviewer_account_id=doctor.account_id,
        notes=body.notes, clinician_grade=body.clinician_grade,
    )
    # Two consequences in the LONGITUDINAL layer, both best effort and neither able to
    # touch anything above. The grant is now a RE-AFFIRMATION rather than the thing that
    # creates access — reaching this line already required an active relationship — and
    # it is kept because an administrator may review without one. A clinician grade is
    # the better input to the follow-up window than the model's, so the plan is
    # recomputed from it. Neither changes the scan record, the AI grade or the referral.
    _passport_after_review(scan_id, doctor.account_id)
    return {
        "ok": True,
        "scan_id": scan_id,
        "clinician_review": entry,
        # Echoed back so a caller can see for itself that the AI result is unchanged.
        "ai_grade_unchanged": rec.get("icdr_grade"),
        "ai_referable_unchanged": rec.get("referable"),
    }


def _passport_after_review(scan_id: str, doctor_account_id: str) -> None:
    """Grant longitudinal access and re-plan the follow-up. Failures are swallowed.

    Imported inside the function on purpose: the reports router must remain mountable on
    its own (tests/conftest.py assembles an app from auth + reports alone), and a review
    must still be recorded if the passport layer is unavailable for any reason.
    """
    try:
        from src.passport import service as passport_service

        grant = passport_service.grant_from_review(scan_id, doctor_account_id)
        if grant:
            passport_service.recompute_follow_up(grant["account_id"], scan_id)
    except Exception:                                 # noqa: BLE001
        log.exception("passport update after review failed for %s "
                      "(the review itself is recorded and unaffected)", scan_id)


__all__ = ["router", "get_scan_store", "REVIEW_STATUSES", "FORBIDDEN_FIELDS"]
