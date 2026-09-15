# I need from you

Ordered by what unblocks the most.

**GCP is not on this list.** It is not part of the current architecture. Do not reopen
billing, request GPU quota, or set up Cloud Run for this build.

---

## RESOLVED

### 1. ~~Rename the project folder~~ — DONE
`/Users/ganesh/Downloads/#SIH_PROJECT` is now `/Users/ganesh/Downloads/SIH_PROJECT`.
The `#` made Next.js treat everything after it as a URL fragment. Fixed; tests pass in place.

### 2. ~~Datasets~~ — DONE
All four are downloaded locally at `~/Documents/SIH-DR/datasets/` (~22 GB):

| Dataset | Path | State |
|---|---|---|
| APTOS 2019 | `APTOS/aptos2019-blindness-detection/` | Extracted. 3,662 labelled images, loader pre-flighted ✅ |
| IDRiD | `IDRiD/` | Extracted. Grading labels + per-lesion masks (MA, HE, EX, SE, OD) |
| DRIVE | `DRIVE/datasets/` | **Still zipped** (`training.zip`, `test.zip`) |
| Messidor-2 | `Messidor-2/` | Split archives, not extracted. Out of scope (cut). |

### 3. ~~MATLAB access~~ — INSTALLED, with one gap
MATLAB R2026a on Apple Silicon. `ver` confirms MATLAB, Simulink, Computer Vision,
Deep Learning, Image Processing, Medical Imaging, Statistics & ML.

---

## OPEN — what I still need

## 1. Push the repo to GitHub, so Kaggle can clone it

**This is the top blocker.** Everything numeric is downstream of a real training run.

`notebooks/kaggle_train.py` still contains the placeholder `YOUR_ORG/YOUR_REPO`. I need
the real repo URL to wire it up.

Then, on Kaggle: New Notebook → Accelerator **GPU P100** → Internet **ON** →
Add Data → Competitions → *APTOS 2019 Blindness Detection* → paste the cells → Run All.
~2 h for 12 epochs at 512px. Launch it and walk away.

When it finishes, download `/kaggle/working/artifacts/model` and drop it into
`artifacts/model/` locally.

## 2. Run the two MATLAB scripts and paste the output

**SimEvents is not installed**, so `build_dr_workflow_model.m` cannot run. I wrote a
base-Simulink replacement, but **I have no MATLAB here and could not test it.** I need
you to run it and send me whatever appears — output or error.

```matlab
cd ~/Downloads/SIH_PROJECT/matlab/simulink
build_dr_workflow_basic      % expect: Built dr_district_workflow_basic.slx
run_sweeps_basic             % expect: min FTE with/without AI + a JSON file
```

A `WARNING` about placeholder parameters is correct and expected.

**Your MATLAB licence is a trial (DEMO).** Trials are time-limited — please check the
expiry date and tell me, so we can sequence the MATLAB work before it lapses.

The classical baseline (`dr_classical_baseline.m`) needs `split.csv` from a real training
run, so it comes after item 1.

## 3. Free hosting logins — for the public demo URL

Render (backend) + Vercel (frontend). No GCP. I will need you to click through the
account connection; I can do the configuration.

## 4. ~200 labelled images — the quality gate's real weakness

Current thresholds were fitted on 13 synthetic images. They pass **60/60 sampled real
APTOS images** — a 0% ungradeable rate, which is not credible for real screening. They
are too loose.

Label ~200 images `1` = would grade / `0` = would retake, as a `path,gradeable` CSV:

```bash
make quality-fit LABELS=<your.csv> PROVENANCE="labelled by <name>, <date>"
```

I can draw the sample from APTOS for you to label.

## 5. One number only you can source

`manual_read_s` — how long an ophthalmologist takes to grade a raw fundus photo unaided.
The FTE saving depends on it more than anything else. A sensitivity analysis across
60–240 s already exists, but a citation or a timed observation lets us state one number.

## 6. Decision: when to open the IDRiD holdout

`scripts/run_holdout.py` permanently records any override. It must be run **once**, after
everything is frozen. I will not run it without your explicit go-ahead.
