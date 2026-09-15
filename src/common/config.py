"""Single source of truth for constants shared across modules.

Anything a judge might ask "where did that number come from?" about lives here with a
comment saying how it was chosen. Thresholds fitted from data are loaded from
`results/`, never hardcoded — see `quality_thresholds()`.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = REPO_ROOT / "results"
DATA_DIR = REPO_ROOT / "data"
ASSETS_DIR = REPO_ROOT / "assets"

DISCLAIMER = "Screening triage aid. Not a diagnostic device."

# ---------------------------------------------------------------- ICDR scale
ICDR_LABELS = {
    0: "No DR",
    1: "Mild NPDR",
    2: "Moderate NPDR",
    3: "Severe NPDR",
    4: "Proliferative DR",
}
# Referable DR = grade 2 or worse. This is the operational decision that matters.
REFERABLE_MIN_GRADE = 2

# ---------------------------------------------------------------- image sizes
# 512 is the training resolution: microaneurysms are a few pixels across at 512 and
# effectively vanish at 224, which is why the usual ImageNet size underperforms here.
TRAIN_IMAGE_SIZE = 512
# Lesion CV runs at higher resolution than the CNN — small lesions need the pixels.
LESION_IMAGE_SIZE = 1024

# ---------------------------------------------------------------- quality gate
# DEFAULTS ONLY. These are the starting points used before the 200-image labelling
# session; `quality_thresholds()` prefers the fitted values whenever they exist.
DEFAULT_QUALITY_THRESHOLDS = {
    "focus_tenengrad_min": 20.0,
    "illumination_grid_cv_max": 0.45,
    "fov_retina_fraction_min": 0.60,
}
QUALITY_THRESHOLDS_FILE = RESULTS_DIR / "quality_gate" / "thresholds.json"


def quality_thresholds() -> dict:
    """Fitted thresholds if the calibration has been run, else documented defaults."""
    if QUALITY_THRESHOLDS_FILE.exists():
        payload = json.loads(QUALITY_THRESHOLDS_FILE.read_text())
        out = dict(DEFAULT_QUALITY_THRESHOLDS)
        out.update(payload.get("thresholds", {}))
        out["_source"] = str(QUALITY_THRESHOLDS_FILE.relative_to(REPO_ROOT))
        out["_fitted"] = True
        return out
    return {**DEFAULT_QUALITY_THRESHOLDS, "_source": "src/common/config.py defaults", "_fitted": False}


# ---------------------------------------------------------------- grading model
MODEL_DIR = Path(os.getenv("DR_MODEL_DIR", str(REPO_ROOT / "artifacts" / "model")))
# Ordinal cut points: score in [0,4] -> grade. Overwritten by the tuned set when present.
DEFAULT_ORDINAL_CUTS = [0.5, 1.5, 2.5, 3.5]
ORDINAL_CUTS_FILE = MODEL_DIR / "thresholds.json"
TEMPERATURE_FILE = MODEL_DIR / "temperature.json"


@dataclass
class QualityCheck:
    passed: bool
    value: float
    threshold: float
    unit: str

    def to_dict(self) -> dict:
        d = asdict(self)
        d["value"] = round(float(self.value), 4)
        d["threshold"] = round(float(self.threshold), 4)
        return d
