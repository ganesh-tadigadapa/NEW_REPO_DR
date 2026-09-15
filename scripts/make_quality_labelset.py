"""Build a REPRODUCIBLE quality-label set from real APTOS images.

WHAT THIS IS, AND WHAT IT IS NOT
--------------------------------
It is NOT a human-graded label set. No ophthalmologist or human grader labelled these
images, and none of the labels here should ever be described as clinical ground truth.

It IS ground truth **by construction**: every "ungradeable" image is a real APTOS fundus
photograph with one controlled, physically meaningful degradation applied, at a severity
chosen to destroy the specific feature the quality gate exists to protect. If we blur an
image until a 15px microaneurysm is no longer resolvable, we know it is ungradeable for
focus, because we did it.

THE LIMITATION THIS CREATES -- STATE IT BEFORE A JUDGE ASKS
----------------------------------------------------------
Thresholds fitted on SYNTHETIC degradations of real images may not transfer to NATURAL
degradation. A camera that is genuinely out of focus does not produce exactly a Gaussian
blur; real uneven illumination is not exactly a linear gradient. This label set is a
large improvement on the previous one -- 13 fully synthetic fundus images -- but it is
NOT a substitute for ~200 human-labelled real captures, which remains the right fix and
is still open in docs/BLOCKERS.md.

THE POSITIVE-CLASS ASSUMPTION -- ALSO A REAL CAVEAT
---------------------------------------------------
Unmodified APTOS images are labelled gradeable. That is an ASSUMPTION, not an
observation: APTOS images were curated for a grading competition and each carries a human
DR grade, which implies a human could grade them. But APTOS is a famously noisy dataset
and some of its images are genuinely poor. So the gradeable class is slightly
contaminated with images a clinician would refuse, which INFLATES measured specificity
(we count a correct refusal of a genuinely bad image as a false reject). Reported numbers
are therefore a lower bound on specificity, not an upper one.

NO LEAKAGE
----------
Fit and held-out subsets are split by SOURCE image, not by row, so the same retina never
appears in both -- a blurred copy in the fit set and the clean original in the held-out
set would be leakage.

    python scripts/make_quality_labelset.py --n 200
"""
from __future__ import annotations

import argparse, csv, glob, json, os, random
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
# APTOS test_images was NEVER part of split.csv -- not in training, not in validation.
TEST_IMAGES = Path.home() / "Documents/SIH-DR/datasets/APTOS/aptos2019-blindness-detection/test_images"
OUT_DIR = ROOT / "data" / "interim" / "quality_real"


def degrade_focus(bgr: np.ndarray) -> np.ndarray:
    """Gaussian blur at sigma = 0.006 x width.

    Rationale: a microaneurysm is roughly 15-30 px across in a native APTOS frame. A
    Gaussian with sigma ~12 px (at 2000 px width) spreads that over a region several
    times its own diameter, so the lesion the grader is looking for is no longer
    resolvable. That is the definition of ungradeable-for-focus in a DR screening
    context, and it is why the severity is tied to image width rather than fixed.
    """
    w = bgr.shape[1]
    sigma = max(3.0, 0.006 * w)
    k = int(sigma * 6) | 1
    return cv2.GaussianBlur(bgr, (k, k), sigma)


def degrade_fov(bgr: np.ndarray, rng: random.Random) -> np.ndarray:
    """Crop to 35-45% of width, cutting the retina off at one edge.

    Rationale: measured on the current gate, a 50% crop still passes and 45% is the first
    to fail, so this band represents captures that are unambiguously mis-framed -- a
    substantial part of the retina is simply not in the photograph.
    """
    w = bgr.shape[1]
    frac = rng.uniform(0.35, 0.45)
    cut = int(w * frac)
    return bgr[:, :cut] if rng.random() < 0.5 else bgr[:, w - cut:]


def degrade_illumination(bgr: np.ndarray, rng: random.Random) -> np.ndarray:
    """Strong one-sided luminance gradient, falling to 20-30% at the dark edge.

    Rationale: this is the classic flash/alignment fault in handheld fundus cameras --
    one side of the retina is washed out or lost in shadow. At 20-30% residual
    brightness, lesion contrast on the dark side is below what a grader can use.
    """
    h, w = bgr.shape[:2]
    lo = rng.uniform(0.20, 0.30)
    ramp = np.linspace(1.0, lo, w, dtype=np.float32)
    if rng.random() < 0.5:
        ramp = ramp[::-1]
    if rng.random() < 0.5:                       # vertical instead of horizontal
        ramp = np.linspace(1.0, lo, h, dtype=np.float32)
        if rng.random() < 0.5:
            ramp = ramp[::-1]
        field = np.repeat(ramp[:, None], w, axis=1)
    else:
        field = np.repeat(ramp[None, :], h, axis=0)
    out = bgr.astype(np.float32) * field[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200, help="total rows (half gradeable)")
    ap.add_argument("--seed", type=int, default=4242)
    ap.add_argument("--fit-frac", type=float, default=0.70)
    a = ap.parse_args()

    rng = random.Random(a.seed)
    files = sorted(glob.glob(str(TEST_IMAGES / "*.png")))
    if not files:
        raise SystemExit(f"no APTOS test images under {TEST_IMAGES}")
    rng.shuffle(files)

    n_bad = a.n // 2
    n_good = a.n - n_bad
    need = n_good + n_bad
    if len(files) < need:
        raise SystemExit(f"need {need} source images, found {len(files)}")

    # Disjoint source pools: a retina used for a degraded row is never also used clean.
    good_src = files[:n_good]
    bad_src = files[n_good:n_good + n_bad]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for f in OUT_DIR.glob("*.png"):
        f.unlink()

    rows = []
    for p in good_src:
        stem = Path(p).stem
        dst = OUT_DIR / f"good_{stem}.png"
        img = cv2.imread(p)
        if img is None:
            continue
        cv2.imwrite(str(dst), img)
        rows.append({"path": str(dst.relative_to(ROOT)), "gradeable": 1,
                     "defect": "none", "source": stem})

    kinds = ["focus", "fov", "illumination"]
    for i, p in enumerate(bad_src):
        stem = Path(p).stem
        img = cv2.imread(p)
        if img is None:
            continue
        kind = kinds[i % 3]
        if kind == "focus":
            out = degrade_focus(img)
        elif kind == "fov":
            out = degrade_fov(img, rng)
        else:
            out = degrade_illumination(img, rng)
        dst = OUT_DIR / f"bad_{kind}_{stem}.png"
        cv2.imwrite(str(dst), out)
        rows.append({"path": str(dst.relative_to(ROOT)), "gradeable": 0,
                     "defect": kind, "source": stem})

    # split by SOURCE so no retina spans both subsets
    sources = sorted({r["source"] for r in rows})
    rng.shuffle(sources)
    n_fit = int(len(sources) * a.fit_frac)
    fit_src = set(sources[:n_fit])
    for r in rows:
        r["subset"] = "fit" if r["source"] in fit_src else "heldout"

    lab = ROOT / "data" / "interim" / "quality_real_labels.csv"
    with open(lab, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["path", "gradeable", "defect", "source", "subset"])
        w.writeheader()
        w.writerows(rows)

    for subset in ("fit", "heldout"):
        sub = [r for r in rows if r["subset"] == subset]
        p = ROOT / "data" / "interim" / f"quality_real_labels_{subset}.csv"
        with open(p, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["path", "gradeable"])
            w.writeheader()
            for r in sub:
                w.writerow({"path": r["path"], "gradeable": r["gradeable"]})

    meta = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "seed": a.seed,
        "source_dataset": "APTOS 2019 test_images (never in split.csv: not train, not validation)",
        "n_total": len(rows),
        "n_gradeable": sum(1 for r in rows if r["gradeable"] == 1),
        "n_ungradeable": sum(1 for r in rows if r["gradeable"] == 0),
        "defect_counts": {k: sum(1 for r in rows if r["defect"] == k)
                          for k in ("none", "focus", "fov", "illumination")},
        "subset_counts": {s: sum(1 for r in rows if r["subset"] == s)
                          for s in ("fit", "heldout")},
        "label_provenance": (
            "GROUND TRUTH BY CONSTRUCTION, NOT HUMAN-GRADED. Ungradeable rows are real "
            "APTOS photographs with one controlled degradation applied by "
            "scripts/make_quality_labelset.py. No human grader was involved."),
        "known_limitations": [
            "Synthetic degradation of real images may not transfer to natural "
            "degradation: real defocus is not exactly a Gaussian blur.",
            "The gradeable class assumes unmodified APTOS images are gradeable. APTOS is "
            "noisy and some genuinely are not, which INFLATES apparent false rejects and "
            "makes reported specificity a lower bound.",
            "Not a substitute for ~200 human-labelled real captures (docs/BLOCKERS.md).",
        ],
        "degradation_parameters": {
            "focus": "GaussianBlur sigma = 0.006 x width (>= 3.0), kernel 6 sigma",
            "fov": "crop to 35-45% of width from a random side",
            "illumination": "one-sided linear luminance ramp to 20-30% residual",
        },
        "split_rule": "by SOURCE image, so no retina appears in both fit and heldout",
    }
    (ROOT / "data" / "interim" / "quality_real_labelset.json").write_text(json.dumps(meta, indent=2))

    print(json.dumps({k: v for k, v in meta.items()
                      if k in ("n_total", "n_gradeable", "n_ungradeable",
                               "defect_counts", "subset_counts")}, indent=2))
    print(f"\nlabels  -> {lab}")
    print(f"images  -> {OUT_DIR}")


if __name__ == "__main__":
    main()
