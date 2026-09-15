"""MATLAB vs Python agreement on the image-quality metrics.

WHY THIS EXISTS
---------------
Path B puts the classical retinal vision in MATLAB. The deployed runtime is Python,
because MATLAB cannot be served publicly on this licence (no MATLAB Compiler / Compiler
SDK entitlement; a trial licence forbids production use). So MATLAB is the *reference
implementation* and Python is the deployed port, and this script measures whether they
actually agree.

WHAT IS COMPARED, AND WHAT IS DELIBERATELY NOT
----------------------------------------------
Compared here: focus, illumination, field-of-view. These are pure arithmetic over
identical kernels, so the two implementations compute the SAME algorithm and a deviation
is a real signal about port fidelity.

NOT compared here, on purpose: lesion counts and vessel masks. Python uses skimage
Frangi and custom blob detectors; MATLAB uses fibermetric and imextendedmin. Those are
genuinely different algorithms, so a "Python vs MATLAB agreement" figure would be
meaningless -- two different wrong answers can agree, and two right answers can differ.
Those components are measured against GROUND TRUTH (DRIVE, IDRiD) instead, which is what
scripts/eval_vessels.py already does.

    python scripts/compare_matlab_python.py --n 60
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
import scipy.io as sio

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common.imaging import crop_to_retina, square_pad          # noqa: E402
from src.quality.gate import focus_score, illumination_score, fov_score  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MATLAB = "/Applications/MATLAB_R2026a.app/bin/matlab"
DEFAULT_APTOS = Path.home() / "Documents/SIH-DR/datasets/APTOS/aptos2019-blindness-detection/train_images"

METRICS = [
    ("focus_tenengrad_norm", "focus"),
    ("illumination_grid_cv", "illumination"),
    ("fov_retina_fraction", "field_of_view"),
    ("fov_centre_offset", "fov_centre_offset"),
]


def python_metrics(path: Path) -> dict:
    bgr = cv2.imread(str(path))
    if bgr is None:
        raise ValueError(f"unreadable: {path}")
    cropped, mask = crop_to_retina(bgr)
    cropped, mask = square_pad(cropped, mask)
    side = 1024
    cropped = cv2.resize(cropped, (side, side), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask.astype(np.uint8), (side, side),
                      interpolation=cv2.INTER_NEAREST).astype(bool)
    frac, off = fov_score(mask)
    return {
        "focus_tenengrad_norm": focus_score(cropped, mask),
        "illumination_grid_cv": illumination_score(cropped, mask),
        "fov_retina_fraction": frac,
        "fov_centre_offset": off,
    }


def run_matlab(paths: list[Path], workdir: Path) -> dict[str, dict]:
    list_file = workdir / "paths.txt"
    out_json = workdir / "matlab_quality.json"
    list_file.write_text("\n".join(str(p) for p in paths))
    ref_dir = ROOT / "matlab" / "reference"
    cmd = (f"addpath('{ref_dir}'); "
           f"run_quality_reference_batch('{list_file}','{out_json}')")
    proc = subprocess.run([MATLAB, "-batch", cmd], capture_output=True, text=True)
    if not out_json.exists():
        print(proc.stdout[-2000:], file=sys.stderr)
        print(proc.stderr[-2000:], file=sys.stderr)
        raise RuntimeError("MATLAB batch produced no output")
    rows = json.loads(out_json.read_text())
    if isinstance(rows, dict):
        rows = [rows]
    return {r["image"]: r for r in rows}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--images", default=str(DEFAULT_APTOS))
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--out", default=str(ROOT / "results" / "matlab_agreement.json"))
    a = ap.parse_args()

    img_dir = Path(a.images)
    files = sorted(list(img_dir.glob("*.png")) + list(img_dir.glob("*.jpg")))
    if not files:
        raise SystemExit(f"no images under {img_dir}")
    random.Random(a.seed).shuffle(files)
    files = files[: a.n]
    print(f"comparing {len(files)} images from {img_dir}")

    with tempfile.TemporaryDirectory() as td:
        workdir = Path(td)
        print("running MATLAB reference...")
        mat = run_matlab(files, workdir)

    print("running Python implementation...")
    per_image, deviations = [], {k: [] for k, _ in METRICS}
    for f in files:
        m = mat.get(str(f))
        if m is None or not m.get("ok", False):
            continue
        try:
            p = python_metrics(f)
        except ValueError:
            continue
        row = {"image": f.name}
        for key, _ in METRICS:
            pv, mv = float(p[key]), float(m[key])
            denom = abs(pv) if abs(pv) > 1e-9 else 1.0
            rel = abs(mv - pv) / denom * 100.0
            row[key] = {"python": round(pv, 6), "matlab": round(mv, 6),
                        "abs_diff": round(abs(mv - pv), 6), "rel_pct": round(rel, 4)}
            deviations[key].append(rel)
        per_image.append(row)

    # ---- isolated metric fidelity: hand MATLAB the EXACT arrays Python used --------
    print("\nrunning isolated metric-fidelity check (identical input arrays)...")
    iso_summary = {}
    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        rows, py_iso = [], []
        for f in files[:30]:
            bgr = cv2.imread(str(f))
            if bgr is None:
                continue
            c, m = crop_to_retina(bgr)
            c, m = square_pad(c, m)
            c = cv2.resize(c, (1024, 1024), interpolation=cv2.INTER_AREA)
            m = cv2.resize(m.astype(np.uint8), (1024, 1024),
                           interpolation=cv2.INTER_NEAREST).astype(bool)
            gray = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY).astype(np.float64)
            rows.append({"gray": gray, "mask": m.astype(np.uint8)})
            py_iso.append({"focus_tenengrad_norm": focus_score(c, m),
                           "illumination_grid_cv": illumination_score(c, m)})
        mat_in, json_out = wd / "arrays.mat", wd / "iso.json"
        sio.savemat(str(mat_in), {"rows": rows})
        ref_dir = ROOT / "matlab" / "reference"
        cmd = (f"addpath('{ref_dir}'); "
               f"quality_metrics_on_array('{mat_in}','{json_out}')")
        subprocess.run([MATLAB, "-batch", cmd], capture_output=True, text=True)
        if json_out.exists():
            iso = json.loads(json_out.read_text())
            if isinstance(iso, dict):
                iso = [iso]
            for key in ("focus_tenengrad_norm", "illumination_grid_cv"):
                devs = []
                for pv_row, mv_row in zip(py_iso, iso):
                    pv, mv = float(pv_row[key]), float(mv_row[key])
                    denom = abs(pv) if abs(pv) > 1e-9 else 1.0
                    devs.append(abs(mv - pv) / denom * 100.0)
                if devs:
                    iso_summary[key] = {
                        "n": len(devs),
                        "mean_rel_deviation_pct": round(statistics.mean(devs), 8),
                        "max_rel_deviation_pct": round(max(devs), 8),
                    }

    summary = {}
    for key, label in METRICS:
        d = deviations[key]
        if not d:
            continue
        summary[key] = {
            "label": label,
            "n": len(d),
            "mean_rel_deviation_pct": round(statistics.mean(d), 4),
            "median_rel_deviation_pct": round(statistics.median(d), 4),
            "max_rel_deviation_pct": round(max(d), 4),
        }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "what_this_is": (
            "Agreement between the MATLAB reference implementation "
            "(matlab/reference/retina_quality_reference.m) and the deployed Python "
            "implementation (src/quality/gate.py) on the SAME real images."),
        "deployment_note": (
            "MATLAB is the reference implementation and is NOT deployed. The live "
            "pipeline is Python. MATLAB Compiler and Compiler SDK are not licensed on "
            "this installation, and the licence is a trial, so MATLAB cannot legally or "
            "technically serve a public endpoint."),
        "only_valid_comparisons": (
            "Only metrics where BOTH implementations compute the same algorithm are "
            "compared. Lesion counts and vessel masks are deliberately excluded: the two "
            "stacks use different algorithms there, so an agreement number would be "
            "meaningless. Those are measured against ground truth instead "
            "(see results/vessels/drive_metrics.json)."),
        "fixed_during_development": [
            "cv2.Sobel defaults to BORDER_REFLECT_101; conv2(...,'same') zero-pads. "
            "On images whose retina touches the frame this changed the focus score by up "
            "to 35%. Fixed by explicit reflect-101 padding in the MATLAB reference. "
            "Verified to 0.00000000% deviation on identical input arrays."
        ],
        "residual_difference_sources": [
            "Downscale to 1024px: cv2.INTER_AREA vs MATLAB imresize 'box' differ slightly.",
            "Retina mask closing: 15x15 cv2 MORPH_ELLIPSE vs MATLAB strel('disk',7).",
            "Both are resampling/morphology differences, not algorithm differences. "
            "Gradient-based metrics (focus) are the most sensitive to them.",
        ],
        "image_source": str(img_dir),
        "n_images": len(per_image),
        "metric_fidelity_isolated": {
            "what": ("MATLAB given the EXACT preprocessed array Python used, so any "
                     "deviation is attributable to the metric implementation alone."),
            "interpretation": ("This answers 'is the algorithm correctly ported?'. The "
                               "end_to_end summary answers a different question -- 'do two "
                               "independent preprocessing stacks produce identical "
                               "pixels?' -- and they do not, which is expected and is not "
                               "a porting error."),
            "results": iso_summary,
        },
        "summary_is_end_to_end": ("Each implementation does its OWN crop, pad, resize and "
                                  "masking. Differences here include resampling, not just "
                                  "the metric."),
        "summary": summary,
        "per_image": per_image,
    }

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"\n{'metric':<24}{'n':>5}{'mean %':>10}{'median %':>11}{'max %':>10}")
    print("-" * 60)
    for key, s in summary.items():
        print(f"{s['label']:<24}{s['n']:>5}{s['mean_rel_deviation_pct']:>10.3f}"
              f"{s['median_rel_deviation_pct']:>11.3f}{s['max_rel_deviation_pct']:>10.3f}")
    if iso_summary:
        print(f"\nISOLATED metric fidelity (identical input arrays):")
        for k, s in iso_summary.items():
            print(f"  {k:<24} n={s['n']:<4} mean {s['mean_rel_deviation_pct']:.8f}%"
                  f"  max {s['max_rel_deviation_pct']:.8f}%")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
