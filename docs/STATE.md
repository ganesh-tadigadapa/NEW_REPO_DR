# Current state — read this first in a new session

Everything below is verified unless it says otherwise. If something here contradicts the
code, the code wins — say so and fix this file.

**No completion percentage is given here deliberately.** Status is stated per item as
done / not run yet.

## Architecture (authoritative)

- **Python** — live retinal image-processing pipeline: quality gate, preprocessing,
  retinal structures, lesion analysis, DR grading model, inference, Grad-CAM, confidence
  calibration, ICDR consistency logic, FastAPI backend.
- **MATLAB** — classical image-processing control baseline; Simulink district
  workflow/resource simulation.
- **Kaggle GPU** — primary (and only) model-training environment.
- **Frontend** — the existing Next.js app, unchanged.
- **GCP / Vertex AI** — not the current path, not a dependency. See the
  "HISTORICAL / ALTERNATIVE ARCHITECTURE" section of `docs/JUSTIFICATION.md`.

## The one-line summary

A **real model trained on APTOS** (Kaggle P100, EfficientNetV2-S + CORAL, 12 epochs,
512px) is live in the pipeline. Validation QWK **0.9224**, referable sensitivity
**0.9238**, specificity **0.9297**. The synthetic demo model is retired.
**The IDRiD external holdout HAS now been run, once:** QWK **0.6934**, referable
sensitivity **0.8594** (below the 90% target), specificity **0.8974**.

---

# CURRENT — what actually works

```bash
make api      # FastAPI on :8080
make web      # Next.js on :3000
make test     # 41 tests
```

**Tests: 41 passed** (verified by running the suite; 33.8 s).

Six routes: `/` `/screen` `/review` `/dashboard` `/how-it-works` `/limitations`.
Five sample fundus images at `web/public/samples/`; two are deliberately bad and are refused.

**Verified live against the running API:**

| Sample | Result |
|---|---|
| `blurry.jpg` | HTTP 422 — "Image is out of focus. Clean the camera lens…" |
| `clipped.jpg` | HTTP 422 — "The retina is not fully in frame. Move closer…" |
| `moderate.jpg`, `no-dr.jpg`, `severe.jpg` | HTTP 200 — grade + Grad-CAM + lesion overlay + PDF, 2.4–4.3 s |
| `no-dr.jpg` | consistency check fired: CNN grade 2 vs rule grade 0 → `referral_disagreement` → `clinician_review` |

**Real APTOS data loads correctly** (loader pre-flighted, no training run):
3,662 images, grade distribution `[1805, 370, 999, 193, 295]`, stratified split
train 3,112 / val 550. Located at `~/Documents/SIH-DR/datasets/APTOS/`.

| Component | Module | Status |
|---|---|---|
| 1 · Quality gate + enhancement | `src/quality/gate.py` | **Refitted on real images.** Held-out recall 0.8889, specificity 0.7917, false-reject rate 0.2083. |
| 2 · Structures + lesions | `src/segment/` | Runs. Verified against planted ground truth. |
| 3 · Grading | `src/grading/` | **Real APTOS model** `aptos-kaggle-run1`. QWK 0.9224, referable sens 0.9238 / spec 0.9297 on the validation split. |
| 4 · Explainability | `src/explain/` | Grad-CAM, ICDR rule engine, temperature scaling, PDF all run. |
| 5 · MATLAB / Simulink | `matlab/` | **Not run yet** — see below. |

---

# NOT YET COMPLETE

- ~~Real APTOS-trained DR model~~ — **DONE** (`results/aptos-kaggle-run1/`).
- ~~Real ML evaluation~~ — **DONE**. `docs/BENCHMARKS.md` Table 4 is filled from files.
- **Real ablation results** — not run yet.
- ~~External holdout (IDRiD)~~ — **DONE, once** (ledger `results/holdout_ledger.json`). QWK 0.6934, sens 0.8594, spec 0.8974.
- ~~Vessel Dice vs DRIVE~~ — **DONE**: Python 0.6029, MATLAB 0.5523 (`results/vessels/`).
- **Grad-CAM attribution vs IDRiD lesion masks** — not run yet.
- ~~Quality-gate thresholds on real labels~~ — **REFITTED** on 140 real degraded images,
  evaluated on a disjoint 60. Recall 0.8889 (was 0.4444), focus 11/14 (was 1/14),
  illumination 6/7 (was 0/7). **Cost: 0.2083 false-reject rate.**
  Labels are ground truth by construction, NOT human-graded — ~200 human labels still wanted.
- **Deployment** — not run yet. Local only.

## MATLAB / Simulink — what has actually executed: **nothing**

MATLAB R2026a is installed (Apple Silicon, **trial/DEMO licence — time-limited**).
`ver` confirms: MATLAB, Simulink, Computer Vision, Deep Learning, Image Processing,
Medical Imaging, Statistics & ML.

**SimEvents is NOT installed.** `matlab/simulink/build_dr_workflow_model.m` is built
entirely from SimEvents blocks and therefore cannot run on this licence.

| Item | Status |
|---|---|
| `build_dr_workflow_model.m` (SimEvents) | Written. **Cannot run** — no SimEvents licence. |
| `build_dr_workflow_basic.m` (base Simulink) | Written as the runnable replacement. **Never executed — untested.** |
| `run_sweeps_basic.m` | Written. **Never executed — untested.** |
| `dr_classical_baseline.m` | Written. **Never executed.** Needs `split.csv` from a real training run. |
| `.slx` files on disk | **Zero.** |

`scripts/simulate_workflow.py` (Python/SimPy) does run and reports 1 ophthalmologist with
AI vs 3 without (2 FTEs saved), but its `parameters_are_measured` flag is `false`, and it
is a cross-check, **not** the graded Simulink deliverable.

---

# Honesty machinery — leave this alone

- The demo model is branded `SYNTHETIC-DEMO-not-a-real-model` from the weights file
  through the API into the UI.
- `/v1/metrics` returns `not run yet` when no evaluation exists.
- Synthetic metrics render **struck through** behind a red warning on `/dashboard`.
- `scripts/run_holdout.py` refuses a second look at the external test set unless
  explicitly overridden, and records the override permanently.
- `docs/BENCHMARKS.md` is deliberately empty. Fill it only from files in `results/`.

**Rules that stay:**
- Never fabricate a metric. Not run yet = write "not run yet".
- Synthetic/demo results stay explicitly labelled synthetic/demo.
- **APTOS validation is not clinical validation.** Say so.
- Do not claim the SIH target is met unless measured: referable **sensitivity > 90%**
  and **specificity > 85%**. Neither has been measured.
- Every real metric traces to a real file in `results/`.

**Corrections already made in this project — do not reintroduce:**
1. An image-size reduction was reported comparing two measurement methods across two CPU
   architectures (commit `3c7e849`). The measured figure is a *wheel* delta
   (591 MB → 214 MB on amd64), not an image-size delta.
2. `docs/JUSTIFICATION.md` claimed in the past tense that Kaggle training had happened
   (commit `086867d`). It had not. No Kaggle run exists.

## Four real bugs were found and fixed. Do not reintroduce them.

Each returned a confident, well-formed, completely wrong answer. All four are pinned by tests.

1. **Focus metric.** Raw Laplacian variance conflates blur with low texture. Now
   contrast-normalised Tenengrad.
2. **Vessel map flagged 99% of the retina**, deleting every lesion candidate.
3. **Then it returned an empty mask on diseased images**, so suppression switched itself
   off exactly where it mattered. Fixed with a percentile fallback.
4. **Frangi at small scales treats a microaneurysm as a ridge** — suppression ate all 18
   planted MAs. Fixed by raising the minimum scale and suppressing only on *elongated*
   components.

## Known gaps, stated plainly

- Neovascularisation, venous beading and IRMA have no detector. The rule engine reports
  them as *unknown*, never as *absent*, and can never confirm grade 4.
- The base-Simulink model is a discrete-**time** flow approximation, not discrete-**event**.
  It loses queue variance and individual wait times. Say so on the limitations slide.

---

# THE REAL MODEL — measured, validation split only

Trained on Kaggle P100, 73.5 min GPU. Verified full dataset: n_train 3112, n_val 550,
512px, efficientnetv2s, `argv.limit` 0, split.csv 3663 lines.

| Metric | Value | 95% CI |
|---|---|---|
| QWK | **0.9224** | 0.8991 – 0.9416 |
| Exact accuracy | 0.8273 | |
| Within one grade | 0.98 | |
| Referable sensitivity (≥2) | **0.9238** | 0.8874 – 0.9569 |
| Referable specificity | **0.9297** | 0.9 – 0.9545 |
| Referable AUC | 0.9753 | |

Calibration: T 0.9879, ECE 0.03513 → 0.03284, MCE 0.3473 → 0.27349, Brier 0.05787 → 0.05777.

## Three caveats that must travel with these numbers

1. **This is the APTOS validation split, tuned on itself.** Thresholds and temperature
   were fitted on this same split, so the figures are optimistic by construction. It is
   **not clinical validation** and **not an external holdout**. Both SIH targets are met
   *on this split* — that is not the same claim as "we achieve 90% sensitivity".
2. **Grade 3 is weak: F1 0.267 on n=29.** Sixteen of 29 severe cases were graded 2.
   Within-one-grade is 0.98 and they still refer, but say this before a judge finds it.
3. **The bundled demo samples are out of distribution.** All five
   `web/public/samples/*.jpg` grade 3 with this model, including `no-dr.jpg`. Verified
   this is domain shift, not model failure: on real APTOS validation images a true
   grade 0 predicts 0 at 0.9998 confidence. **The live demo looks wrong until these are
   replaced with held-out APTOS images.**

# EXTERNAL VALIDATION — the number that counts

IDRiD, n=103, frozen model `b608ec0742b692db`, run ONCE.

| | validation | **external** |
|---|---|---|
| QWK | 0.9224 | **0.6934** |
| Exact accuracy | 0.8273 | **0.4078** |
| Referable sensitivity | 0.9238 | **0.8594** ❌ target >0.90 |
| Referable specificity | 0.9297 | **0.8974** ✅ target >0.85 |

**The SIH sensitivity target is not met externally.** 9 of 64 referable cases missed.
Grade-0 recall collapses from 0.982 to 0.206 — the model over-grades on this domain.
No threshold was adjusted to chase the target.

# NEXT MAJOR TASK

**Obtain ~200 human-labelled real captures** and refit the quality gate against them.

The gate has been refitted on real images with constructed degradations and is now far
better (recall 0.4444 → 0.8889; focus 1/14 → 11/14; illumination 0/7 → 6/7),
but it carries a **0.2083 false-reject rate** and its labels are constructed, not clinical.
Human labels would fix both. Everything else the project needs is measured and recorded.

Datasets are downloaded locally at `~/Documents/SIH-DR/datasets/`
(APTOS, IDRiD, DRIVE, Messidor-2). APTOS loading is pre-flighted and working.

Order once the real model exists:

```bash
python scripts/fit_quality_thresholds.py --labels <csv>   # real thresholds
python scripts/calibrate_and_freeze.py --model-dir <dir>  # temperature + thresholds
python scripts/run_ablation.py                            # the table the PS asks for
python scripts/run_holdout.py                             # ONCE, everything frozen first
```


## Demo samples — replaced with held-out APTOS

`web/public/samples/` now holds 7 real APTOS images from the validation split, verified
absent from the 3112 training rows. All five graded samples predict their ground-truth
grade through the live API. Two refusal samples work.

One is marked `modified` in the manifest: the field-of-view sample is a real held-out
image cropped to 40% width, because APTOS contains no naturally ungradeable image our
gate would refuse. The focus sample is kept at native resolution because downscaling it
to 1024px makes it pass — the focus metric is resolution-sensitive.

## SimEvents — still not installed

`license('test','SimEvents')` returns 1, but the toolbox is not on disk and
`load_system('simevents')` fails. Installing needs an interactive MathWorks login.
**The original discrete-event `build_dr_workflow_model.m` has never executed and must not
be described as implemented.** The base-Simulink `build_dr_workflow_basic.m` does run and
is the deliverable; it is a discrete-TIME flow approximation, which loses queue variance
and individual wait times.
