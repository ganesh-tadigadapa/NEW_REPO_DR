"""Lesion detection and vessel suppression.

These two components fight each other: vessels and dark lesions look identical to an
intensity threshold, so anything that suppresses vessels can delete lesions. Both bugs
below were real, and both were invisible without measuring against known ground truth —
the pipeline returned a confident, well-formed, completely wrong answer.

Counts are checked against the synthetic generator's planted lesions. Synthetic images
are NOT valid for reporting accuracy, but they are exactly right for pinning a
regression, because we know the true count.
"""
import cv2
import numpy as np
import pytest

from scripts.make_synthetic_fundus import synth
from src.common.imaging import preprocess_for_lesions
from src.segment.lesions import analyse, elongated_vessels, vessel_map
from src.segment.structures import find_fovea, find_optic_disc

SIZE = 1024


def pipeline(grade: int, seed: int = 0):
    img = synth(SIZE, grade=grade, seed=100 * grade + seed)
    li, lm = preprocess_for_lesions(img, SIZE)
    disc = find_optic_disc(li, lm)
    fovea = find_fovea(li, lm, disc)
    return li, lm, disc, fovea


@pytest.mark.parametrize("grade", [0, 1, 2, 3, 4])
def test_vessel_map_covers_a_plausible_fraction(grade):
    """Regression: the first implementation (max-over-orientation morphological line
    opening) flagged 99% of the retina and deleted every lesion candidate downstream.
    The second returned an EMPTY mask on any diseased image, disabling suppression
    exactly where it matters. Both were silent."""
    li, lm, _, _ = pipeline(grade)
    coverage = vessel_map(li, lm)[lm].mean()
    assert 0.02 <= coverage <= 0.30, f"grade {grade}: implausible coverage {coverage:.3f}"


def test_suppression_uses_only_elongated_components():
    """A compact blob of vesselness response is far more likely to be the lesion we are
    counting than a vessel. Suppressing on the whole mask lost real haemorrhages."""
    blob = np.zeros((200, 200), bool)
    cv2.circle(blob.view(np.uint8), (100, 100), 12, 1, -1)
    assert not elongated_vessels(blob).any(), "a disc must not count as a vessel"

    line = np.zeros((200, 200), bool)
    cv2.line(line.view(np.uint8), (10, 100), (190, 104), 1, 3)
    assert elongated_vessels(line).any(), "a long thin stroke must count as a vessel"


@pytest.mark.parametrize("grade,planted_ma", [(0, 0), (1, 6), (2, 18)])
def test_microaneurysms_survive_vessel_suppression(grade, planted_ma):
    """Regression: raising Frangi's minimum scale to 2.0 matters because at sigma 1 a
    microaneurysm IS a valid ridge — the vessel mask ate all 18 planted MAs on grade 2."""
    li, lm, disc, fovea = pipeline(grade)
    got = analyse(li, lm, disc, fovea)["summary"]["microaneurysms"]["count"]
    if planted_ma == 0:
        assert got == 0
    else:
        assert got >= 0.8 * planted_ma, f"lost too many: {got}/{planted_ma}"


def test_clean_retina_produces_no_false_lesions():
    """A grade-0 image must not manufacture disease. A false positive here becomes an
    unnecessary referral, and at screening scale that is how you overwhelm a district."""
    li, lm, disc, fovea = pipeline(0)
    s = analyse(li, lm, disc, fovea)["summary"]
    assert s["microaneurysms"]["count"] == 0
    assert s["haemorrhages"]["count"] == 0


def test_lesion_counts_increase_with_severity():
    """Monotonicity is the weakest true claim we can make, and it must hold — if it
    doesn't, the rule engine's grade is noise."""
    totals = []
    for g in (0, 2, 4):
        li, lm, disc, fovea = pipeline(g)
        s = analyse(li, lm, disc, fovea)["summary"]
        totals.append(sum(s[k]["count"] for k in
                          ("microaneurysms", "haemorrhages", "hard_exudates")))
    assert totals[0] < totals[1] < totals[2], totals


def test_quadrant_counts_sum_to_the_total():
    """The 4-2-1 rule reads per-quadrant counts; if they don't sum, the rule is wrong."""
    li, lm, disc, fovea = pipeline(3)
    s = analyse(li, lm, disc, fovea)["summary"]
    for key in ("microaneurysms", "haemorrhages", "hard_exudates"):
        assert sum(s[key]["by_quadrant"].values()) == s[key]["count"], key
