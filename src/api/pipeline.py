"""The one pass that produces an entire /v1/analyze response.

Order is fixed and each step is timed:

    quality gate -> (refuse and stop)  |  preprocess -> grade -> Grad-CAM
                                                     -> lesion CV -> ICDR rules -> PDF

Two invariants that are worth stating out loud because they are what make the output
trustworthy:

  1. **An image that fails the gate is never graded.** We return the refusal and stop.
     There is no "grade it anyway with low confidence" path, because a confident-looking
     grade on an ungradeable image is exactly how a screening programme goes wrong.
  2. **Every block is independently degradable.** No model? Quality + lesions + rules
     still run and the response says why grading is absent. Grad-CAM fails? The grade
     still returns. Nothing in this function can turn a partial result into no result.
"""
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone

import numpy as np

from src.common.config import (DISCLAIMER, LESION_IMAGE_SIZE, TRAIN_IMAGE_SIZE)
from src.common.imaging import (preprocess_for_lesions, preprocess_for_model,
                                to_png_bytes)
from src.explain import icdr_rules
from src.explain.gradcam import attention_summary, gradcam, overlay
from src.quality import gate as quality_gate
from src.segment import lesions as lesion_cv
from src.segment.structures import draw_landmarks, find_fovea, find_optic_disc

log = logging.getLogger(__name__)


class _Timer:
    def __init__(self):
        self.marks = {}
        self._t0 = time.perf_counter()

    def mark(self, name, start):
        self.marks[name] = int((time.perf_counter() - start) * 1000)

    def total(self):
        self.marks["total"] = int((time.perf_counter() - self._t0) * 1000)
        return self.marks


def _b64(png: bytes) -> str:
    import base64
    return base64.b64encode(png).decode("ascii")


def analyze(bgr: np.ndarray, predictor, *, patient_ref: str | None = None,
            want_report: bool = True, want_images: bool = True) -> tuple[dict, int]:
    """Returns (response_dict, http_status). 422 means 'ungradeable', which is a
    successful refusal, not an error."""
    t = _Timer()
    scan_id = "sc_" + uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    base = {
        "scan_id": scan_id,
        "created_at": now,
        "patient_ref": patient_ref,
        "model_id": predictor.model_id if predictor.available else None,
        "disclaimer": DISCLAIMER,
        # Propagated into every response so the UI can refuse to present a synthetic
        # model's output as a clinical result.
        "synthetic_demo_model": bool(getattr(predictor, "synthetic", False)),
    }

    # ------------------------------------------------------------ 1. quality
    s = time.perf_counter()
    quality = quality_gate.assess(bgr)
    t.mark("quality", s)

    if not quality["gradeable"]:
        return ({**base, "quality": quality, "grading": None, "lesions": None,
                 "rule_check": None, "explain": None, "report": None,
                 "timing_ms": t.total()}, 422)

    # --------------------------------------------------------- 2. preprocess
    s = time.perf_counter()
    model_img = preprocess_for_model(bgr, predictor.image_size or TRAIN_IMAGE_SIZE)
    lesion_img, lesion_mask = preprocess_for_lesions(bgr, LESION_IMAGE_SIZE)
    t.mark("preprocess", s)

    # ------------------------------------------------------------- 3. grade
    grading, grading_error = None, None
    if predictor.available:
        s = time.perf_counter()
        try:
            grading = predictor.predict_one(model_img)
        except Exception as e:                    # noqa: BLE001
            log.exception("grading failed")
            grading_error = str(e)
        t.mark("grading", s)
    else:
        grading_error = predictor.reason or "no model loaded"

    # ------------------------------------------- 4. landmarks + lesion CV
    s = time.perf_counter()
    try:
        disc = find_optic_disc(lesion_img, lesion_mask)
        fovea = find_fovea(lesion_img, lesion_mask, disc)
        lesion_out = lesion_cv.analyse(lesion_img, lesion_mask, disc, fovea)
        lesions_summary, lesions_raw = lesion_out["summary"], lesion_out["raw"]
    except Exception as e:                        # noqa: BLE001
        log.exception("lesion analysis failed")
        disc = fovea = None
        lesions_summary, lesions_raw = None, {}
        grading_error = grading_error or f"lesion analysis failed: {e}"
    t.mark("lesions", s)

    # -------------------------------------------------------- 5. ICDR rules
    rule_block = None
    if lesions_summary is not None:
        rules = icdr_rules.evaluate(
            lesions_summary,
            cnn_grade=grading["icdr_grade"] if grading else None)
        rule_block = icdr_rules.api_block(rules)

    # ---------------------------------------------------------- 6. Grad-CAM
    explain_block, overlay_img = None, None
    if want_images:
        s = time.perf_counter()
        try:
            cam = None
            if predictor.available and predictor.last_conv:
                cam = gradcam(predictor.model, model_img[None, ...].astype("float32"),
                              predictor.last_conv)
            lesion_overlay = (lesion_cv.draw_lesions(lesion_img, lesions_raw)
                              if lesions_raw else lesion_img)
            if disc and fovea:
                lesion_overlay = draw_landmarks(lesion_overlay, disc, fovea)

            explain_block = {
                "gradcam_available": cam is not None,
                "gradcam_unavailable_reason": None if cam is not None else grading_error,
                "lesion_overlay_png_b64": _b64(to_png_bytes(lesion_overlay)),
            }
            if cam is not None:
                import cv2
                # Mask the heatmap to the retina. Attention shown over the black surround
                # is meaningless — there is no tissue there — and a heatmap that appears
                # to light up outside the eye undermines the explanation it is meant to
                # provide. The model image is already circularly masked, so the retina is
                # exactly the non-black region.
                mmask = cv2.cvtColor(model_img, cv2.COLOR_BGR2GRAY) > 0
                overlay_img = overlay(model_img, cam, mask=mmask)
                explain_block["overlay_png_b64"] = _b64(to_png_bytes(overlay_img))
                explain_block["gradcam_png_b64"] = _b64(to_png_bytes(
                    (cv2.resize(cam, model_img.shape[:2][::-1]) * 255).astype("uint8")))
                if disc and fovea:
                    explain_block["attention_summary"] = attention_summary(
                        cam, lesions_raw, disc, fovea, LESION_IMAGE_SIZE)
        except Exception as e:                    # noqa: BLE001
            log.exception("explainability failed")
            explain_block = {"gradcam_available": False,
                             "gradcam_unavailable_reason": str(e)}
        t.mark("gradcam", s)

    if grading is None:
        grading = {"available": False, "reason": grading_error,
                   "icdr_grade": None, "referable": None}

    result = {**base, "quality": quality, "grading": grading if grading.get("available") is not False else None,
              "grading_unavailable_reason": grading_error if grading.get("available") is False else None,
              "lesions": lesions_summary, "rule_check": rule_block,
              "explain": explain_block, "report": None, "timing_ms": t.marks}

    # ------------------------------------------------------------ 7. report
    if want_report:
        s = time.perf_counter()
        try:
            from src.explain.report import build_report_b64
            pdf = build_report_b64(result, lesion_img, overlay_img)
            result["report"] = {"pdf_b64": pdf,
                                "filename": f"dr-report-{scan_id}.pdf"}
        except Exception as e:                    # noqa: BLE001
            log.exception("report generation failed")
            result["report"] = {"error": str(e)}
        t.mark("report", s)

    result["timing_ms"] = t.total()
    return result, 200
