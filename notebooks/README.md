# Training notebooks

## `kaggle_train.py` — the intended path, NOT YET RUN

> **Status: never executed.** This file is a template. It still contains the placeholder
> `YOUR_ORG/YOUR_REPO`. No Kaggle run, artifact or log exists anywhere in this repo.
> Do not describe this as a completed training path.

`python notebooks/kaggle_train.py` prints the cells to paste into a Kaggle notebook.
Free P100, no approval, no billing. ~2 hours for 12 epochs at 512px.

Kaggle GPU is the primary training environment for this build. GCP/Vertex is not part of
the current architecture — see the historical section below and `docs/JUSTIFICATION.md`.

## HISTORICAL / ALTERNATIVE ARCHITECTURE — Vertex AI

**Not the current path.** Kaggle GPU is the primary and only training environment for this
build. Do not request GCP billing or GPU quota. Retained for reference only.

```bash
gcloud ai custom-jobs create \
  --region=us-central1 --display-name=dr-run-1 \
  --worker-pool-spec=machine-type=n1-standard-8,replica-count=1,\
accelerator-type=NVIDIA_TESLA_T4,accelerator-count=1,\
executor-image-uri=us-docker.pkg.dev/vertex-ai/training/tf-gpu.2-16.py310:latest,\
local-package-path=.,python-module=src.grading.train \
  --args=--aptos-csv=/gcs/BUCKET/aptos/train.csv,\
--aptos-images=/gcs/BUCKET/aptos/train_images,\
--out=/gcs/BUCKET/artifacts/model,--epochs=12
```

**State the cost before running it:** `n1-standard-8` + 1×T4 ≈ **$0.73/hr** in
us-central1. A 2-hour run ≈ **$1.50**. Log it in `docs/COST_LOG.md`.

Never create a Vertex **prediction endpoint** — it bills continuously, and Grad-CAM needs
gradients it will not return anyway.
