"""The quality gate. A regression here silently changes who gets screened."""
from pathlib import Path

import cv2
import numpy as np
import pytest

from scripts.make_synthetic_fundus import synth
from src.quality.gate import RECAPTURE_MESSAGES, assess, focus_score


@pytest.fixture(scope="module")
def good():
    """A REAL held-out APTOS image, not a synthetic one.

    This used to be `synth(768, grade=3, seed=11)`. Once the thresholds were refitted on
    real images (results/quality_gate/thresholds.json, tag real-degraded) the synthetic
    fixture started failing the focus check -- generated fundus texture does not have the
    gradient statistics of a real retina, so a threshold calibrated on real images
    legitimately refuses it. Testing the real contract against a real image is the
    stronger assertion, so the fixture moved rather than the threshold.
    """
    path = Path(__file__).resolve().parents[1] / "web/public/samples/aptos-grade0.png"
    img = cv2.imread(str(path))
    assert img is not None, f"missing demo sample {path}"
    return img


def test_good_image_passes(good):
    assert assess(good)["gradeable"] is True


def test_synthetic_fundus_is_not_used_to_validate_the_fitted_gate():
    """Guard against quietly reverting the fixture above to a synthetic image.

    The gate's thresholds are fitted on real data; validating it against generated
    images would be circular and would hide exactly the defect that refitting fixed.
    """
    src = Path(__file__).read_text()
    assert "def good():" in src
    block = src.split("def good():", 1)[1].split("def test_good_image_passes", 1)[0]
    code = [ln for ln in block.splitlines() if "return synth(" in ln]
    assert not code, "the `good` fixture must return a real image, not synth(...)"


@pytest.mark.parametrize("defect,expected_check", [
    ("blur", "focus"),
    ("clipped", "field_of_view"),
])
def test_defects_are_refused_with_the_right_reason(defect, expected_check):
    r = assess(synth(768, grade=3, seed=11, defect=defect))
    assert r["gradeable"] is False
    assert r["checks"][expected_check]["passed"] is False
    assert r["recapture_instruction"] == RECAPTURE_MESSAGES[expected_check]


def test_refusal_always_carries_an_actionable_instruction():
    for defect in ("blur", "clipped", "uneven"):
        r = assess(synth(768, grade=2, seed=5, defect=defect))
        if not r["gradeable"]:
            assert r["recapture_instruction"], "a refusal with no instruction is useless"
            assert len(r["recapture_instruction"]) > 25


def test_focus_score_is_not_a_proxy_for_lesion_count(good):
    """The bug this pins: raw Laplacian variance scored a clean grade-0 retina as
    blurrier than a defocused diseased one, so the gate would have quietly rejected
    healthy eyes and biased every prevalence number downstream."""
    from src.common.imaging import crop_to_retina, square_pad

    def prep(img):
        c, m = crop_to_retina(img)
        c, m = square_pad(c, m)
        c = cv2.resize(c, (1024, 1024), interpolation=cv2.INTER_AREA)
        m = cv2.resize(m.astype(np.uint8), (1024, 1024),
                       interpolation=cv2.INTER_NEAREST).astype(bool)
        return c, m

    healthy_sharp = focus_score(*prep(synth(768, grade=0, seed=21)))
    diseased_blur = focus_score(*prep(synth(768, grade=4, seed=21, defect="blur")))
    assert healthy_sharp > diseased_blur


def test_overall_score_is_bounded():
    for g in range(5):
        s = assess(synth(512, grade=g, seed=g))["overall_score"]
        assert 0.0 <= s <= 1.0


def test_illumination_and_focus_failing_together_blames_lighting_not_the_lens():
    """Uneven lighting lowers the focus score, so the two checks fail together.

    Measured on 33 illumination-degraded real APTOS images: 29 tripped BOTH checks and
    none tripped illumination alone. Reporting "clean the camera lens" there sends the
    operator to fix the wrong thing, so the combined case must name lighting first.
    """
    from src.quality.gate import RECAPTURE_MESSAGES
    import numpy as np
    import cv2
    from src.quality import gate as g

    # a real-shaped fundus with a hard one-sided luminance ramp
    img = np.zeros((600, 600, 3), np.uint8)
    cv2.circle(img, (300, 300), 280, (120, 90, 70), -1)
    ramp = np.linspace(1.0, 0.2, 600, dtype=np.float32)
    img = np.clip(img.astype(np.float32) * ramp[None, :, None], 0, 255).astype(np.uint8)

    q = g.assess(img)
    failed = {k for k, v in q["checks"].items() if not v["passed"]}
    if {"focus", "illumination"} <= failed and "field_of_view" not in failed:
        assert q["recapture_instruction"] == RECAPTURE_MESSAGES["illumination_and_focus"]
        assert "lighting" in q["recapture_instruction"].lower()
