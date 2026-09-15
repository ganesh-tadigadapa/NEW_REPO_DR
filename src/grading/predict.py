"""Inference wrapper around the grading model.

Two responsibilities beyond "call the model":

1. **Degrade honestly when there are no weights.** Until training lands, `load()` returns
   a predictor with `available=False`. The API then serves the quality gate, lesion CV
   and the rule engine — which need no CNN — and returns `grading: null` with an explicit
   reason. This is what lets the app be live and useful from hour 1, and it is why the
   frontend never sees a fabricated grade.
2. **Own the tuned thresholds and the temperature.** The cut points and T are properties
   of a *run*, not of the code, so they load from the model directory alongside the
   weights and travel with them.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from src.common.config import (DEFAULT_ORDINAL_CUTS, ICDR_LABELS, MODEL_DIR,
                               REFERABLE_MIN_GRADE, TRAIN_IMAGE_SIZE)
from src.explain.calibration import confidence_from_cumulative
from src.grading.model import (cumulative_to_grade, cumulative_to_per_grade,
                               logits_to_cumulative, referable_probability)

log = logging.getLogger(__name__)

# Cut points act on the CUMULATIVE probabilities P(grade>k), so they live in [0,1] and
# default to 0.5 each. The referable cut (index 1) is the one tuned for sensitivity.
DEFAULT_CUMULATIVE_CUTS = [0.5, 0.5, 0.5, 0.5]


class Predictor:
    def __init__(self, model=None, cuts=None, temperature: float = 1.0,
                 model_id: str = "none", image_size: int = TRAIN_IMAGE_SIZE,
                 last_conv: str | None = None, reason: str | None = None,
                 synthetic: bool = False):
        self.model = model
        self.cuts = list(cuts or DEFAULT_CUMULATIVE_CUTS)
        self.temperature = float(temperature)
        self.model_id = model_id
        self.image_size = image_size
        self.last_conv = last_conv
        self.reason = reason
        # True when the loaded weights come from the synthetic demo model. Surfaced all
        # the way to the UI so nobody can mistake a plumbing demo for a clinical result.
        self.synthetic = synthetic

    @property
    def available(self) -> bool:
        return self.model is not None

    @property
    def calibrated(self) -> bool:
        return abs(self.temperature - 1.0) > 1e-9

    def logits(self, batch: np.ndarray) -> np.ndarray:
        raw = self.model.predict(batch, verbose=0)
        return np.asarray(raw, dtype=np.float64) / max(self.temperature, 1e-3)

    def predict_one(self, image_chw: np.ndarray) -> dict:
        """image_chw: (H,W,3) uint8 preprocessed to the training transform."""
        if not self.available:
            raise RuntimeError("no model loaded")
        batch = image_chw[None, ...].astype("float32")
        lg = self.logits(batch)
        cum = logits_to_cumulative(lg)
        grade = int(cumulative_to_grade(cum, self.cuts)[0])
        per_grade = cumulative_to_per_grade(cum)[0]
        p_ref = float(referable_probability(cum)[0])
        most_likely = int(np.argmax(per_grade))
        return {
            "icdr_grade": grade,
            # The reported grade comes from tuned cut points, not from argmax, and the two
            # can differ: the referable cut is deliberately lowered to hit the sensitivity
            # target, which means we knowingly over-call borderline cases. Surfacing this
            # rather than hiding it is the difference between a reviewer seeing a
            # considered trade-off and a reviewer seeing a broken confidence number.
            "most_likely_grade": most_likely,
            "grade_from_threshold_not_argmax": bool(most_likely != grade),
            "icdr_label": ICDR_LABELS[grade],
            "referable": bool(grade >= REFERABLE_MIN_GRADE),
            "referable_probability": round(p_ref, 4),
            "ordinal_score": round(float(cum[0].sum()), 4),
            "confidence": round(confidence_from_cumulative(cum[0], grade), 4),
            "confidence_calibrated": self.calibrated,
            "per_grade_probability": [round(float(p), 4) for p in per_grade],
            "cumulative_probability": [round(float(p), 4) for p in cum[0]],
            "threshold_set": self.model_id,
            "cuts": self.cuts,
        }


def load(model_dir: Path | None = None) -> Predictor:
    """Load weights + thresholds + temperature, or return an unavailable Predictor."""
    d = Path(model_dir or MODEL_DIR)
    weights = None
    for name in ("model.keras", "saved_model", "model.h5"):
        p = d / name
        if p.exists():
            weights = p
            break
    if weights is None:
        return Predictor(reason=f"no model artifact found in {d}")

    try:
        import tensorflow as tf
        from src.grading.model import CoralHead
        model = tf.keras.models.load_model(
            str(weights), custom_objects={"CoralHead": CoralHead}, compile=False)
    except Exception as e:                       # noqa: BLE001 - must never crash the API
        log.exception("model load failed")
        return Predictor(reason=f"model present but failed to load: {e}")

    cuts = DEFAULT_CUMULATIVE_CUTS
    tp = d / "thresholds.json"
    if tp.exists():
        try:
            cuts = json.loads(tp.read_text())["cumulative_cuts"]
        except Exception:
            log.warning("thresholds.json unreadable; using defaults")
    temperature = 1.0
    cp = d / "temperature.json"
    if cp.exists():
        try:
            temperature = float(json.loads(cp.read_text())["temperature"])
        except Exception:
            log.warning("temperature.json unreadable; using T=1")

    meta = {}
    mp = d / "run.json"
    if mp.exists():
        try:
            meta = json.loads(mp.read_text())
        except Exception:
            pass

    size = int(meta.get("image_size", model.input_shape[1] or TRAIN_IMAGE_SIZE))
    last_conv = meta.get("last_conv_layer") or _guess_last_conv(model)
    return Predictor(model=model, cuts=cuts, temperature=temperature,
                     model_id=meta.get("run_id", weights.stem), image_size=size,
                     last_conv=last_conv,
                     synthetic=bool(meta.get("synthetic_demo_model", False)))


def _guess_last_conv(model) -> str | None:
    import tensorflow as tf
    for layer in reversed(model.layers):
        if isinstance(layer, tf.keras.layers.Conv2D):
            return layer.name
        # the backbone may be nested as a single layer
        if hasattr(layer, "layers"):
            for inner in reversed(layer.layers):
                if isinstance(inner, tf.keras.layers.Conv2D):
                    return inner.name
    return None
