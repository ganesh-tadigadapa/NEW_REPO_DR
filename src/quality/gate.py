"""Requirement #1 — image quality assessment, enhancement, and refusal.

Three independent checks. Each one produces a NUMBER, a threshold, and a pass/fail, so
the API can tell a health worker *which* thing was wrong and what to do about it. That
specificity is the whole point: "bad image" is useless to someone holding a camera in a
village clinic; "out of focus - clean the lens and retake" is actionable.

  focus         Contrast-normalised Tenengrad (gradient energy / intensity variance)
                over the retina only. Measures sharpness independently of how much
                texture the retina happens to contain. See focus_score for why not the
                textbook Laplacian variance.
  illumination  Coefficient of variation of mean brightness across a 3x3 grid of retina
                cells. A vignetted or half-lit fundus photo has high CV.
  field_of_view Fraction of the frame the retina occupies, plus a centring check. Catches
                "camera not aligned / only half the retina in frame".

Thresholds are FITTED against human labels by `scripts/fit_quality_thresholds.py`, not
picked off the internet. Until that runs, documented defaults are used and the API
reports `_fitted: false`.
"""
from __future__ import annotations

import cv2
import numpy as np

from src.common.config import QualityCheck, quality_thresholds
from src.common.imaging import (ben_graham, clahe_green, crop_to_retina,
                                square_pad, apply_circular_mask)

# What the health worker is told, per failed check. Ordered by severity: if several
# fail we surface the most actionable one first.
RECAPTURE_MESSAGES = {
    "field_of_view": ("The retina is not fully in frame. Move closer and centre the "
                      "camera on the pupil, then retake."),
    "focus": ("Image is out of focus. Clean the camera lens, ask the patient to look "
              "steadily at the fixation target, and retake."),
    "illumination": ("Lighting is uneven across the image. Dim the room, wait a few "
                     "seconds for the pupil to dilate, and retake."),
    # Emitted when focus AND illumination both fail. Measured on 33 illumination-degraded
    # real images: 29 tripped BOTH checks and none tripped illumination alone. Severe
    # one-sided darkening lowers gradient energy on the dark side, so uneven lighting
    # drags the focus score down and produces a spurious focus failure. Leading with
    # "clean the lens" would send the operator to fix the wrong thing, so when the two
    # co-occur we name lighting as the likely root cause and mention focus second.
    "illumination_and_focus": ("Lighting is very uneven, which is also making the image "
                               "read as out of focus. Dim the room, reposition so the "
                               "flash is centred, wait for the pupil to dilate, and "
                               "retake. If it still looks soft, clean the lens."),
}
_SEVERITY_ORDER = ["field_of_view", "focus", "illumination"]


# ------------------------------------------------------------------ measurements
def focus_score(bgr: np.ndarray, mask: np.ndarray) -> float:
    """Contrast-normalised Tenengrad: mean squared gradient magnitude over the retina,
    divided by the retina's own intensity variance.

    Why not the textbook "variance of the Laplacian": raw Laplacian variance conflates
    *blur* with *low texture*. A genuinely healthy grade-0 retina is smooth — few
    lesions, few edges — and scores as low as a blurred diseased one. We measured this
    directly (see results/quality_gate/focus_metric_comparison.json): raw Laplacian
    variance ranked a sharp grade-0 image as blurrier than a deliberately defocused
    image. Normalising gradient energy by the image's own contrast decouples the two, so
    the threshold means "is this in focus" rather than "does this have lesions in it" —
    which matters enormously, because a gate that quietly rejects healthy eyes would
    bias every downstream prevalence number we report.

    Higher is sharper. Unit-free (scaled x100 for readability).
    """
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    energy = (gx[mask] ** 2 + gy[mask] ** 2)
    vals = gray[mask].astype(np.float64)
    if vals.size < 100:
        return 0.0
    contrast = vals.var()
    if contrast < 1e-6:
        return 0.0
    return float(energy.mean() / contrast * 100.0)


def illumination_score(bgr: np.ndarray, mask: np.ndarray, grid: int = 3) -> float:
    """Coefficient of variation of cell-mean luminance across a grid. Lower is better."""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float64)
    h, w = gray.shape
    means = []
    for i in range(grid):
        for j in range(grid):
            ys, ye = i * h // grid, (i + 1) * h // grid
            xs, xe = j * w // grid, (j + 1) * w // grid
            cell, cmask = gray[ys:ye, xs:xe], mask[ys:ye, xs:xe]
            # ignore cells that are mostly outside the retina - the corners of a circle
            # inscribed in a square are legitimately empty and are not a lighting fault
            if cmask.mean() < 0.35:
                continue
            means.append(cell[cmask].mean())
    if len(means) < 2:
        return 1.0
    means = np.array(means)
    if means.mean() < 1e-6:
        return 1.0
    return float(means.std() / means.mean())


def fov_score(mask: np.ndarray) -> tuple[float, float]:
    """(fraction of frame that is retina, normalised centre offset).

    A full fundus photo is a circle inscribed in the frame: pi/4 ~= 0.785 of the pixels.
    Much less than that means the retina is clipped or the camera is too far back.
    """
    frac = float(mask.mean())
    ys, xs = np.where(mask)
    if ys.size == 0:
        return 0.0, 1.0
    h, w = mask.shape
    cy, cx = ys.mean(), xs.mean()
    off = float(np.hypot(cy - h / 2, cx - w / 2) / (min(h, w) / 2))
    return frac, off


# ------------------------------------------------------------------ enhancement
def enhance(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Borderline-image rescue: Ben-Graham + CLAHE, re-masked."""
    out = ben_graham(bgr)
    out = clahe_green(out)
    return apply_circular_mask(out, mask)


# ------------------------------------------------------------------ the gate
def assess(bgr: np.ndarray, thresholds: dict | None = None) -> dict:
    """Run all three checks. Returns the `quality` block of the API contract.

    Enhancement policy: if the image passes outright we still enhance it (the CNN was
    trained on enhanced images, so this is not optional). If it fails ONLY on
    illumination, we enhance and re-measure — Ben-Graham exists precisely to fix uneven
    lighting, so refusing such an image before trying would be wrong. Focus and FOV
    failures are not recoverable by any amount of processing, so we refuse immediately.
    """
    th = thresholds or quality_thresholds()

    cropped, mask = crop_to_retina(bgr)
    cropped, mask = square_pad(cropped, mask)
    # normalise scale so the Laplacian threshold means the same thing for a 1000px and a
    # 4000px camera; without this, focus score scales with sensor resolution.
    side = 1024
    cropped = cv2.resize(cropped, (side, side), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask.astype(np.uint8), (side, side),
                      interpolation=cv2.INTER_NEAREST).astype(bool)

    def measure(img):
        f = focus_score(img, mask)
        i = illumination_score(img, mask)
        return f, i

    focus, illum = measure(cropped)
    frac, centre_off = fov_score(mask)

    fov_ok = frac >= th["fov_retina_fraction_min"] and centre_off <= 0.45
    focus_ok = focus >= th["focus_tenengrad_min"]
    illum_ok = illum <= th["illumination_grid_cv_max"]

    enhanced_applied = False
    if fov_ok and focus_ok and not illum_ok:
        rescued = enhance(cropped, mask)
        _, illum2 = measure(rescued)
        if illum2 <= th["illumination_grid_cv_max"]:
            illum, illum_ok, enhanced_applied = illum2, True, True

    checks = {
        "focus": QualityCheck(focus_ok, focus, th["focus_tenengrad_min"], "tenengrad_norm"),
        "illumination": QualityCheck(illum_ok, illum, th["illumination_grid_cv_max"], "grid_cv"),
        "field_of_view": QualityCheck(fov_ok, frac, th["fov_retina_fraction_min"], "retina_frac"),
    }
    gradeable = all(c.passed for c in checks.values())

    instruction = None
    if not gradeable:
        failed = {name for name, c in checks.items() if not c.passed}
        # Field of view is unrecoverable and unambiguous, so it always wins. Otherwise,
        # if focus and illumination failed together, uneven lighting is the more likely
        # root cause of both -- see the note on RECAPTURE_MESSAGES.
        if "field_of_view" in failed:
            instruction = RECAPTURE_MESSAGES["field_of_view"]
        elif {"focus", "illumination"} <= failed:
            instruction = RECAPTURE_MESSAGES["illumination_and_focus"]
        else:
            for name in _SEVERITY_ORDER:
                if name in failed:
                    instruction = RECAPTURE_MESSAGES[name]
                    break

    return {
        "gradeable": gradeable,
        "overall_score": round(_overall(checks, th), 4),
        "checks": {k: v.to_dict() for k, v in checks.items()},
        "enhanced": enhanced_applied or gradeable,
        "recapture_instruction": instruction,
        "threshold_source": th.get("_source"),
        "thresholds_fitted": bool(th.get("_fitted", False)),
        "_centre_offset": round(centre_off, 4),
    }


def _overall(checks: dict, th: dict) -> float:
    """A single 0-1 number for the UI dial. Geometric mean of three clipped ratios, so
    one very bad check cannot be hidden by two good ones."""
    f = min(checks["focus"].value / max(th["focus_tenengrad_min"], 1e-6), 1.5) / 1.5
    i = min(max(th["illumination_grid_cv_max"], 1e-6) / max(checks["illumination"].value, 1e-6), 1.5) / 1.5
    v = min(checks["field_of_view"].value / max(th["fov_retina_fraction_min"], 1e-6), 1.5) / 1.5
    vals = np.clip([f, i, v], 1e-3, 1.0)
    return float(np.exp(np.mean(np.log(vals))))
