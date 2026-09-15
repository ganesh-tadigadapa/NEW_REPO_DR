# Why Kaggle GPU for the model, and where MATLAB stays

The problem statement asks for a "MATLAB-based retinal image analysis pipeline". We build a **hybrid**:
the DR grading model is trained in Python on **Kaggle GPU**, and MATLAB provides the classical-CV control
arm plus the Simulink workflow simulation. This is slide 8 of the deck. Lead with it — do not hope nobody
asks.

**Primary model-training environment: Kaggle GPU.** Free P100/T4, no approval, no billing, no spend.
`src/grading/train.py` runs there unmodified.

## What is Python and what is MATLAB — state this precisely

**Python owns the live pipeline**: quality gate, preprocessing, retinal structures, lesion analysis, the
DR grading model, inference, Grad-CAM, calibration, the ICDR consistency logic, and the FastAPI backend.
**MATLAB owns two offline deliverables**: the classical control baseline and the Simulink district
workflow simulation.

Do **not** claim MATLAB runs the live vision pipeline or the consistency check. It does not — those are
Python, in `src/quality/`, `src/segment/` and `src/explain/`. The honest framing is: *"Python trains and
serves one model and runs the live pipeline, because it has to deploy to a free public URL. MATLAB is our
control arm — the classical single-technique pipeline the problem statement asks us to beat, on identical
splits — and the Simulink model of the district screening workflow."*

## Where MATLAB stays (non-negotiable)

- **Requirement #5, the Simulink telemedicine workflow model.** An explicit deliverable, needs no GPU.
- **The classical Image Processing Toolbox baseline.** Top-hat exudates, extended-minima microaneurysms,
  matched-filter vessels, SVM grading. This is the "single technique approach" the problem statement asks
  us to outperform — our control arm, on identical splits.

## Why the CNN trains in Python on Kaggle, not in MATLAB

1. **Free GPU access.** No CUDA laptop in the room. The planned EfficientNetV2-S at 512×512 over ~3,700
   images is ~2 h on a Kaggle P100 and over a day on a laptop CPU. Kaggle costs nothing and needs no
   approval.
2. **Toolbox availability.** A licence gap discovered late is fatal. Kaggle has no licence risk.
3. **Deployability.** "Deployment in primary healthcare centres" is not answered by a model on a laptop.
   Serving MATLAB publicly needs Production Server; a Python FastAPI service deploys to free hosting.
4. **Reproducibility.** Versioned, pinned, re-runnable jobs are what "clinical validation rigour" means
   in practice.

We use **TensorFlow/Keras**. Kaggle supports it directly with no setup.

## Cost

**$0.00.** Kaggle GPU is free; hosting is free-tier. No paid cloud resource is provisioned.

## Current training status — say this plainly

**No GPU training run has happened yet.** `notebooks/kaggle_train.py` is a written, un-executed template —
it still contains the placeholder `YOUR_ORG/YOUR_REPO`. The only training that has ever run is a
23-second local CPU smoke test on 60 synthetic images (`artifacts/model/run.json`), whose predictions are
meaningless.

*Do not tell a panel we have trained on Kaggle. We have not. The honest line is: "the trainer is written
and smoke-tested; the real run is our next step."*

## The honest risk

MathWorks set this problem and their engineers are likely on the panel. A team that deletes MATLAB
entirely invites a hostile question. A team that says *"we benchmarked the MATLAB classical pipeline as
our control, built the required Simulink model, and trained the CNN in Python on a free GPU because we
had no GPU and needed a public demo"* has an answer that survives the follow-up.

---

# HISTORICAL / ALTERNATIVE ARCHITECTURE

**Not the current implementation path. Retained for reasoning, not for action.**
Do not request GCP billing, GPU quota, Vertex credentials, or Cloud Run setup.

An earlier plan trained on **Google Vertex AI** (GPU, $300 free credit) and served on **Cloud Run**.
The reasoning that is still worth keeping:

- **TensorFlow over PyTorch** was originally chosen because Vertex AI Explainable AI's managed feature
  attribution supports custom-trained TensorFlow models and not PyTorch. We cut the XRAI channel for
  time. TensorFlow remains the right choice on Kaggle independently, so nothing is lost.
- **No prediction endpoint in the hot path**, partly for cost (an endpoint bills continuously) and partly
  because Grad-CAM needs gradients an endpoint will not return. This reasoning still governs the current
  in-process design.
- **Why it was abandoned:** the GCP billing account attached to project `sih-dr-31042` is closed
  (`OPEN: False` on both accounts), so no Vertex job could ever be launched. Rather than wait on a
  billing action, the build moved to Kaggle GPU, which was always the documented fallback and needs no
  billing. The trainer package is environment-agnostic, so this cost zero code changes.
