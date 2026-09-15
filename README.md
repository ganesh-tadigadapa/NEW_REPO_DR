# SIH26038 — Explainable AI for Diabetic Retinopathy Screening

Upload a fundus photograph → ICDR grade 0–4, referable yes/no, Grad-CAM heatmap, lesion
evidence checked against the ICDR clinical rules, calibrated confidence, and a one-page
PDF an ophthalmologist signs off in under 30 seconds. A blurry image is **refused** with a
specific instruction for retaking it.

> **Screening triage aid. Not a diagnostic device.**

## New here, or not a coder? Read `GUIDE/` first

`GUIDE/00_START_HERE.md` explains this whole project in plain English with no jargon —
what it does, what each folder holds, what every number means, how to run it, and what to
say to judges. Every code folder also has a plain-English `README.md` inside it.

## Status

The pipeline is built and verified end to end. It runs today with no cloud account and no
datasets — on a model trained on **synthetic images**, which is branded as such from the
model file through the API into a warning bar in the UI. The plumbing is done; the science
is waiting on data.

**Read `docs/BLOCKERS.md` first** — four things need your accounts, and one is a 5-second
folder rename that unblocks the entire frontend.

## Run it

```bash
make setup                 # venv + npm install
make synth                 # generate test images
make api                   # http://localhost:8080
make web                   # http://localhost:3000   (see BLOCKERS.md #1 first)
make test                  # 41 tests
make smoke                 # end-to-end: expects 200 then 422
```

## The five graded requirements

| # | Requirement | Where | Evidence it produces |
|---|---|---|---|
| 1 | Image quality + enhancement | `src/quality/` | 3 checks (thresholds fitted on SYNTHETIC data — refit needed); HTTP 422 + a recapture instruction naming the failed criterion |
| 2 | Structure segmentation | `src/segment/` | optic disc, fovea, Frangi vessels (Dice vs DRIVE — *not yet measured*), lesion counts by quadrant |
| 3 | DR severity grading | `src/grading/` | CORAL ordinal head; QWK + referable sens/spec with bootstrap CIs (*code ready; no real run yet*) |
| 4 | Explainability | `src/explain/` | Grad-CAM measured against lesion masks, ICDR rule cross-check, temperature scaling, PDF |
| 5 | Simulink workflow | `matlab/` | ophthalmologist FTEs with and without AI triage |

## The decisions worth defending

- **Ordinal (CORAL) head, not softmax.** The grades are ordered, so `P(grade ≥ 2)` — the
  referral decision — is a direct model output with its own tunable threshold.
- **Contrast-normalised sharpness, not Laplacian variance.** The textbook measure
  confuses a healthy smooth retina with a blurred one and would have quietly rejected
  healthy eyes. Pinned by a test.
- **The rule engine returns *unknown*, not *absent*,** for venous beading, IRMA and
  neovascularisation, which it cannot detect. Treating those as absent would under-grade
  the sickest patients.
- **The model runs in-process, not behind a hosted prediction endpoint.** Grad-CAM needs
  gradients an endpoint will not return. Cheaper too.
- **Vessel suppression only fires on elongated structures.** Frangi at small scales treats
  a microaneurysm as a ridge; suppressing on the raw mask deleted the lesions we count.
- **No number can be faked.** The dashboard reads `/v1/metrics`; no results file means the
  UI prints "not run yet". There is no placeholder to accidentally ship.

## Layout

```
src/quality/   quality gate + enhancement        src/api/      FastAPI backend
src/segment/   disc, fovea, vessels, lesions     web/          Next.js frontend
src/grading/   CORAL model, trainer, evaluation  matlab/       Simulink + classical baseline
src/explain/   Grad-CAM, calibration, ICDR rules, PDF
results/       every run's config + metrics      docs/         contract, blockers, clock, cost
```

## Documents

| File | What it is |
|---|---|
| `docs/BLOCKERS.md` | **what I need from you**, ordered by leverage |
| `EXPLAIN_IT_BLOCK1.md` | plain-English brief for defending this to a judge |
| `docs/API_CONTRACT.md` | the frozen v1 contract both tracks build against |
| `docs/CLOCK.md` | the 36-hour plan and what is already done |
| `docs/JUSTIFICATION.md` | why Kaggle GPU for the CNN and where MATLAB stays |
| `docs/BENCHMARKS.md` | the result tables — empty cells say "not run yet" |
| `docs/COST_LOG.md` | cloud spend. Currently $0.00 — this build is free-tier only |
