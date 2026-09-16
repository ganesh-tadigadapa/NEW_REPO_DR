"""CareBridge Eye Health Passport — the loop, tested end to end without a model.

The acceptance scenario from the brief runs here as one test
(`test_the_whole_acceptance_flow`): Patient A is screened at grade 1, a follow-up is
created, they return later, the second image grades 2, the previous grade 1 is found, a
comparison is produced saying +1 ICDR category, the timeline grows, a comparison PDF is
generated, and the next follow-up plan is computed from the current result.

Three properties this file pins, because they are what makes the feature safe:

  * **No clinical claim is invented.** `test_no_comparison_ever_claims_the_disease_changed`
    asserts the forbidden vocabulary appears nowhere in any comparison the module can
    produce, for every pair of grades on the scale.
  * **An ungradeable screening is not half of a comparison.** It is a real visit on the
    timeline, and it is never a result.
  * **A clinician outranks the table.** Both kinds of override are tested.

Nothing here loads TensorFlow, reads an image or sends a message.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.passport import comparison as cmp_mod
from src.passport import followup as fu_mod
from src.passport import service as passport_service
from src.passport.routes import router as passport_router
from src.passport.store import screening_record
from tests.conftest import auth_header, signup

PATIENT = "+919812350001"
OTHER = "+919812350002"

# Sentences a screening comparison is not entitled to say, whatever the grades were.
FORBIDDEN_CLAIMS = [
    "worsened", "worse", "progressed", "progression", "improved", "deteriorated",
    "getting worse", "disease has", "definitely",
]


def analyze_result(scan_id: str, *, grade: int | None = 1, created_at: str,
                   gradeable: bool = True, referable: bool | None = None,
                   confidence: float = 0.8, with_report: bool = True) -> dict:
    """The shape `/v1/analyze` returns, trimmed to what the passport layer reads."""
    labels = {0: "No DR", 1: "Mild NPDR", 2: "Moderate NPDR", 3: "Severe NPDR",
              4: "Proliferative DR"}
    grading = None if grade is None else {
        "icdr_grade": grade, "icdr_label": labels[grade],
        "referable": (grade >= 2) if referable is None else referable,
        "confidence": confidence,
    }
    return {
        "scan_id": scan_id,
        "created_at": created_at,
        # Deliberately present: the passport row must NOT copy it.
        "patient_ref": "Lakshmi Narayanan +919812345678",
        "quality": {"gradeable": gradeable, "overall_score": 0.88},
        "grading": grading,
        "report": ({"pdf_b64": "eA==", "filename": f"dr-report-{scan_id}.pdf"}
                   if with_report else None),
    }


@pytest.fixture
def api(auth_store, evidence, passport):
    """The passport router on its own. It stands up with no medical pipeline at all,
    which is the architectural point the access layers already make."""
    from src.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(passport_router)
    with TestClient(app) as c:
        c.passport = passport
        yield c


def screen(passport, account_id: str, scan_id: str, *, grade, created_at,
           gradeable: bool = True):
    """Run one screening through the passport layer, as `/v1/analyze` does."""
    return passport_service.record_screening(
        analyze_result(scan_id, grade=grade, created_at=created_at, gradeable=gradeable),
        account_id)


# ===================================================== 1-3. save and retrieve
def test_the_first_screening_is_saved(passport):
    out = screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    assert out["recorded"] is True
    assert out["returning_patient"] is False
    history = passport.history("acc_a")
    assert [r["screening_id"] for r in history] == ["sc_1"]
    assert history[0]["icdr_grade"] == 1
    assert history[0]["severity_label"] == "Mild NPDR"
    assert history[0]["quality_status"] == "pass"


def test_the_second_screening_is_saved_against_the_same_account(passport):
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    out = screen(passport, "acc_a", "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")
    assert out["returning_patient"] is True
    assert out["history_count"] == 2
    assert [r["screening_id"] for r in passport.history("acc_a")] == ["sc_1", "sc_2"]


def test_the_previous_screening_is_retrieved(passport):
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    screen(passport, "acc_a", "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")
    previous = passport.previous_valid("acc_a", "sc_2")
    assert previous["screening_id"] == "sc_1"
    assert previous["icdr_grade"] == 1


def test_a_screening_row_never_copies_the_patient_reference(passport):
    """`patient_ref` is free text that may hold a name. It is not a field of the row."""
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    row = passport.history("acc_a")[0]
    assert "patient_ref" not in row
    assert "Lakshmi" not in str(row)
    assert "+919812345678" not in str(row)


# ================================================== 4-8. the comparison itself
def test_a_comparison_is_generated(passport):
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    out = screen(passport, "acc_a", "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")
    c = out["comparison"]
    assert c["available"] is True
    assert (c["previous_grade"], c["current_grade"], c["grade_change"]) == (1, 2, 1)
    assert c["change_label"] == "One ICDR category higher"
    assert c["statement"] == ("The current screening result is one ICDR category higher "
                              "than the previous screening.")
    assert c["previous"]["severity_label"] == "Mild NPDR"
    assert c["current"]["severity_label"] == "Moderate NPDR"
    assert c["interval_days"] == 181


def test_an_unchanged_grade_says_so(passport):
    screen(passport, "acc_a", "sc_1", grade=2, created_at="2026-09-16T09:00:00Z")
    out = screen(passport, "acc_a", "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")
    c = out["comparison"]
    assert c["grade_change"] == 0
    assert c["change_direction"] == "same"
    assert c["change_label"] == "Same ICDR category"
    assert c["statement"] == ("The current screening result is in the same ICDR category "
                              "as the previous screening.")


def test_a_grade_increase_is_named_as_a_category_change(passport):
    screen(passport, "acc_a", "sc_1", grade=0, created_at="2026-09-16T09:00:00Z")
    out = screen(passport, "acc_a", "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")
    c = out["comparison"]
    assert c["grade_change"] == 2
    assert c["change_label"] == "Two ICDR categories higher"
    assert c["referral_change"]["newly_referable"] is True


def test_a_grade_decrease_is_named_as_a_category_change(passport):
    screen(passport, "acc_a", "sc_1", grade=3, created_at="2026-09-16T09:00:00Z")
    out = screen(passport, "acc_a", "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")
    c = out["comparison"]
    assert c["grade_change"] == -1
    assert c["change_direction"] == "lower"
    assert c["change_label"] == "One ICDR category lower"
    assert "lower than the previous screening" in c["statement"]


def test_multiple_historical_screenings_compare_against_the_immediately_previous_one(passport):
    for i, (grade, when) in enumerate([(0, "2024-01-10T09:00:00Z"),
                                       (1, "2025-01-10T09:00:00Z"),
                                       (1, "2026-01-10T09:00:00Z"),
                                       (3, "2027-01-10T09:00:00Z")], start=1):
        out = screen(passport, "acc_a", f"sc_{i}", grade=grade, created_at=when)
    assert out["comparison"]["previous"]["screening_id"] == "sc_3"
    assert out["comparison"]["previous_grade"] == 1
    assert out["comparison"]["current_grade"] == 3
    assert out["comparison"]["change_label"] == "Two ICDR categories higher"
    assert len(passport.history("acc_a")) == 4


@pytest.mark.parametrize("previous_grade", [0, 1, 2, 3, 4])
@pytest.mark.parametrize("current_grade", [0, 1, 2, 3, 4])
def test_no_comparison_ever_claims_the_disease_changed(previous_grade, current_grade):
    """Every pair on the scale, checked against the forbidden vocabulary.

    This is the test that stops a future edit turning "+1 category" into "your disease
    has worsened". It runs over all 25 combinations rather than the interesting ones,
    because the claim would be just as wrong for any of them.
    """
    previous = {"screening_id": "a", "created_at": "2026-01-01T00:00:00Z",
                "icdr_grade": previous_grade, "gradeable": True, "referable": False}
    current = {"screening_id": "b", "created_at": "2027-01-01T00:00:00Z",
               "icdr_grade": current_grade, "gradeable": True, "referable": False}
    c = cmp_mod.compare(previous, current)
    # The CLAIM-BEARING strings only. The disclaimer is checked separately below,
    # because it deliberately contains the negated form ("not ... evidence that the
    # disease has changed") and a naive substring check would flag its own denial.
    prose = " ".join([c["statement"], c["change_label"]]).lower()
    for claim in FORBIDDEN_CLAIMS:
        assert claim not in prose, f"a comparison said {claim!r}: {prose}"
    # It talks about the screening RESULT, never about the eye.
    assert "screening result" in c["statement"]
    assert "your eye" not in prose and "your disease" not in prose
    # And the caveat travels with every comparison, in the negative.
    assert c["disclaimer"] == cmp_mod.NOT_A_DIAGNOSIS
    assert "not a diagnosis" in c["disclaimer"].lower()


def test_the_timeline_is_ordered_oldest_first_whatever_order_things_arrived_in(passport):
    """Rows are appended in arrival order; the timeline is ordered by screening time."""
    screen(passport, "acc_a", "sc_late", grade=2, created_at="2027-03-16T09:00:00Z")
    screen(passport, "acc_a", "sc_early", grade=1, created_at="2026-09-16T09:00:00Z")
    points = passport_service.timeline("acc_a")
    assert [p["screening_id"] for p in points] == ["sc_early", "sc_late"]
    assert [p["date"] for p in points] == sorted(p["date"] for p in points)
    assert [p["icdr_grade"] for p in points] == [1, 2]


# ================================================= 18-19. the absent cases
def test_a_first_screening_has_no_comparison_and_that_is_not_an_error(passport):
    out = screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    assert out["comparison"]["available"] is False
    assert out["comparison"]["reason"] == cmp_mod.NO_PREVIOUS
    # A follow-up is still planned: a first result is exactly when one is needed.
    assert out["follow_up"]["recommended_window"]["min_months"] == 12


def test_an_ungradeable_screening_creates_no_longitudinal_comparison(passport):
    """Requirement 19, and the reason for it: there is no result to compare."""
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    out = screen(passport, "acc_a", "sc_bad", grade=None,
                 created_at="2027-03-16T09:00:00Z", gradeable=False)
    assert out["comparison"]["available"] is False
    assert out["comparison"]["reason"] == cmp_mod.CURRENT_UNGRADEABLE
    # It IS on the timeline — the visit happened — and it is marked as refused.
    points = passport_service.timeline("acc_a")
    assert [p["quality_status"] for p in points] == ["pass", "refused"]
    # And it asks for a repeat photograph rather than a screening interval.
    assert out["follow_up"]["basis"] == "quality_recapture"


def test_an_ungradeable_screening_is_skipped_when_the_next_one_is_compared(passport):
    """The refused visit does not become the 'previous result' for the visit after it."""
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    screen(passport, "acc_a", "sc_bad", grade=None, created_at="2026-10-16T09:00:00Z",
           gradeable=False)
    out = screen(passport, "acc_a", "sc_3", grade=2, created_at="2027-03-16T09:00:00Z")
    assert out["comparison"]["previous"]["screening_id"] == "sc_1"
    assert out["comparison"]["grade_change"] == 1


# ================================================ 10-12. follow-up and override
def test_a_follow_up_is_created_against_the_screening(passport):
    out = screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    plan = out["follow_up"]
    assert plan["screening_id"] == "sc_1"
    assert plan["account_id"] == "acc_a"
    assert plan["status"] == "scheduled"
    assert plan["reminder_status"] == "pending"
    assert plan["channel"] == "whatsapp"
    assert plan["clinician_override"] is False
    assert plan["due_at"].startswith("2027-09")
    assert passport.active_follow_up("acc_a")["follow_up_id"] == plan["follow_up_id"]


def test_the_follow_up_is_updated_by_the_next_screening_and_the_old_one_is_closed(passport):
    first = screen(passport, "acc_a", "sc_1", grade=1,
                   created_at="2026-09-16T09:00:00Z")["follow_up"]
    second = screen(passport, "acc_a", "sc_2", grade=2,
                    created_at="2027-03-16T09:00:00Z")["follow_up"]

    assert second["follow_up_id"] != first["follow_up_id"]
    assert second["screening_id"] == "sc_2"
    # The plan that brought them back is COMPLETED, not superseded: a screening happened.
    assert passport.get_follow_up(first["follow_up_id"])["status"] == "completed"
    assert (passport.get_follow_up(first["follow_up_id"])["completed_by_screening_id"]
            == "sc_2")
    assert passport.active_follow_up("acc_a")["follow_up_id"] == second["follow_up_id"]
    # And the window was brought forward because the category went up.
    assert second["basis"] == "guideline_escalated"
    assert second["recommended_window"]["max_months"] == 3


def test_the_follow_up_is_not_one_universal_interval(passport):
    """Requirement 9: different results get different windows."""
    windows = {}
    for grade in range(5):
        out = screen(passport, f"acc_{grade}", f"sc_{grade}", grade=grade,
                     created_at="2026-09-16T09:00:00Z")
        w = out["follow_up"]["recommended_window"]
        windows[grade] = (w["min_months"], w["max_months"], w["priority"])
    assert len(set(windows.values())) == len(windows), windows
    # Severe and proliferative are handled as referrals, not as long-term reminders.
    assert windows[3][2] == "prompt"
    assert windows[4][2] == "urgent"
    assert windows[0][1] > windows[2][1] > windows[3][1]


def test_a_clinician_follow_up_overrides_the_guideline_window(passport):
    """Override kind 1: an explicit recommendation wins outright."""
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    assert passport.active_follow_up("acc_a")["recommended_window"]["max_months"] == 12

    plan = passport_service.set_clinician_follow_up(
        account_id="acc_a", screening_id="sc_1", months=2,
        reason="Media opacity noted; reviewing sooner.", priority="soon",
        clinician_account_id="acc_doctor")
    assert plan["basis"] == "clinician_override"
    assert plan["clinician_override"] is True
    assert plan["recommended_window"]["max_months"] == 2
    assert plan["set_by"] == "acc_doctor"
    assert passport.active_follow_up("acc_a")["follow_up_id"] == plan["follow_up_id"]
    # The screening record itself is untouched: the AI grade is exactly what it was.
    assert passport.get_screening("sc_1")["icdr_grade"] == 1


def test_a_clinician_grade_replaces_the_model_grade_in_the_window(evidence, passport):
    """Override kind 2: the doctor's own grade is the better input to the table."""
    _ev, ledger = evidence
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    assert passport.active_follow_up("acc_a")["recommended_window"]["max_months"] == 12

    ledger.record("sc_1", status="disagreed", reviewer_account_id="acc_doctor",
                  notes="More haemorrhages than the model counted.", clinician_grade=3)
    plan = passport_service.recompute_follow_up("acc_a", "sc_1")

    assert plan["basis"] == "clinician_grade"
    assert plan["recommended_window"]["priority"] == "prompt"
    assert plan["clinician_override"] is True
    # The AI grade on the record is unchanged — the review added a fact, it did not
    # rewrite one.
    assert passport.get_screening("sc_1")["icdr_grade"] == 1


def test_an_explicit_clinician_follow_up_is_not_recomputed_away(evidence, passport):
    _ev, ledger = evidence
    screen(passport, "acc_a", "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    passport_service.set_clinician_follow_up(
        account_id="acc_a", screening_id="sc_1", months=2, reason="",
        priority="soon", clinician_account_id="acc_doctor")
    ledger.record("sc_1", status="confirmed", reviewer_account_id="acc_doctor",
                  clinician_grade=0)
    assert passport_service.recompute_follow_up("acc_a", "sc_1") is None
    assert passport.active_follow_up("acc_a")["basis"] == "clinician_override"


def test_a_due_follow_up_is_marked_due(passport):
    screen(passport, "acc_a", "sc_1", grade=4, created_at="2020-01-01T09:00:00Z")
    due = passport_service.due_follow_ups("acc_a")
    assert len(due) == 1
    assert due[0]["status"] == "due"


# ============================================================ the HTTP surface
def test_a_patient_reads_their_own_passport_over_http(api, passport):
    token = signup(api, PATIENT)["token"]
    me = api.get("/v1/auth/me", headers=auth_header(token)).json()
    account_id = me["account"]["account_id"]

    screen(passport, account_id, "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")
    screen(passport, account_id, "sc_2", grade=2, created_at="2027-03-16T09:00:00Z")

    r = api.get("/v1/passport", headers=auth_header(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["history_count"] == 2
    assert [p["icdr_grade"] for p in body["timeline"]] == [1, 2]
    assert body["latest_comparison"]["change_label"] == "One ICDR category higher"
    assert body["follow_up"]["screening_id"] == "sc_2"

    status = api.get("/v1/passport/status", headers=auth_header(token)).json()
    assert status["has_history"] is True
    assert status["last_screening"]["screening_id"] == "sc_2"


def test_the_passport_requires_a_session(api):
    assert api.get("/v1/passport").status_code == 401
    assert api.get("/v1/passport/status").status_code == 401
    assert api.get("/v1/passport/screenings/sc_1/comparison").status_code == 401


def test_a_comparison_endpoint_answers_available_false_for_a_first_screening(api, passport):
    token = signup(api, PATIENT)["token"]
    account_id = api.get("/v1/auth/me", headers=auth_header(token)).json()["account"]["account_id"]
    screen(passport, account_id, "sc_1", grade=1, created_at="2026-09-16T09:00:00Z")

    r = api.get("/v1/passport/screenings/sc_1/comparison", headers=auth_header(token))
    assert r.status_code == 200
    assert r.json() == {"available": False, "reason": cmp_mod.NO_PREVIOUS,
                        "disclaimer": cmp_mod.NOT_A_DIAGNOSIS}


# =================================================== the acceptance scenario
def test_the_whole_acceptance_flow(api, passport):
    """Patient A: grade 1, follow-up, returns, grade 2, +1 category, PDF, next plan."""
    token = signup(api, PATIENT)["token"]
    account_id = api.get("/v1/auth/me", headers=auth_header(token)).json()["account"]["account_id"]

    # --- first visit ------------------------------------------------------
    first = screen(passport, account_id, "sc_a1", grade=1,
                   created_at="2026-09-16T09:00:00Z")
    assert first["screening"]["icdr_grade"] == 1
    assert first["comparison"]["available"] is False           # nothing to compare yet
    first_plan = first["follow_up"]
    assert first_plan["status"] == "scheduled"

    # --- the patient returns and is screened again ------------------------
    second = screen(passport, account_id, "sc_a2", grade=2,
                    created_at="2027-03-16T09:00:00Z")
    assert second["returning_patient"] is True
    assert second["previous_follow_ups_completed"] == 1        # the RETURN step

    # --- the system finds the previous grade 1 and compares ---------------
    c = second["comparison"]
    assert (c["previous_grade"], c["current_grade"]) == (1, 2)
    assert c["grade_change"] == 1
    assert c["change_label"] == "One ICDR category higher"

    # --- the timeline grew -------------------------------------------------
    body = api.get("/v1/passport", headers=auth_header(token)).json()
    assert [p["icdr_grade"] for p in body["timeline"]] == [1, 2]

    # --- the comparison PDF is generated ----------------------------------
    pdf = api.get("/v1/passport/screenings/sc_a2/comparison.pdf",
                  headers=auth_header(token))
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF")
    assert "attachment" in pdf.headers["content-disposition"]

    # --- the next follow-up plan comes from the CURRENT result ------------
    plan = second["follow_up"]
    assert plan["screening_id"] == "sc_a2"
    assert plan["follow_up_id"] != first_plan["follow_up_id"]
    assert plan["recommended_window"]["priority"] == "prompt"
    assert plan["referral_indicated"] is True
    assert passport.get_follow_up(first_plan["follow_up_id"])["status"] == "completed"


# =============================================== the module boundaries
def test_the_passport_row_is_a_whitelist_not_a_copy_of_the_result():
    """A field added to the analyse response later cannot leak into the record."""
    result = analyze_result("sc_1", grade=2, created_at="2026-09-16T09:00:00Z")
    result["a_new_field_someone_added"] = "should not appear"
    result["lesions"] = {"microaneurysms": {"count": 14}}
    row = screening_record(result, account_id="acc_a")
    assert "a_new_field_someone_added" not in row
    assert "lesions" not in row
    assert set(row) == {
        "screening_id", "account_id", "created_at", "icdr_grade", "severity_label",
        "referable", "confidence", "gradeable", "quality_status", "report_available",
        "model_id",
    }


def test_the_guideline_table_is_configuration_not_a_calculation():
    """Retuning a programme's protocol is a dict edit, not a code change."""
    assert set(fu_mod.GUIDELINE_WINDOWS) == {0, 1, 2, 3, 4}
    for grade, (lo, hi, priority) in fu_mod.GUIDELINE_WINDOWS.items():
        assert 0 <= lo <= hi, grade
        assert priority in fu_mod.PRIORITIES, grade
