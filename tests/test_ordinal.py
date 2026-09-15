"""The ordinal head's maths. If this breaks, every grade the system reports is wrong."""
import numpy as np
import pytest

from src.grading.model import (NUM_CUTS, cumulative_to_grade, cumulative_to_per_grade,
                               grade_to_levels, logits_to_cumulative,
                               referable_probability)


def test_grade_to_levels_roundtrip():
    y = np.array([0, 1, 2, 3, 4])
    lv = grade_to_levels(y)
    assert lv.shape == (5, NUM_CUTS)
    assert (lv.sum(axis=1) == y).all()          # grade == number of exceeded cuts
    assert np.all(np.diff(lv, axis=1) <= 0)     # cumulative encoding is monotone


def test_cumulative_is_monotone_even_for_disordered_logits():
    # CORAL's shared weights make this monotone by construction, but we enforce it so a
    # future head change cannot silently emit "worse than 2 but not worse than 1".
    cum = logits_to_cumulative(np.array([[-5.0, 9.0, -3.0, 7.0]]))
    assert np.all(np.diff(cum, axis=1) <= 1e-12)


def test_per_grade_probabilities_sum_to_one():
    cum = logits_to_cumulative(np.random.default_rng(0).normal(size=(64, NUM_CUTS)))
    p = cumulative_to_per_grade(cum)
    assert p.shape == (64, 5)
    assert np.allclose(p.sum(axis=1), 1.0)
    assert (p >= 0).all()


def test_grade_never_skips_and_matches_cut_count():
    cum = np.array([[0.9, 0.8, 0.7, 0.6], [0.9, 0.1, 0.05, 0.01], [0.1, 0.0, 0.0, 0.0]])
    assert cumulative_to_grade(cum).tolist() == [4, 1, 0]


def test_referable_probability_is_the_second_cut():
    cum = np.array([[0.9, 0.42, 0.1, 0.01]])
    assert referable_probability(cum)[0] == pytest.approx(0.42)


def test_referable_agrees_with_decoded_grade():
    """P(grade>=2) above the cut must imply the decoded grade is >= 2, or the UI would
    show a referral decision contradicting the grade beside it."""
    rng = np.random.default_rng(3)
    cum = logits_to_cumulative(rng.normal(size=(500, NUM_CUTS)) * 2)
    cuts = [0.5] * NUM_CUTS
    grades = cumulative_to_grade(cum, cuts)
    referable_by_prob = referable_probability(cum) > cuts[1]
    assert ((grades >= 2) == referable_by_prob).all()
