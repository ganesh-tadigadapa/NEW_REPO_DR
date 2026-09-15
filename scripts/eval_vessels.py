"""Vessel segmentation, measured against DRIVE ground truth.

Completes the evidence column for requirement #2. Our vessel map exists primarily to
*suppress* vessels in the dark-lesion detectors — a vessel cross-section and a
haemorrhage look identical to an intensity threshold — so this is an honest measurement
of a supporting component, not a claim to compete with the DRIVE leaderboard.

State that framing when reporting the number. Published supervised methods reach ~0.80
Dice on DRIVE; an unsupervised Frangi filter reaching materially less is the expected
result and is not a failure, because it is doing a different job. What would be a failure
is over- or under-segmenting so badly that lesion suppression breaks — which is what the
coverage guard in vessel_map() protects against, and what this script would reveal.

    python scripts/eval_vessels.py \
        --images data/raw/drive/test/images \
        --masks  data/raw/drive/test/1st_manual \
        --fov    data/raw/drive/test/mask
"""
from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from src.common.config import RESULTS_DIR
from src.segment.lesions import vessel_map

SIZE = 1024


def _read_gray(p: Path):
    img = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
    if img is None:                      # DRIVE ships .gif, which OpenCV cannot read
        try:
            from PIL import Image
            img = np.array(Image.open(p).convert("L"))
        except Exception:
            return None
    return img


def _match(directory: Path, stem: str):
    key = stem.split("_")[0]
    for q in sorted(directory.iterdir()):
        if q.name.startswith(key):
            return q
    return None


def dice(pred: np.ndarray, truth: np.ndarray) -> float:
    inter = float((pred & truth).sum())
    denom = float(pred.sum() + truth.sum())
    return 2 * inter / denom if denom else 1.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--masks", required=True, help="manual vessel annotations")
    ap.add_argument("--fov", default="", help="field-of-view masks (optional)")
    a = ap.parse_args()

    img_dir, mask_dir = Path(a.images), Path(a.masks)
    fov_dir = Path(a.fov) if a.fov else None
    rows = []

    for q in sorted(img_dir.iterdir()):
        if q.suffix.lower() not in (".tif", ".tiff", ".png", ".jpg", ".gif"):
            continue
        bgr = cv2.imread(str(q))
        if bgr is None:
            from PIL import Image
            bgr = cv2.cvtColor(np.array(Image.open(q).convert("RGB")), cv2.COLOR_RGB2BGR)
        gt_path = _match(mask_dir, q.stem)
        if gt_path is None:
            continue
        gt = _read_gray(gt_path)
        if gt is None:
            continue

        bgr = cv2.resize(bgr, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
        gt = cv2.resize(gt, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST) > 127

        if fov_dir and fov_dir.is_dir():
            fp = _match(fov_dir, q.stem)
            fm = _read_gray(fp) if fp else None
            retina = (cv2.resize(fm, (SIZE, SIZE), interpolation=cv2.INTER_NEAREST) > 127
                      if fm is not None else np.ones((SIZE, SIZE), bool))
        else:
            retina = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) > 10

        pred = vessel_map(bgr, retina) & retina
        gt = gt & retina

        tp = int((pred & gt).sum()); fp_ = int((pred & ~gt).sum())
        fn = int((~pred & gt).sum()); tn = int((~pred & ~gt & retina).sum())
        rows.append({
            "image": q.name,
            "dice": round(dice(pred, gt), 4),
            "sensitivity": round(tp / max(tp + fn, 1), 4),
            "specificity": round(tn / max(tn + fp_, 1), 4),
            "predicted_coverage": round(float(pred[retina].mean()), 4),
            "truth_coverage": round(float(gt[retina].mean()), 4),
        })
        print(f"  {q.name}: dice {rows[-1]['dice']}")

    if not rows:
        raise SystemExit("no image/annotation pairs matched — check the directory layout")

    def mean(k):
        return round(float(np.mean([r[k] for r in rows])), 4)

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "unsupervised multiscale Frangi vesselness + Otsu, coverage-guarded",
        "n_images": len(rows),
        "mean_dice": mean("dice"),
        "mean_sensitivity": mean("sensitivity"),
        "mean_specificity": mean("specificity"),
        "mean_predicted_coverage": mean("predicted_coverage"),
        "mean_truth_coverage": mean("truth_coverage"),
        "framing": ("This component exists to suppress vessels in the dark-lesion "
                    "detectors, not to compete on DRIVE. Supervised published methods "
                    "reach ~0.80 Dice; an unsupervised filter scoring below that is the "
                    "expected result for a different task. Compare predicted vs truth "
                    "coverage: a large gap is what would actually break lesion counting."),
        "per_image": rows,
    }
    d = RESULTS_DIR / "vessels"; d.mkdir(parents=True, exist_ok=True)
    (d / "drive_metrics.json").write_text(json.dumps(out, indent=2))
    print(f"\nmean Dice {out['mean_dice']}  sens {out['mean_sensitivity']}  "
          f"spec {out['mean_specificity']}")
    print(f"coverage: predicted {out['mean_predicted_coverage']} vs truth "
          f"{out['mean_truth_coverage']}")
    print(f"wrote {d/'drive_metrics.json'}")


if __name__ == "__main__":
    main()
