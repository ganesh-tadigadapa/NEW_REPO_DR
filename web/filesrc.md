I'll map out the backend files for you. Let me explore the project structure first.

Bash List project structure and Python files
IN
ls -la && echo "---TREE---" && find . -type f -name "*.py" -not -path "./.git/*" -not -path "*/node_modules/*" -not -path "*/venv/*" -not -path "*/.venv/*" | head -100

OUT
total 184
drwxr-xr-x@  33 ganesh  staff   1056 Sep 15 13:31 .
drwx------@ 142 ganesh  staff   4544 Sep 15 12:50 ..
-rw-r--r--@   1 ganesh  staff  10244 Sep 15 09:25 .DS_Store
-rw-r--r--@   1 ganesh  staff     89 Sep 11 21:36 .dockerignore
drwxr-xr-x@  14 ganesh  staff    448 Sep 14 12:16 .git
-rw-r-----    1 ganesh  staff     44 Sep 14 02:40 .gitattributes
-rw-r--r--@   1 ganesh  staff    436 Sep 11 22:04 .gitignore
drwxr-xr-x@   6 ganesh  staff    192 Sep 11 21:34 .pytest_cache
drwxr-xr-x@   9 ganesh  staff    288 Sep 13 19:08 .venv
-rw-r--r--@   1 ganesh  staff   2130 Sep 11 22:13 Dockerfile
-rw-r--r--@   1 ganesh  staff   5819 Sep 13 15:50 EXPLAIN_IT_BLOCK1.md
-rw-r--r--@   1 ganesh  staff  21361 Sep 14 12:40 FILE_MAP.txt
drwxr-xr-x@   9 ganesh  staff    288 Sep 14 00:14 GUIDE
-rw-r--r--@   1 ganesh  staff   2905 Sep 11 21:59 Makefile
-rw-r--r--@   1 ganesh  staff   4437 Sep 14 00:14 README.md
drwxr-xr-x@   3 ganesh  staff     96 Sep 11 21:34 __pycache__
drwxr-xr-x@   6 ganesh  staff    192 Sep 15 09:25 artifacts
drwxr-xr-x@   3 ganesh  staff     96 Sep 11 20:27 assets
-rw-r--r--@   1 ganesh  staff     80 Sep 11 20:37 conftest.py
drwxr-xr-x@   6 ganesh  staff    192 Sep 12 21:46 data
drwxr-xr-x@   4 ganesh  staff    128 Sep 13 22:58 deploy
drwxr-xr-x@   9 ganesh  staff    288 Sep 12 22:06 docs
drwxr-xr-x@   7 ganesh  staff    224 Sep 13 18:43 matlab
drwxr-xr-x@   5 ganesh  staff    160 Sep 13 18:51 notebooks
-rw-r--r--@   1 ganesh  staff    270 Sep 11 20:37 pyproject.toml
-rw-r--r--@   1 ganesh  staff     65 Sep 11 20:27 requirements-dev.txt
-rw-r--r--@   1 ganesh  staff   1787 Sep 12 00:03 requirements-serve.txt
-rw-r--r--@   1 ganesh  staff    530 Sep 11 20:27 requirements.txt
drwxr-xr-x@  14 ganesh  staff    448 Sep 13 23:51 results
drwxr-xr-x@  20 ganesh  staff    640 Sep 13 21:35 scripts
drwxr-xr-x@  11 ganesh  staff    352 Sep 12 21:46 src
drwxr-xr-x@   8 ganesh  staff    256 Sep 11 23:55 tests
drwxr-xr-x@  16 ganesh  staff    512 Sep 12 21:50 web
---TREE---
./conftest.py
./tests/test_ordinal.py
./tests/test_quality_gate.py
./tests/test_lesions.py
./tests/test_samples.py
./tests/test_icdr_rules.py
./scripts/eval_explainability.py
./scripts/compare_focus_metrics.py
./scripts/calibrate_and_freeze.py
./scripts/compare_matlab_python.py
./scripts/fit_quality_thresholds.py
./scripts/export_simulink_params.py
./scripts/run_ablation.py
./scripts/__init__.py
./scripts/make_quality_labelset.py
./scripts/eval_localisation.py
./scripts/run_holdout.py
./scripts/make_synthetic_fundus.py
./scripts/eval_vessels.py
./scripts/eval_quality_gate.py
./scripts/simulate_workflow.py
./scripts/export_session.py
./notebooks/kaggle_train_selfcontained.py
./notebooks/kaggle_train.py
./src/__init__.py
./src/explain/icdr_rules.py
./src/explain/__init__.py
./src/explain/gradcam.py
./src/explain/report.py
./src/explain/calibration.py
./src/grading/predict.py
./src/grading/__init__.py
./src/grading/model.py
./src/grading/train.py
./src/grading/evaluate.py
./src/grading/data.py
./src/quality/__init__.py
./src/quality/gate.py
./src/segment/__init__.py
./src/segment/lesions.py
./src/segment/structures.py
./src/common/config.py
./src/common/__init__.py
./src/common/imaging.py
./src/api/store.py
./src/api/__init__.py
./src/api/pipeline.py
./src/api/main.py
Bash Dump headers and definitions of backend modules
IN
for f in src/api/*.py src/common/*.py src/quality/*.py src/segment/*.py src/grading/*.py src/explain/*.py; do echo "=========== $f ($(wc -l < $f) lines)"; head -25 "$f"; echo "--- defs:"; grep -nE "^(def |class |async def )" "$f"; done 2>/dev/null | head -400

OUT
=========== src/api/__init__.py (       0 lines)
--- defs:
=========== src/api/main.py (     221 lines)
"""FastAPI service. Implements docs/API_CONTRACT.md v1.

Deployment note that is also a design principle: the model is loaded **in-process**, not
called over the network from a Vertex prediction endpoint. Grad-CAM needs the gradient of
an output with respect to an intermediate activation, and a managed endpoint returns only
the output tensor. The explainability requirement therefore rules that architecture out.
It is also cheaper, and it is a good answer to give when a judge asks why there is no
"proper" model-serving tier.

The service starts and answers `/health` with `model_loaded: false` when no weights are
present. That is deliberate: it lets the URL be live from hour 1.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.pipeline import analyze
--- defs:
55:def _startup():
66:def health():
81:def root():
87:async def analyze_endpoint(file: UploadFile = File(...),
125:def _summarise(result: dict) -> dict:
150:class Review(BaseModel):
158:def review(scan_id: str, body: Review):
168:def scans(limit: int = 50):
174:def metrics():
193:def operational():
=========== src/api/pipeline.py (     190 lines)
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
--- defs:
39:class _Timer:
52:def _b64(png: bytes) -> str:
57:def analyze(bgr: np.ndarray, predictor, *, patient_ref: str | None = None,
=========== src/api/store.py (      99 lines)
"""Scan + review persistence.

Firestore in the cloud, a local JSON file when there is no GCP. The interface is
identical so the API never branches on which one is live — and, importantly, the app
runs and demos with zero cloud dependencies, which is what let us keep building while
the billing account was closed.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_LOCK = threading.Lock()


class LocalStore:
    """Append-only JSON store. Good enough for a screening demo; not a database."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
--- defs:
19:class LocalStore:
63:class FirestoreStore:
91:def get_store():
=========== src/common/__init__.py (       0 lines)
--- defs:
=========== src/common/config.py (      81 lines)
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
--- defs:
50:def quality_thresholds() -> dict:
71:class QualityCheck:
=========== src/common/imaging.py (     137 lines)
"""Fundus image preprocessing.

Three operations, in this order, and the order matters:

1. `crop_to_retina`  — fundus photos are a bright circle on a black rectangle, and the
   black border varies hugely between cameras. Cropping to the circle is what makes a
   cheap portable camera's output look dimensionally like a hospital camera's.
2. `ben_graham`      — subtract a heavily blurred copy of the image from itself. This
   cancels the camera's own illumination gradient. Highest-value single trick on fundus
   images; it is what won the 2015 Kaggle DR competition.
3. `clahe_green`     — contrast-limited adaptive histogram equalisation on the green
   channel, which carries the most lesion detail (haemoglobin absorbs green).

Everything here is pure numpy/OpenCV — no model, no GPU. It runs identically in the
trainer, in the API, and in the tests.
"""
from __future__ import annotations

import cv2
import numpy as np


# --------------------------------------------------------------------------- crop
def retina_mask(bgr: np.ndarray, thresh: int = 10) -> np.ndarray:
    """Boolean mask of the illuminated circular retina region."""
--- defs:
24:def retina_mask(bgr: np.ndarray, thresh: int = 10) -> np.ndarray:
39:def crop_to_retina(bgr: np.ndarray, pad: int = 2) -> tuple[np.ndarray, np.ndarray]:
50:def square_pad(bgr: np.ndarray, mask: np.ndarray | None = None):
65:def ben_graham(bgr: np.ndarray, sigma_frac: float = 1 / 30, alpha: float = 4.0,
73:def clahe_green(bgr: np.ndarray, clip: float = 2.5, tiles: int = 8) -> np.ndarray:
80:def apply_circular_mask(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
89:def preprocess_for_model(bgr: np.ndarray, size: int, enhance: bool = True) -> np.ndarray:
108:def preprocess_for_lesions(bgr: np.ndarray, size: int):
124:def decode_image(data: bytes) -> np.ndarray:
133:def to_png_bytes(bgr: np.ndarray) -> bytes:
=========== src/quality/__init__.py (       0 lines)
--- defs:
=========== src/quality/gate.py (     212 lines)
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

--- defs:
54:def focus_score(bgr: np.ndarray, mask: np.ndarray) -> float:
83:def illumination_score(bgr: np.ndarray, mask: np.ndarray, grid: int = 3) -> float:
106:def fov_score(mask: np.ndarray) -> tuple[float, float]:
123:def enhance(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
131:def assess(bgr: np.ndarray, thresholds: dict | None = None) -> dict:
205:def _overall(checks: dict, th: dict) -> float:
=========== src/segment/__init__.py (       0 lines)
--- defs:
=========== src/segment/lesions.py (     261 lines)
"""Requirement #2b — lesion detection by classical computer vision.

Deliberately NOT a trained U-Net. Reasons we say out loud:
  - IDRiD gives 54 pixel-annotated training images. A segmentation net trained on that
    is a model of 54 images, not of diabetic retinopathy.
  - Classical morphology is inherently interpretable: every detection traces to an
    explicit geometric criterion a clinician can be shown.
  - It needs zero training time, which we do not have.

Three detectors, each keyed to the actual appearance of the lesion:

  microaneurysms  Small, round, DARK, isolated. Found by morphological closing on the
                  inverted green channel (removes vessels, which are elongated) followed
                  by extended-minima. The classic Walter-Klein approach.
  haemorrhages    Dark like MAs but LARGER and irregular. Same dark-blob pipeline with a
                  larger size band and a relaxed circularity requirement.
  hard exudates   BRIGHT, sharp-edged, irregular, yellow-white. Found by top-hat on the
                  green channel with the optic disc masked out (the disc is bright and
                  round and would otherwise dominate every image).

Every detector returns pixel-space blobs so the API can draw them and assign quadrants.
"""
from __future__ import annotations

import cv2
--- defs:
37:def vessel_map(bgr: np.ndarray, mask: np.ndarray) -> np.ndarray:
104:def _blobs(binary: np.ndarray, min_area: int, max_area: int,
127:def detect_dark_lesions(bgr: np.ndarray, mask: np.ndarray, disc: dict) -> tuple[list, list]:
178:def elongated_vessels(vessels: np.ndarray, min_elongation: float = 3.0) -> np.ndarray:
199:def detect_exudates(bgr: np.ndarray, mask: np.ndarray, disc: dict) -> list[dict]:
238:def analyse(bgr: np.ndarray, mask: np.ndarray, disc: dict, fovea: dict) -> dict:
254:def draw_lesions(bgr: np.ndarray, raw: dict) -> np.ndarray:
=========== src/segment/structures.py (     121 lines)
"""Requirement #2a — anatomical landmarks: optic disc and fovea.

We need these for two reasons that are not "because the PS asked":

1. The optic disc is the brightest round object in a fundus photo and it looks exactly
   like a giant hard exudate. Without masking it out, the exudate detector fires on it
   every single time. Disc localisation is a *prerequisite* for lesion counting, not a
   decoration.
2. The ICDR 4-2-1 rule is defined *by quadrant*, and quadrants are defined relative to
   the disc-fovea axis. You cannot compute the clinical rule without knowing where the
   disc is.

Both are classical CV. No training data needed, and the failure modes are inspectable.
"""
from __future__ import annotations

import cv2
import numpy as np


def find_optic_disc(bgr: np.ndarray, mask: np.ndarray) -> dict:
    """Locate the optic disc. Returns {'cx','cy','radius','confidence'} in pixels.

    Method: the disc is the brightest sustained region in the red+green channels. We
    blur hard (killing exudates, which are small) and take the max of the smoothed
--- defs:
21:def find_optic_disc(bgr: np.ndarray, mask: np.ndarray) -> dict:
58:def find_fovea(bgr: np.ndarray, mask: np.ndarray, disc: dict) -> dict:
91:def quadrant_of(x: float, y: float, disc: dict, fovea: dict) -> str:
112:def draw_landmarks(bgr: np.ndarray, disc: dict, fovea: dict) -> np.ndarray:
=========== src/grading/__init__.py (       0 lines)
--- defs:
=========== src/grading/data.py (     153 lines)
"""Dataset construction for APTOS / IDRiD.

## The split rule, which matters more than the architecture

Splits are **stratified by grade** and made once, with a fixed seed, and written to disk
as a CSV. Two consequences we say out loud:

  - APTOS is heavily imbalanced (roughly half the images are grade 0 and grade 3 is under
    6%). An unstratified random split can leave a validation set with a handful of grade-3
    cases, and every metric computed on it is then noise.
  - **IDRiD is never split.** It is the external holdout, opened exactly once, after
    everything is frozen. It does not appear in training or validation under any
    circumstance, and no threshold is ever tuned on it.

APTOS gives one image per patient, so there is no patient-level leakage to guard against
here. If a dataset with multiple images per patient is ever added, the split must move to
grouping by patient — a note, not a claim that we did it.

## Augmentation

Only transforms that produce a *plausible fundus photograph*: flips (a mirrored retina is
just the other eye), rotation (the camera has no canonical orientation), and mild
brightness/contrast jitter (cameras and operators vary). We deliberately do NOT use
aggressive colour jitter or cutout: lesion colour is diagnostic information, and cutout
can delete the only lesion in a mild case and turn a grade-1 label into a lie.
--- defs:
42:def stratified_split(paths: list[str], labels: list[int], val_frac: float = 0.15,
58:def write_split(out: Path, train, train_y, val, val_y) -> None:
68:def read_aptos(csv_path: Path, image_dir: Path,
83:def read_idrid(csv_path: Path, image_dir: Path,
102:def _load_and_preprocess(path: str, size: int, enhance: bool) -> np.ndarray:
110:def _augment(x: tf.Tensor, seed: int = 0) -> tf.Tensor:
120:def build_dataset(paths: list[str], labels: list[int], size: int, batch: int,
142:def class_weights_from_levels(labels: list[int]) -> np.ndarray:
=========== src/grading/evaluate.py (     201 lines)
"""Metrics, threshold tuning, and the one-shot holdout protocol.

## The protocol, which is the actual deliverable here

    1. Train.                                        (train split)
    2. Tune the referable cut for sensitivity.       (VALIDATION logits only)
    3. Fit the temperature.                          (VALIDATION logits only)
    4. FREEZE. Write thresholds.json + temperature.json.
    5. Run the holdout ONCE.                         (IDRiD, never seen, never tuned on)

Step 5 is run by `scripts/run_holdout.py`, which refuses to run twice against the same
frozen config without an explicit override, because "we opened the test set once" has to
be enforced by something other than good intentions.

## Metrics we report and why

  QWK                 the APTOS competition metric, so our number is comparable to
                      published work. Quadratic weights punish being far off.
  referable sens/spec the operational decision. Reported WITH bootstrap CIs, because on
                      a 103-image holdout a point estimate alone is close to meaningless.
  ECE                 whether the confidence is honest, before and after calibration.
  confusion matrix    where the errors actually are.
"""
from __future__ import annotations

--- defs:
35:def quadratic_weighted_kappa(y_true, y_pred, n_classes: int = 5) -> float:
56:def confusion(y_true, y_pred, n=5) -> list:
63:def binary_stats(y_true_bin, y_pred_bin) -> dict:
77:def roc_auc(scores, labels) -> float:
92:def bootstrap_ci(fn, *arrays, n_boot: int = 2000, alpha: float = 0.05,
112:def tune_referable_cut(cum_val: np.ndarray, grades_val: np.ndarray,
151:def tune_all_cuts(cum_val: np.ndarray, grades_val: np.ndarray,
172:def evaluate_split(logits: np.ndarray, grades: np.ndarray, cuts, label: str,
=========== src/grading/model.py (     161 lines)
"""Requirement #3 — the ICDR 0-4 severity model.

## Why an ordinal head and not a 5-way softmax

The ICDR grades are *ordered*. Softmax cross-entropy treats "predicted 0, truth 4" and
"predicted 3, truth 4" as equally wrong. Clinically the first could blind someone and the
second is a rounding error. Softmax throws away the single most important structural fact
about the label space.

We use **CORAL** (Consistent Rank Logits, Cao et al. 2020): instead of 5 class scores, the
head emits K-1 = 4 cumulative binary probabilities

    p_k = P(grade > k)   for k = 0,1,2,3

from a *single shared* feature projection plus 4 independent bias terms. Sharing the
weights and letting only the biases differ is what guarantees monotonicity:
p_0 >= p_1 >= p_2 >= p_3 always holds, so the model can never output the incoherent
"probably worse than grade 2 but probably not worse than grade 1".

Three things fall out of this for free, and each is worth saying to a judge:

1. **Referable DR is a direct output.** Referable = grade >= 2 = `p_1`. We do not derive
   it by cutting a regression score or by summing softmax bins — it is one number the
   network was explicitly trained to produce, and it has its own tunable threshold. That
   is what lets us hit ">90% sensitivity" as a *decision*, not a hope.
--- defs:
45:class CoralHead(layers.Layer):
78:def coral_loss(label_levels, logits):
89:def grade_to_levels(y: np.ndarray) -> np.ndarray:
95:def build_model(image_size: int = 512, backbone: str = "efficientnetv2s",
117:def _find_last_conv(base: keras.Model) -> str:
125:def logits_to_cumulative(logits: np.ndarray) -> np.ndarray:
133:def cumulative_to_per_grade(cum: np.ndarray) -> np.ndarray:
146:def cumulative_to_grade(cum: np.ndarray, cuts: np.ndarray | list | None = None) -> np.ndarray:
159:def referable_probability(cum: np.ndarray) -> np.ndarray:
=========== src/grading/predict.py (     158 lines)
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
Bash Dump remaining module headers and API routes
IN
for f in src/grading/train.py src/explain/gradcam.py src/explain/icdr_rules.py src/explain/calibration.py src/explain/report.py; do echo "=========== $f ($(wc -l < $f) lines)"; head -30 "$f"; echo "--- defs:"; grep -nE "^(def |class |async def )" "$f"; done; echo "=== API ROUTES ==="; grep -nE "@app\.|@router\." src/api/main.py; echo "=== WEB ==="; ls web deploy

OUT
=========== src/grading/train.py (     177 lines)
"""Trainer. Runs unmodified as a Vertex AI custom job, a Kaggle notebook, or locally.

    python -m src.grading.train \
        --aptos-csv data/raw/aptos/train.csv \
        --aptos-images data/raw/aptos/train_images \
        --epochs 12 --batch 16 --image-size 512 --run-id run-20260911-a1

Cloud-agnostic by construction: it reads local paths, and `--gcs-out` (if given) copies
the artefacts up at the end. Nothing in here imports a Google library, which is precisely
why the Kaggle fallback cost us no code changes when the GCP billing account turned out
to be closed.

Everything a reported number depends on is written next to the weights:
`run.json` (the full config + git commit), `history.json`, `thresholds.json`,
`temperature.json`. A metric whose run cannot be reproduced is not a metric.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def git_commit() -> str:
--- defs:
30:def git_commit() -> str:
38:def main():
=========== src/explain/gradcam.py (     178 lines)
"""Requirement #4a — Grad-CAM, and the measurement that makes it defensible.

## What we explain

With a CORAL head there is no "class logit" to differentiate — there are four cumulative
logits. We explain **the referable decision**, i.e. the logit for P(grade >= 2), because
that is the output the clinic actually acts on. Explaining a softmax class score would
tell a health worker why the model said "grade 3 rather than grade 2", which is not the
question anyone is asking. This is a deliberate choice and a good answer to give.

## Why this can't run on a managed prediction endpoint

Grad-CAM needs the gradient of an output with respect to an intermediate activation. A
managed endpoint returns the output tensor and nothing else. This is the concrete reason
the model is loaded in-process inside Cloud Run rather than behind Vertex Prediction —
the explainability requirement makes the fashionable architecture impossible. It also
happens to be cheaper.

## Why we also measure it

Grad-CAM is well known to be unreliable, and "here is a pretty heatmap" is not evidence.
`attribution_mass_in_masks` computes what fraction of the heatmap's total attention falls
inside ground-truth lesion annotations, against a random-attribution control. That turns
explainability from a screenshot into a number with a baseline — see
`scripts/eval_explainability.py`.
"""
from __future__ import annotations

import cv2
import numpy as np
--- defs:
36:def _grad_model(model: tf.keras.Model, last_conv_layer: str):
41:def gradcam(model: tf.keras.Model, image_batch: np.ndarray, last_conv_layer: str,
68:def gradcam_plus_plus(model: tf.keras.Model, image_batch: np.ndarray,
102:def upsample(cam: np.ndarray, size: int) -> np.ndarray:
106:def colourise(cam: np.ndarray) -> np.ndarray:
110:def overlay(bgr: np.ndarray, cam: np.ndarray, alpha: float = 0.40,
125:def attribution_mass_in_masks(cam: np.ndarray, lesion_mask: np.ndarray) -> float:
139:def random_attribution_control(lesion_mask: np.ndarray, retina_mask: np.ndarray,
152:def attention_summary(cam: np.ndarray, lesion_raw: dict, disc: dict, fovea: dict,
=========== src/explain/icdr_rules.py (     183 lines)
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
--- defs:
46:def evaluate(lesions: dict, cnn_grade: int | None = None) -> dict:
121:def _compare(rule_grade: int, cnn_grade: int, ceiling: int) -> dict:
168:def api_block(rules: dict) -> dict:
=========== src/explain/calibration.py (     110 lines)
"""Requirement #4c — calibrated confidence.

A raw sigmoid output is not a probability. Modern deep networks are systematically
*overconfident*: a batch of predictions at "90% confident" is typically right rather less
than 90% of the time. Putting an uncalibrated number next to a medical decision is
actively dangerous, because the clinician reads it as a probability and it is not one.

**Temperature scaling** (Guo et al. 2017) is the fix: divide the logits by a single
scalar T fitted on the validation set by minimising negative log-likelihood. One
parameter, so it cannot overfit; it never changes any ranking, so accuracy, QWK, AUC and
the tuned thresholds are all mathematically unchanged. It only makes the numbers honest.

We report **ECE before and after** to prove the correction did something, and we bin by
the referable probability, because that is the number shown to the user.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))


def coral_nll(logits: np.ndarray, levels: np.ndarray, T: float) -> float:
    """Negative log-likelihood of the cumulative binary targets at temperature T."""
--- defs:
25:def _sigmoid(z):
29:def coral_nll(logits: np.ndarray, levels: np.ndarray, T: float) -> float:
37:def fit_temperature(logits: np.ndarray, levels: np.ndarray,
45:def apply_temperature(logits: np.ndarray, T: float) -> np.ndarray:
50:def expected_calibration_error(probs: np.ndarray, labels: np.ndarray,
80:def brier_score(probs: np.ndarray, labels: np.ndarray) -> float:
87:def save_temperature(path: Path, T: float, report: dict) -> None:
92:def load_temperature(path: Path) -> float | None:
101:def confidence_from_cumulative(cum_row: np.ndarray, grade: int) -> float:
=========== src/explain/report.py (     294 lines)
"""Requirement #4d — the one-page PDF an ophthalmologist signs off in under 30 seconds.

Design constraints that come from that 30-second target, not from taste:

  - **One page.** A second page means scrolling, and scrolling means the 30 seconds is
    gone. Everything that matters is above the fold of a single A4 sheet.
  - **The decision first.** Referable yes/no is the largest element on the page, top
    left, colour-coded. The grade is secondary. A reviewer should be able to triage from
    across the room.
  - **Images side by side.** The original and the Grad-CAM overlay at the same scale, so
    the eye can flick between them without re-orienting.
  - **The evidence is a table, not prose.** Counts by quadrant, and the ICDR criteria
    that fired, so the reviewer can check the reasoning rather than trust it.
  - **Disagreements are printed in a box, not buried.** If the CNN and the rules differ,
    that is the single most decision-relevant fact on the page.
  - **The disclaimer is on the page**, not in a footer nobody reads.

No metric that has not been measured appears here. Fields that are unavailable print as
"not available", never as a plausible-looking number.
"""
from __future__ import annotations

import base64
import io
from datetime import datetime, timezone

import cv2
import numpy as np
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
--- defs:
53:def _img_reader(bgr: np.ndarray) -> ImageReader:
60:def _para(text, size=8.2, colour=INK, leading=None, bold=False):
68:def build_report(result: dict, original_bgr: np.ndarray, overlay_bgr: np.ndarray | None,
293:def build_report_b64(*args, **kwargs) -> str:
=== API ROUTES ===
54:@app.on_event("startup")
65:@app.get("/health")
80:@app.get("/")
86:@app.post(f"/{API_VERSION}/analyze")
157:@app.post(f"/{API_VERSION}/review/{{scan_id}}")
167:@app.get(f"/{API_VERSION}/scans")
173:@app.get(f"/{API_VERSION}/metrics")
192:@app.get(f"/{API_VERSION}/operational")
=== WEB ===
deploy:
Dockerfile.hf
README.md

web:
app
components
lib
next-env.d.ts
next.config.js
node_modules
package-lock.json
package.json
public
tsconfig.json
vercel.json
Here's the backend map. Everything backend lives in src/ (the app) plus scripts/ (offline tools you run by hand).

1. src/common/ — shared basics
config.py — one place for every constant (ICDR grade names, folder paths, disclaimer). Fitted thresholds are read from results/, never hardcoded.
Theory: if a judge asks "where did that number come from?", it's answerable from one file.
imaging.py — turns a raw camera photo into something the model can read. Three steps in order: crop to the retina circle → Ben Graham subtraction → CLAHE on the green channel.
Theory: fundus photos are a bright circle on a black border that differs per camera. Cropping makes a cheap phone camera look dimensionally like a hospital one. Ben Graham subtracts a blurred copy of the image from itself, cancelling the camera's own lighting gradient — the trick that won the 2015 Kaggle DR competition. Green channel is used because blood absorbs green, so lesions show up strongest there.
2. src/quality/ — "is this photo even usable?"
gate.py — three independent checks: focus, illumination evenness, field of view. Each gives a number + threshold + pass/fail.
Theory: telling a health worker "bad image" is useless; "out of focus — clean the lens and retake" is actionable. Focus uses contrast-normalised Tenengrad (gradient energy) so a smooth retina isn't mistaken for a blurry one. Illumination uses variation of brightness across a 3×3 grid — a half-lit photo scores high. Thresholds are fitted to human labels, not guessed.
3. src/segment/ — classical computer vision (no AI)
structures.py — finds the optic disc and the fovea.
Theory: two reasons, both practical. The optic disc is bright and round and looks exactly like a giant exudate, so it must be masked out or the exudate detector fires every time. And the clinical 4-2-1 rule is defined by quadrant, and quadrants are measured from the disc–fovea axis.
lesions.py — detects microaneurysms, haemorrhages, hard exudates.
Theory: deliberately not a trained U-Net — IDRiD only gives 54 pixel-labelled images, so a net trained on it models 54 images, not the disease. Instead each lesion is found by its actual shape: MAs are small/round/dark/isolated (morphological closing removes vessels, which are elongated); haemorrhages are the same but bigger and irregular; exudates are bright and sharp-edged (top-hat filter). Every detection traces back to a geometric rule you can show a clinician.
4. src/grading/ — the deep-learning severity model
model.py — the network. Uses a CORAL ordinal head, not a normal 5-way softmax.
Theory: grades 0–4 are ordered. Softmax treats "said 0, truth 4" and "said 3, truth 4" as equally wrong — clinically the first blinds someone, the second is a rounding error. CORAL outputs 4 cumulative probabilities P(grade > 0…3) from shared weights + separate biases, which mathematically guarantees they stay in order. Bonus: "referable DR" (grade ≥ 2) is a single direct output with its own tunable threshold, so hitting >90% sensitivity is a decision, not luck.
data.py — builds train/validation sets and augmentation.
Theory: splits are stratified by grade with a fixed seed, because APTOS is ~half grade-0 and under 6% grade-3 — a random split leaves too few sick cases for metrics to mean anything. IDRiD is never split; it's the sealed external holdout. Augmentation is only flips/rotation/mild brightness — no colour jitter or cutout, because lesion colour is diagnostic and cutout can delete the only lesion in a mild case.
train.py — the trainer. Runs identically locally, on Kaggle, or on Vertex AI.
Theory: imports no Google libraries on purpose — which is why the Kaggle fallback cost zero code changes when GCP billing was closed. Writes config + git commit + history next to the weights, so any reported number is reproducible.
evaluate.py — metrics + the one-shot holdout protocol.
Theory: thresholds and temperature are tuned on validation only, then frozen, then the holdout opens exactly once. Reports QWK (comparable to published work), referable sensitivity/specificity with bootstrap confidence intervals (a point estimate on 103 images is nearly meaningless), and ECE.
predict.py — inference wrapper.
Theory: degrades honestly. No weights present → returns available=False, and the API still serves quality + lesions + rules with grading: null and a stated reason. The frontend never sees a fabricated grade.
5. src/explain/ — why the model said that
gradcam.py — heatmap of where the model looked.
Theory: explains the referable logit specifically, because that's the decision the clinic acts on. Also measures itself: attribution_mass_in_masks computes what fraction of the heat lands inside real lesion annotations vs a random control — turning a pretty picture into a number with a baseline. This is also why the model runs in-process rather than behind a managed endpoint: Grad-CAM needs internal gradients, which an endpoint won't give you.
icdr_rules.py — grades the image a second time from published clinical criteria, no neural net involved.
Theory: two independent estimators, and disagreements are shown, not hidden. Honest about limits: our CV can't see venous beading, IRMA or neovascularisation, so the rules report an assessable_ceiling and say "cannot confirm" rather than pretending absence of evidence is evidence of absence — which would under-grade the sickest patients.
calibration.py — temperature scaling.
Theory: deep networks are systematically overconfident — a batch marked "90% confident" is right less than 90% of the time. Dividing logits by one fitted scalar T fixes the numbers without changing any ranking (accuracy, QWK, AUC, thresholds all unchanged). ECE is reported before and after to prove it did something.
report.py — the one-page signable PDF.
Theory: built around a 30-second review target. One page, referable yes/no as the biggest element, original and heatmap side by side at the same scale, evidence as a table not prose, disagreements in a box, disclaimer on the page. Anything unmeasured prints "not available".
6. src/api/ — the web service
main.py — FastAPI app. Endpoints: /health, /v1/analyze, /v1/review/{scan_id}, /v1/scans, /v1/metrics, /v1/operational.
Theory: model loads in-process (see Grad-CAM above). Starts and answers /health with model_loaded: false when there are no weights, so the URL can be live from hour one.
pipeline.py — the single pass that produces a full analysis, in fixed order: quality gate → preprocess → grade → Grad-CAM → lesion CV → ICDR rules → PDF.
Theory: two hard rules. A photo that fails the gate is never graded — there's no "grade it anyway" path, because a confident grade on an ungradeable image is how screening programmes go wrong. And every block degrades independently — no model still returns quality + lesions + rules; Grad-CAM crashing still returns the grade.
store.py — saves scans and reviews. Firestore in the cloud, a local JSON file otherwise, same interface.
Theory: the app runs and demos with zero cloud dependencies — what let work continue while billing was closed.
Reading order if you want to follow one image through
imaging.py → gate.py → structures.py → lesions.py → model.py → gradcam.py → icdr_rules.py → report.py, with pipeline.py as the conductor tying them together.

Note: FILE_MAP.txt already exists in the repo (untracked) and covers similar ground — this answer is the backend-only, theory-first version.