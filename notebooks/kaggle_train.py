"""Kaggle notebook trainer — paste this into one cell and run.

This is the PRIMARY training path right now, because the GCP billing account is closed
(docs/BLOCKERS.md #2). Kaggle gives a free P100/T4 with no approval and no billing, and
`src/grading/train.py` runs on it unmodified — which is the whole point of having kept
the trainer cloud-agnostic.

SETUP (2 minutes)
  1. kaggle.com -> Create -> New Notebook
  2. Settings -> Accelerator -> GPU P100
  3. Settings -> Internet -> ON
  4. Add Data -> Competitions -> "APTOS 2019 Blindness Detection"
  5. Paste this whole file into one cell, set REPO to your GitHub URL, Run All

At the end it writes /kaggle/working/artifacts/model — download that directory, drop it
into artifacts/model locally, restart the API, and the real model is live.

RUNTIME: ~2 hours for 12 epochs at 512px on a P100. Launch it, then go build something
else. Never sit and watch the logs.
"""

SETUP = r"""
!git clone -q https://github.com/YOUR_ORG/YOUR_REPO.git /kaggle/working/repo || true
%cd /kaggle/working/repo
!pip install -q opencv-python-headless==4.10.0.84 scikit-image==0.24.0 2>/dev/null
import sys; sys.path.insert(0, '/kaggle/working/repo')
"""

TRAIN = r"""
!python -m src.grading.train \
    --aptos-csv    /kaggle/input/aptos2019-blindness-detection/train.csv \
    --aptos-images /kaggle/input/aptos2019-blindness-detection/train_images \
    --image-ext .png \
    --out /kaggle/working/artifacts/model \
    --run-id kaggle-run-1 \
    --image-size 512 \
    --batch 16 \
    --epochs 12
"""

FREEZE = r"""
!python scripts/calibrate_and_freeze.py --model-dir /kaggle/working/artifacts/model
!cat /kaggle/working/artifacts/model/FROZEN.json
"""

PACKAGE = r"""
# zip the artefacts so they come down as one file from the notebook Output tab
!cd /kaggle/working && zip -qr model_artifacts.zip artifacts/model \
    -x '*/val_logits.npz'   # keep this one separate, it is small but wanted locally
!cp /kaggle/working/artifacts/model/val_logits.npz /kaggle/working/
!ls -lh /kaggle/working/*.zip /kaggle/working/*.npz
"""

if __name__ == "__main__":
    print(__doc__)
    for name, cell in [("SETUP", SETUP), ("TRAIN", TRAIN),
                       ("FREEZE", FREEZE), ("PACKAGE", PACKAGE)]:
        print(f"\n{'='*70}\n# CELL: {name}\n{'='*70}{cell}")
