# The 36-hour clock

**Start time:** _not started — this is the pre-work build_
**Current block:** pre-work, substantially complete

## What is already built and verified

Everything below runs today, on this machine, with no cloud account.
**Primary training environment: Kaggle GPU. GCP is not part of this build.**

- [x] Repo, venv (Python 3.11), **41 passing tests** (verified), Makefile
- [x] **Quality gate** — 3 checks, fitted-threshold pipeline, actionable recapture messages
- [x] **Preprocessing** — retina crop, Ben-Graham, CLAHE; one shared transform for train + serve
- [x] **Landmarks** — optic disc, fovea, disc–fovea quadrant assignment
- [x] **Lesion CV** — MA / haemorrhage / exudate detection, verified against planted
      ground truth; Frangi vessel suppression restricted to elongated structures
- [x] **Vessel eval** — `scripts/eval_vessels.py`, Dice vs DRIVE (needs the dataset)
- [x] **Grading model** — CORAL ordinal head; save/load verified bit-identical. Code defaults to
      EfficientNetV2-S @ 512px, but the **shipped weights are efficientnetv2b0 @ 128px** (smoke run only)
- [x] **Trainer** — written to run on Kaggle GPU or locally unmodified; **only ever run locally on CPU**
      (60 synthetic images, 23 s). Never executed on a GPU
- [x] **Grad-CAM + Grad-CAM++** — verified to produce gradients through the CORAL head
- [x] **Calibration** — temperature scaling, verified to recover an injected distortion exactly
- [x] **ICDR rule engine** — 4-2-1 rule, honest "cannot assess" for beading/IRMA/NVD
- [x] **PDF report** — one page, visually checked
- [x] **API** — all endpoints against the frozen contract; 422 refusal path working
- [x] **Frontend** — 6 routes, builds clean, renders (folder-name bug resolved)
- [ ] **Simulink model + classical baseline** — written, **not yet executed**. MATLAB R2026a is now
      installed but has **no SimEvents**, so a base-Simulink replacement was written and is still untested
- [x] **Workflow simulation** — runs; AI cuts human workload to 26.8% of images
- [x] **Container** — linux/amd64 image (2.53 GB on disk), verified serving the whole
      pipeline. Deployment target is now **free hosting (Render/Vercel)**, not Cloud Run

## Blocks

- [x] **Pre-work** — repo, scaffold, everything above
- [ ] **A** 0–2 — **GitHub push → Kaggle GPU training run #1** (docs/BLOCKERS.md 1) · free-hosting deploy
- [ ] **B** 2–5 — launch training run #1 · label 200 images for the quality gate
- [ ] **C** 5–10 — run #1 lands → `make freeze` · real model wired into the live API
- [ ] **D** 10–13 — classical baseline in MATLAB (needs split.csv from run #1) · lesion overlay tuning
- [ ] **E** 13–17 — launch run #2 (ablation rows)
- [ ] **F** 17–21 — explainability eval on IDRiD masks · review screen timing data
- [ ] **G** 21–26 — **SLEEP, staggered.** One person babysits the job.
- [ ] **H** 26–29 — **IDRiD holdout, ONCE** (`make holdout`) · mobile pass
- [ ] **I** 29–32 — base-Simulink model executed with measured params · **app feature freeze**
- [ ] **J** 32–35 — ablation + benchmark tables, deck, demo video
- [ ] **K** 35–36 — rehearse ×3, buffer

## Blocked on the lead

See `docs/BLOCKERS.md`. The short version: **push the repo to GitHub** so Kaggle can clone it,
and **run the two MATLAB scripts** and paste the output. Datasets are downloaded; MATLAB is installed.

## Reminders

- [ ] No hosted prediction endpoint is created (Grad-CAM needs gradients an endpoint will not return)
- [ ] Re-run `make params` after real traffic, before quoting simulation numbers
- [ ] MATLAB licence is a **trial** — confirm the expiry date and finish MATLAB work before it lapses
