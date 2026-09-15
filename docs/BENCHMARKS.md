# Benchmarks

> Every cell traces to a file under `results/`. Empty = **not run yet**. Never fill a cell from a paper
> and present it as ours. The "Theirs" column is published work and is labelled as such.

## Table 1 — vs published work (same dataset, same protocol)

| Work | Dataset | Metric | Theirs | Ours | Source file |
|---|---|---|---|---|---|
| EfficientNetB0 + attention | APTOS 2019 | QWK | ~0.92 (published) | **0.9224** (CI95 0.8991-0.9416) | `results/aptos-kaggle-run1/validation_metrics.json` |
| IDRiD challenge leaders | IDRiD | AUPR (MA / HE / EX) | published | not run yet | |
| DRIVE leaderboard | DRIVE | Dice | ~0.81 (published) | **0.6029** (Python) / **0.5523** (MATLAB) | `results/vessels/drive_metrics.json`, `..._matlab.json` |

## Table 2 — ablation: integrated pipeline vs single techniques

| Configuration | QWK | Referable sens | Referable spec | Source file |
|---|---|---|---|---|
| MATLAB classical CV baseline (control arm) | not run yet | | | |
| CNN only, raw images, softmax head | not run yet | | | |
| CNN + preprocessing + ordinal head + tuned threshold | not run yet | | | |
| **Full pipeline + quality gate + lesion-rule cross-check** | not run yet | | | |

## Table 3 — explainability, attribution mass inside IDRiD lesion masks

| Method | Fraction inside ground-truth lesions | Source file |
|---|---|---|
| Grad-CAM | not run yet | |
| Grad-CAM++ (if built) | not run yet | |
| Random-attribution baseline (control) | not run yet | |

## Operational

| Metric | Value | Source file |
|---|---|---|
| Median end-to-end latency | not run yet | |
| Ungradeable rate | not run yet | |
| Quality-gate agreement with human grader | not run yet | |
| Median clinician review time (target <30 s) | not run yet | |


## Table 4 — the real APTOS run (validation split, n=550)

> Source: `results/aptos-kaggle-run1/validation_metrics.json`. Trained on Kaggle P100,
> 12 epochs, 512px, EfficientNetV2-S + CORAL. **This is the APTOS validation split, which
> is NOT clinical validation and NOT an external holdout.** Thresholds and temperature
> were tuned on this same split, so these numbers are optimistic by construction.
> The IDRiD external holdout has NOT been run.

| Metric | Value | 95% CI |
|---|---|---|
| QWK | **0.9224** | 0.8991 – 0.9416 |
| Exact accuracy | 0.8273 | |
| Within one grade | 0.98 | |
| Referable sensitivity (grade ≥2) | **0.9238** | 0.8874 – 0.9569 |
| Referable specificity | **0.9297** | 0.9 – 0.9545 |
| Referable AUC | 0.9753 | |
| PPV / NPV | 0.8996 / 0.947 | |

SIH targets: sensitivity >90% **met (0.9238)**, specificity >85% **met (0.9297)** —
*on the validation split only, with thresholds tuned on that split.*

### Per-class (derived from the confusion matrix)

| Grade | n | Precision | Recall | F1 |
|---|---|---|---|---|
| 0 No DR | 271 | 0.996 | 0.982 | 0.989 |
| 1 Mild | 56 | 0.611 | 0.589 | 0.600 |
| 2 Moderate | 150 | 0.738 | 0.807 | 0.771 |
| 3 Severe | 29 | 0.258 | 0.276 | **0.267** |
| 4 PDR | 44 | 0.794 | 0.614 | 0.692 |

**Grade 3 is the weak class (F1 0.267, n=29).** Say this before a judge finds it.

### Calibration (temperature scaling on the validation split)

| | before | after |
|---|---|---|
| ECE | 0.03513 | 0.03284 |
| MCE | 0.3473 | 0.27349 |
| Brier | 0.05787 | 0.05777 |

T = 0.9879 — the model was already close to calibrated, so scaling changes little.


---

# FINAL BENCHMARK SUMMARY

Every number below traces to a file under `results/`. Nothing is estimated.

## The headline table — validation vs external holdout

| Metric | APTOS validation (n=550) | **IDRiD external holdout (n=103)** |
|---|---|---|
| QWK | 0.9224 (0.8991–0.9416) | **0.6934** (0.5921–0.7687) |
| Exact accuracy | 0.8273 | **0.4078** |
| Within one grade | 0.98 | 0.8932 |
| Referable sensitivity (≥2) | 0.9238 | **0.8594** (0.7681–0.9375) |
| Referable specificity | 0.9297 | **0.8974** (0.8–0.9762) |
| Referable AUC | 0.9753 | 0.9151 |

Source: `results/aptos-kaggle-run1/validation_metrics.json`, `holdout_metrics.json`.
Holdout run once, logged in `results/holdout_ledger.json` (fingerprint `b608ec0742b692db`).

## SIH targets — state it this way

| Target | Validation | **External (the one that counts)** |
|---|---|---|
| Referable sensitivity > 90% | 0.9238 ✅ | **0.8594 ❌ NOT MET** |
| Referable specificity > 85% | 0.9297 ✅ | **0.8974 ✅ met** |

The validation figures are tuned on themselves — thresholds and temperature were
fitted on that split. **The external result is the honest one: sensitivity 0.8594,
below target, with the CI reaching 0.7681. Nine of 64 referable cases were missed.**
No threshold was adjusted to chase the target.

## Why the gap — the per-class evidence

| Grade | Validation F1 | Holdout F1 | Holdout recall |
|---|---|---|---|
| 0 No DR | 0.989 | 0.311 | **0.206** |
| 1 Mild | 0.600 | 0.105 | 0.400 |
| 2 Moderate | 0.771 | 0.622 | 0.719 |
| 3 Severe | 0.267 | 0.333 | 0.263 |
| 4 PDR | 0.692 | 0.526 | 0.385 |

Grade-0 recall collapses from 0.982 to 0.206: 24 of 34 healthy IDRiD eyes were graded 1.
The model systematically over-grades on this domain. Grade 3 is weak in both.

## Classical vision — both implementations against ground truth

| Component | Python (deployed) | MATLAB (reference) | Ground truth |
|---|---|---|---|
| Vessel Dice (DRIVE, n=20) | **0.6029** | **0.5523** | coverage 0.1254 |
| Optic disc error (IDRiD, n=60) | 29.4 px, 96.7% within 1 DR | 36.9 px, 96.7% within 1 DR | — |
| Fovea error (IDRiD, n=60) | 152.3 px, 50.0% within 1 DR | 157.8 px, 11.7% within 1 DR | — |

Quality-metric port fidelity, MATLAB vs Python on identical arrays: **0.00000000%**
deviation on focus and illumination (`results/matlab_agreement.json`).

## Operational, measured on 80 held-out images

| Metric | Value |
|---|---|
| Median end-to-end latency | 2067 ms (no report/images), 4.3–6.7 s full |
| **Ungradeable rate** | **0.0** ← see defect below |
| Images needing a human | **0.725** |
| Flags | 21 agree · 33 referral-disagree · 19 severity-disagree · 7 rules-cannot-confirm |

## Workflow simulation (base Simulink, measured rates)

1 ophthalmologist with AI triage vs 3 without → **2 FTEs saved per 100k diabetics**.
Driven by AI-assisted review at 18.2 s vs 120 s unaided, *not* by filtering images away.
`manualReadSeconds` remains the one unmeasured input. Source: `results/simulation/simulink_sweep.json`.

## Three known defects — say these before a judge finds them

1. **Quality gate refuses nothing on real data** — 1 of 550 validation and 0 of 400 test
   images. Thresholds were fitted on 13 synthetic images. The recapture demo works only
   because one genuinely blurred image exists in the validation split and because the
   field-of-view sample was cropped on purpose.
2. **The ICDR rule engine disagrees with the CNN on 4 in 10 images**, so the consistency
   check escalates 72.5% rather than the ~28% assumed. Safe, but it means the AI clears
   far less work than the headline FTE number suggests.
3. **External sensitivity is 0.8594, below the 90% target**, and grade-0 recall falls to
   0.206 on IDRiD.


## Quality gate — refitted on real images

Thresholds fitted on 140 real APTOS images with controlled degradations, evaluated on a
**disjoint held-out 60** (split by source image, so no retina spans both).
Source: `results/quality_gate/thresholds.json`, `results/quality_gate/heldout_eval.json`.

| | before (synthetic-fitted) | **after (real-fitted)** |
|---|---|---|
| Recall (ungradeable caught) | 0.4444 | **0.8889** |
| Specificity (gradeable kept) | 1.0000 | **0.7917** |
| Precision | — | 0.8649 |
| F1 | — | 0.8767 |
| Accuracy | — | 0.85 |
| **False accept rate** | 0.5556 | **0.1111** |
| **False reject rate** | 0.0000 | **0.2083** |

Confusion (positive = ungradeable): TP 32 · FN 4 · FP 5 · TN 19

| Defect | before | **after** |
|---|---|---|
| Focus | 1/14 | **11/14** (0.7857) |
| Field of view | 15/15 | **15/15** (1.0) |
| Illumination | 0/7 | **6/7** (0.8571) |

Fitted thresholds: focus ≥ 94.127 · illumination CV ≤ 0.254 · FOV fraction ≥ 0.6042.

### What the labels are — do not overstate this

**Ground truth by construction, NOT human grading.** No clinician labelled these. Every
ungradeable row is a real APTOS photograph with one controlled degradation applied by
`scripts/make_quality_labelset.py` (seed 4242). Two caveats travel with every number above:

1. Synthetic degradation may not transfer to natural degradation — real defocus is not
   exactly a Gaussian blur.
2. The gradeable class assumes unmodified APTOS images are gradeable. APTOS is noisy and
   some genuinely are not, so **reported specificity is a lower bound**.

~200 human-labelled real captures remains the correct fix and is still open.

### The cost, stated plainly

**A 20.8% false-reject rate.** Roughly 1 in 5 good images is now refused, and all 5 false
rejects in the held-out set fired on the focus check, whose classes genuinely overlap
(fitted Youden J only 0.5025). The threshold was not hand-tuned to soften this. Youden's
J was the pre-committed criterion, and the clinical asymmetry supports the direction: a
false reject costs a recapture while the patient is still present; a false accept means
grading an unreadable image.

### Recapture advice — a real bug this work exposed

On 33 illumination-degraded images, **29 tripped both focus and illumination and none
tripped illumination alone**. Severe one-sided darkening lowers gradient energy, so
uneven lighting produces a spurious focus failure. The old severity ordering therefore
told the operator to *clean the lens* for essentially every lighting fault. The gate now
names lighting as the likely root cause when both fail together. Pinned by a test.


---

# ABLATION — does the integrated pipeline beat a single technique?

The problem statement asks for exactly this. All rows use the **identical** 3112/550
split (`artifacts/model/split_local.csv`), so the comparison is like-for-like.

| Configuration | QWK | Referable sens | Referable spec | Source |
|---|---|---|---|---|
| **1. MATLAB classical CV + SVM** (control arm) | **0.5378** | 0.7040 | 0.8716 | `results/ablation/classical_baseline_metrics.json` |
| 2. CNN only, raw images, softmax head | *not run* | | | would need a second GPU training run |
| **3. CNN + preprocessing + CORAL + tuned threshold** | **0.9224** | 0.9238 | 0.9297 | `results/aptos-kaggle-run1/validation_metrics.json` |
| **4. Row 3 + quality gate** (ungradeable excluded) | 0.9187 | 0.918 | 0.9349 | `results/ablation/quality_gated_eval.json` |

## Row 1 — the control arm, and what it establishes

MATLAB Image Processing + Statistics & ML only: top-hat exudates, extended-minima
microaneurysms, matched-filter vessels, 9 features, RBF SVM via `fitcecoc`. Ran on all
3662 images, ~70 minutes.

**The integrated pipeline beats it decisively: QWK 0.5378 → 0.9224 (+0.3846),
referable sensitivity 0.7040 → 0.9238 (+0.2198).**
That is the clause the problem statement explicitly demands, and it is now evidenced.

The classical confusion matrix shows *why* it fails: it predicts grade 3 for **zero**
images and grade 4 for only 3 of 550. Hand-crafted lesion counts cannot separate severe
from moderate disease — it collapses everything into grades 0–2. A low control-arm score
is the expected and desirable outcome here; it is what the CNN has to beat.

## Row 4 — an honest negative result

Applying the quality gate **does not improve grading performance on APTOS**. It refuses
**106 of 550 images (19.3%)** and the metrics on what remains are essentially unchanged,
slightly worse on two of three:

| | without gate | with gate |
|---|---|---|
| QWK | 0.9224 | 0.9187 |
| Referable sensitivity | 0.9238 | 0.918 |
| Referable specificity | 0.9297 | 0.9349 |

If the gate were refusing genuinely harder images, accuracy on the remainder should rise.
It does not. On APTOS the images it rejects are no harder to grade than the ones it keeps,
which is direct evidence that **the gate is over-rejecting** — consistent with the 20.8%
false-reject rate measured independently on the held-out quality set.

Do not claim the quality gate improves accuracy. Its defensible justification is
operational, not statistical: in the field it prevents a confident grade being issued on
an unreadable capture, and it tells the operator how to retake. On a curated dataset like
APTOS that benefit does not show up as a metric gain.

## Row 2 — why it is missing

A CNN with a softmax head on raw images requires a second full GPU training run. The
model is frozen and the instruction was not to retrain, so this row is honestly left
empty rather than estimated.
