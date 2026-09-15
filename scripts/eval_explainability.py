"""Table 3 — explainability, MEASURED.

"Here is a heatmap" is not evidence. This computes what fraction of Grad-CAM's attention
actually lands inside IDRiD's pixel-level lesion annotations, against two controls:

  uniform control  a flat heatmap over the retina. Equals the lesion area fraction.
                   Lesions cover ~1% of a fundus image, so ANY method scores a small
                   absolute number — the ratio to this control is the real result.
  random control   a smooth random heatmap, to show the metric isn't rewarding
                   smoothness or centre bias.

If Grad-CAM does not clearly beat both, we report that. A negative result honestly
reported is worth more than a picture.

    python scripts/eval_explainability.py \
        --images data/raw/idrid/images --masks data/raw/idrid/masks
"""
from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from src.common.config import LESION_IMAGE_SIZE, RESULTS_DIR
from src.common.imaging import preprocess_for_lesions, preprocess_for_model
from src.explain.gradcam import (attribution_mass_in_masks, gradcam, gradcam_plus_plus,
                                 random_attribution_control, upsample)

# IDRiD ships one mask directory per lesion type
MASK_SUBDIRS = {"microaneurysms": "1. Microaneurysms", "haemorrhages": "2. Haemorrhages",
                "hard_exudates": "3. Hard Exudates", "soft_exudates": "4. Soft Exudates"}


def load_union_mask(mask_root: Path, stem: str, size: int) -> np.ndarray | None:
    acc = None
    for sub in MASK_SUBDIRS.values():
        d = mask_root / sub
        if not d.is_dir():
            continue
        for cand in list(d.glob(f"{stem}*.tif")) + list(d.glob(f"{stem}*.png")):
            m = cv2.imread(str(cand), cv2.IMREAD_GRAYSCALE)
            if m is None:
                continue
            m = cv2.resize(m, (size, size), interpolation=cv2.INTER_NEAREST) > 0
            acc = m if acc is None else (acc | m)
    return acc


def smooth_random(size: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    r = rng.random((16, 16)).astype(np.float32)
    r = cv2.resize(r, (size, size), interpolation=cv2.INTER_CUBIC)
    return np.clip(r, 0, 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", required=True)
    ap.add_argument("--masks", required=True)
    ap.add_argument("--model-dir", default="artifacts/model")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()

    from src.grading.predict import load
    p = load(Path(a.model_dir))
    if not p.available:
        raise SystemExit(f"no model: {p.reason}")
    if p.synthetic:
        print("WARNING: this is the synthetic demo model. Numbers will be meaningless.")

    imgs = sorted([q for q in Path(a.images).iterdir()
                   if q.suffix.lower() in (".jpg", ".jpeg", ".png", ".tif")])
    if a.limit:
        imgs = imgs[:a.limit]

    rows = []
    for i, q in enumerate(imgs):
        bgr = cv2.imread(str(q))
        if bgr is None:
            continue
        lm = load_union_mask(Path(a.masks), q.stem, LESION_IMAGE_SIZE)
        if lm is None or not lm.any():
            continue
        _, retina = preprocess_for_lesions(bgr, LESION_IMAGE_SIZE)
        x = preprocess_for_model(bgr, p.image_size)[None, ...].astype("float32")

        cam = gradcam(p.model, x, p.last_conv)
        try:
            campp = gradcam_plus_plus(p.model, x, p.last_conv)
        except Exception:
            campp = None

        rnd = smooth_random(LESION_IMAGE_SIZE, seed=i)
        rows.append({
            "image": q.name,
            "lesion_area_fraction": round(float(lm.mean()), 6),
            "gradcam": round(attribution_mass_in_masks(cam, lm), 6),
            "gradcam_pp": (round(attribution_mass_in_masks(campp, lm), 6)
                           if campp is not None else None),
            "random_smooth": round(attribution_mass_in_masks(rnd, lm), 6),
            "uniform_control": round(random_attribution_control(lm, retina), 6),
        })
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(imgs)}")

    if not rows:
        raise SystemExit("no image had a usable lesion mask — check --masks layout")

    def mean(k):
        v = [r[k] for r in rows if r[k] is not None]
        return round(float(np.mean(v)), 6) if v else None

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": p.model_id,
        "synthetic_demo_model": p.synthetic,
        "n_images": len(rows),
        "mean_attribution_inside_lesions": {
            "gradcam": mean("gradcam"),
            "gradcam_pp": mean("gradcam_pp"),
            "random_smooth_control": mean("random_smooth"),
            "uniform_control": mean("uniform_control"),
        },
        "lift_over_uniform_control": (
            round(mean("gradcam") / mean("uniform_control"), 3)
            if mean("uniform_control") else None),
        "interpretation": ("Lesions occupy about "
                           f"{mean('uniform_control'):.2%} of the retina, so a heatmap "
                           "that ignored the image entirely would still score that much. "
                           "The lift over the uniform control is the result; the raw "
                           "fraction on its own is not."),
        "per_image": rows,
    }
    d = RESULTS_DIR / "explainability"; d.mkdir(parents=True, exist_ok=True)
    (d / "attribution.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary["mean_attribution_inside_lesions"], indent=2))
    print(f"lift over uniform control: {summary['lift_over_uniform_control']}x")
    print(f"wrote {d/'attribution.json'}")


if __name__ == "__main__":
    main()
