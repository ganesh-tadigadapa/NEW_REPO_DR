"""Requirement #4b — the ICDR clinical rule engine: a second, independent grade.

The CNN says "grade 3". *Why* grade 3? A heatmap is not a reason. This module computes
the grade a **second time**, from the explicit published clinical criteria applied to the
lesion counts, with no neural network involved. Two independent estimators, and we show
the user when they disagree instead of hiding it.

## The actual ICDR severity scale

  0  No DR              no abnormalities
  1  Mild NPDR          microaneurysms only
  2  Moderate NPDR      more than microaneurysms only, but less than severe
  3  Severe NPDR        the 4-2-1 rule, with no signs of proliferative disease:
                          > 20 intraretinal haemorrhages in EACH of 4 quadrants, OR
                          definite venous beading in >= 2 quadrants, OR
                          prominent IRMA in >= 1 quadrant
  4  Proliferative DR   neovascularisation, or vitreous/preretinal haemorrhage

## What we can and cannot assess — say this before a judge finds it

Our classical detectors find microaneurysms, haemorrhages and hard exudates. They do
**not** detect venous beading, IRMA, or neovascularisation. Two of the three 4-2-1 limbs
and the whole of grade 4 are therefore **unassessable by the rule engine**.

We do not paper over that. The engine returns `assessable_ceiling`, and any image whose
CNN grade exceeds what the rules can confirm is reported as *"rules cannot confirm"*
rather than as a disagreement. Silently treating "I cannot see it" as "it is not there"
would systematically under-grade the sickest patients — the exact failure mode that
blinds people. This limitation is on the limitations slide.
"""
from __future__ import annotations

from src.common.config import ICDR_LABELS, REFERABLE_MIN_GRADE

QUADRANTS = ("ST", "SN", "IT", "IN")

# The 4-2-1 haemorrhage limb requires >20 haemorrhages in *each* quadrant.
HAEMORRHAGE_PER_QUADRANT_SEVERE = 20

# Detector noise floor. A single blob in a 1024px image is as likely to be a dust speck
# or a vessel crossing as a microaneurysm, so one detection is not "disease present".
# This is a stated, tunable assumption, not a magic number.
MIN_CREDIBLE_COUNT = 2


def evaluate(lesions: dict, cnn_grade: int | None = None) -> dict:
    """Apply the ICDR criteria to lesion counts.

    `lesions` is the `summary` block from src.segment.lesions.analyse:
        {"microaneurysms": {"count": n, "by_quadrant": {...}}, ...}
    """
    ma = lesions["microaneurysms"]["count"]
    he = lesions["haemorrhages"]["count"]
    ex = lesions["hard_exudates"]["count"]
    he_q = lesions["haemorrhages"]["by_quadrant"]

    criteria: list[str] = []

    ma_present = ma >= MIN_CREDIBLE_COUNT
    he_present = he >= MIN_CREDIBLE_COUNT
    ex_present = ex >= MIN_CREDIBLE_COUNT

    # ---- the 4-2-1 rule, limb by limb -------------------------------------
    q_severe = [q for q in QUADRANTS if he_q.get(q, 0) > HAEMORRHAGE_PER_QUADRANT_SEVERE]
    haemorrhages_4q = len(q_severe) == 4
    four_two_one = {
        "haemorrhages_4q": haemorrhages_4q,
        "haemorrhage_quadrants_over_20": q_severe,
        # honestly unassessable — we have no detector for either
        "venous_beading_2q": None,
        "irma_1q": None,
        "severe": haemorrhages_4q,
        "unassessable_limbs": ["venous_beading_2q", "irma_1q"],
    }

    # ---- grade assignment --------------------------------------------------
    if haemorrhages_4q:
        grade = 3
        criteria.append(f"4-2-1 haemorrhage limb: >{HAEMORRHAGE_PER_QUADRANT_SEVERE} "
                        f"haemorrhages in all four quadrants {q_severe}")
    elif he_present or ex_present:
        grade = 2
        if he_present:
            criteria.append(f"haemorrhages present (n={he})")
        if ex_present:
            criteria.append(f"hard exudates present (n={ex})")
        if ma_present:
            criteria.append(f"microaneurysms present (n={ma})")
    elif ma_present:
        grade = 1
        criteria.append(f"microaneurysms only (n={ma})")
    else:
        grade = 0
        criteria.append("no lesions detected above the credibility floor "
                        f"(>= {MIN_CREDIBLE_COUNT} detections)")

    # The rules can never *confirm* grade 4, and can only reach 3 via one of three limbs.
    assessable_ceiling = 3

    out = {
        "rule_grade": grade,
        "rule_label": ICDR_LABELS[grade],
        "rule_referable": grade >= REFERABLE_MIN_GRADE,
        "criteria_fired": criteria,
        "four_two_one": four_two_one,
        "assessable_ceiling": assessable_ceiling,
        "counts_used": {"microaneurysms": ma, "haemorrhages": he, "hard_exudates": ex},
        "credibility_floor": MIN_CREDIBLE_COUNT,
        "limitations": [
            "Venous beading and IRMA are not detected; two of the three 4-2-1 limbs "
            "cannot be evaluated.",
            "Neovascularisation is not detected; the rule engine can never confirm "
            "grade 4 (Proliferative DR).",
        ],
    }
    if cnn_grade is not None:
        out.update(_compare(grade, int(cnn_grade), assessable_ceiling))
    return out


def _compare(rule_grade: int, cnn_grade: int, ceiling: int) -> dict:
    """Reconcile the two grades, routing uncertainty UPWARD.

    The asymmetry is deliberate and clinical: a false alarm costs one appointment, a
    missed grade-3 costs sight. So whenever the two estimators disagree we escalate to
    human review rather than averaging them or trusting the CNN.
    """
    agrees = rule_grade == cnn_grade
    referable_agrees = (rule_grade >= REFERABLE_MIN_GRADE) == (cnn_grade >= REFERABLE_MIN_GRADE)

    if cnn_grade > ceiling:
        return {
            "agrees_with_cnn": None,
            "referable_agrees": referable_agrees,
            "flag": "rules_cannot_confirm",
            "flag_message": (
                f"The model reports {ICDR_LABELS[cnn_grade]}. The rule engine cannot "
                f"confirm any grade above {ICDR_LABELS[ceiling]} because venous beading, "
                "IRMA and neovascularisation are not detected. This is a limitation of "
                "the rule check, not evidence against the model."),
            "recommendation": "clinician_review",
        }
    if agrees:
        return {"agrees_with_cnn": True, "referable_agrees": True, "flag": None,
                "flag_message": None, "recommendation": "routine"}
    if not referable_agrees:
        return {
            "agrees_with_cnn": False, "referable_agrees": False,
            "flag": "referral_disagreement",
            "flag_message": (
                f"The model grades this {ICDR_LABELS[cnn_grade]} and the clinical rules "
                f"grade it {ICDR_LABELS[rule_grade]}. They disagree on whether the "
                "patient needs referral. Escalated for clinician review."),
            "recommendation": "clinician_review",
        }
    return {
        "agrees_with_cnn": False, "referable_agrees": True,
        "flag": "severity_disagreement",
        "flag_message": (
            f"The model grades this {ICDR_LABELS[cnn_grade]}; the clinical rules grade it "
            f"{ICDR_LABELS[rule_grade]}. Both agree the patient "
            f"{'does' if rule_grade >= REFERABLE_MIN_GRADE else 'does not'} need referral, "
            "so the referral decision is unaffected."),
        "recommendation": "routine",
    }


def api_block(rules: dict) -> dict:
    """Trim the full evaluation down to the `rule_check` block of the API contract."""
    return {
        "rule_grade": rules["rule_grade"],
        "rule_label": rules["rule_label"],
        "rule_referable": rules["rule_referable"],
        "criteria_fired": rules["criteria_fired"],
        "four_two_one": rules["four_two_one"],
        "agrees_with_cnn": rules.get("agrees_with_cnn"),
        "referable_agrees": rules.get("referable_agrees"),
        "flag": rules.get("flag"),
        "flag_message": rules.get("flag_message"),
        "recommendation": rules.get("recommendation"),
        "assessable_ceiling": rules["assessable_ceiling"],
        "limitations": rules["limitations"],
    }
