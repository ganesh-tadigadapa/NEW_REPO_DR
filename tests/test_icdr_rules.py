"""The clinical rule engine. These are published criteria, so the tests are the spec."""
from src.explain.icdr_rules import HAEMORRHAGE_PER_QUADRANT_SEVERE, evaluate


def L(ma=0, he=0, ex=0, he_q=None):
    z = {"ST": 0, "SN": 0, "IT": 0, "IN": 0}
    return {
        "microaneurysms": {"count": ma, "by_quadrant": dict(z)},
        "haemorrhages": {"count": he, "by_quadrant": he_q or dict(z)},
        "hard_exudates": {"count": ex, "by_quadrant": dict(z)},
    }


def test_no_lesions_is_grade_0():
    assert evaluate(L())["rule_grade"] == 0


def test_microaneurysms_only_is_grade_1():
    r = evaluate(L(ma=9))
    assert r["rule_grade"] == 1 and not r["rule_referable"]


def test_haemorrhages_make_it_referable():
    r = evaluate(L(ma=9, he=6))
    assert r["rule_grade"] == 2 and r["rule_referable"]


def test_exudates_alone_are_grade_2():
    assert evaluate(L(ex=7))["rule_grade"] == 2


def test_single_detection_is_below_the_credibility_floor():
    """One blob is as likely to be a dust speck as a lesion."""
    assert evaluate(L(ma=1))["rule_grade"] == 0


def test_four_two_one_needs_all_four_quadrants():
    over = HAEMORRHAGE_PER_QUADRANT_SEVERE + 5
    three = L(he=90, he_q={"ST": over, "SN": over, "IT": over, "IN": 3})
    four = L(he=120, he_q={"ST": over, "SN": over, "IT": over, "IN": over})
    assert evaluate(three)["rule_grade"] == 2
    assert evaluate(four)["rule_grade"] == 3
    assert evaluate(four)["four_two_one"]["haemorrhages_4q"] is True


def test_unassessable_limbs_are_reported_as_unknown_not_absent():
    """Treating 'we cannot detect venous beading' as 'there is none' would systematically
    under-grade the sickest patients. It must be None, never False."""
    f = evaluate(L(ma=5))["four_two_one"]
    assert f["venous_beading_2q"] is None
    assert f["irma_1q"] is None


def test_pdr_from_cnn_is_flagged_as_unconfirmable_not_as_disagreement():
    r = evaluate(L(ma=20, he=10), cnn_grade=4)
    assert r["flag"] == "rules_cannot_confirm"
    assert r["agrees_with_cnn"] is None          # not False — we simply cannot tell
    assert r["recommendation"] == "clinician_review"


def test_referral_disagreement_escalates():
    r = evaluate(L(), cnn_grade=3)               # rules say 0, CNN says 3
    assert r["flag"] == "referral_disagreement"
    assert r["recommendation"] == "clinician_review"


def test_severity_disagreement_that_does_not_change_referral_stays_routine():
    r = evaluate(L(ma=30, he=12), cnn_grade=3)   # rules 2, CNN 3 — both referable
    assert r["flag"] == "severity_disagreement"
    assert r["referable_agrees"] is True
    assert r["recommendation"] == "routine"
