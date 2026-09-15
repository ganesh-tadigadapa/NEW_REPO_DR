"""Optic-disc and fovea localisation: Python and MATLAB, both against IDRiD truth.

VALID BY CONSTRUCTION
---------------------
Each implementation is scored against the SAME ground truth (IDRiD C. Localization
markups), with the same metric: Euclidean distance from the annotated centre, expressed
both in pixels of the 1024px working frame and as a fraction of the image width.

The two detectors are NOT compared to each other. They use different algorithms, so a
detector-vs-detector distance would say nothing about which one is correct.

Both receive byte-identical preprocessed images, so the comparison isolates the detector.

    python scripts/eval_localisation.py --n 120
"""
from __future__ import annotations

import argparse, csv, json, subprocess, statistics, sys, tempfile
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.common.imaging import crop_to_retina, square_pad, retina_mask   # noqa: E402
from src.segment.structures import find_optic_disc, find_fovea           # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
MATLAB = "/Applications/MATLAB_R2026a.app/bin/matlab"
IDRID = Path.home() / "Documents/SIH-DR/datasets/IDRiD/C. Localization"
IMGS = IDRID / "1. Original Images/a. Training Set"
OD_CSV = IDRID / "2. Groundtruths/1. Optic Disc Center Location/a. IDRiD_OD_Center_Training Set_Markups.csv"
FV_CSV = IDRID / "2. Groundtruths/2. Fovea Center Location/IDRiD_Fovea_Center_Training Set_Markups.csv"
SIZE = 1024


def read_markup(p: Path) -> dict[str, tuple[float, float]]:
    out = {}
    with open(p) as f:
        for row in csv.DictReader(f):
            name = (row.get("Image No") or "").strip()
            try:
                x = float(row["X- Coordinate"]); y = float(row["Y - Coordinate"])
            except (KeyError, TypeError, ValueError):
                continue
            if name:
                out[name] = (x, y)
    return out


def transform(bgr, gt_xy):
    """Map an original-image coordinate into the 1024px preprocessed frame.

    Mirrors crop_to_retina -> square_pad -> resize exactly.
    """
    mask = retina_mask(bgr)
    if not mask.any():
        return None, None, None
    ys, xs = np.where(mask)
    y0 = max(ys.min() - 2, 0); x0 = max(xs.min() - 2, 0)
    y1 = min(ys.max() + 3, bgr.shape[0]); x1 = min(xs.max() + 3, bgr.shape[1])
    ch, cw = y1 - y0, x1 - x0
    s = max(ch, cw)
    top, left = (s - ch) // 2, (s - cw) // 2
    scale = SIZE / s
    cropped, m = crop_to_retina(bgr)
    cropped, m = square_pad(cropped, m)
    img = cv2.resize(cropped, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
    m = cv2.resize(m.astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_NEAREST).astype(bool)
    gx, gy = gt_xy
    tx = (gx - x0 + left) * scale
    ty = (gy - y0 + top) * scale
    return img, m, (tx, ty)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--out", default=str(ROOT / "results" / "localisation_metrics.json"))
    a = ap.parse_args()

    od, fv = read_markup(OD_CSV), read_markup(FV_CSV)
    names = sorted(set(od) & set(fv))[: a.n]
    print(f"{len(names)} IDRiD images with both OD and fovea ground truth")

    with tempfile.TemporaryDirectory() as td:
        wd = Path(td)
        prep_dir = wd / "prep"; prep_dir.mkdir()
        rows, listing = [], []
        for nm in names:
            src = IMGS / f"{nm}.jpg"
            if not src.exists():
                continue
            bgr = cv2.imread(str(src))
            if bgr is None:
                continue
            img, mask, od_t = transform(bgr, od[nm])
            if img is None:
                continue
            _, _, fv_t = transform(bgr, fv[nm])
            pd_ = find_optic_disc(img, mask)
            pf_ = find_fovea(img, mask, pd_)
            pth = prep_dir / f"{nm}.png"
            cv2.imwrite(str(pth), img)
            listing.append(str(pth))
            rows.append({"name": nm, "od_true": od_t, "fv_true": fv_t,
                         "py_od": (pd_["cx"], pd_["cy"]), "py_fv": (pf_["cx"], pf_["cy"])})

        lst = wd / "list.txt"; lst.write_text("\n".join(listing))
        mj = wd / "matlab_loc.json"
        ref = ROOT / "matlab" / "reference"
        subprocess.run([MATLAB, "-batch",
                        f"addpath('{ref}'); disc_fovea_reference('{lst}','{mj}')"],
                       capture_output=True, text=True)
        mat = {}
        if mj.exists():
            data = json.loads(mj.read_text())
            if isinstance(data, dict):
                data = [data]
            mat = {Path(r["image"]).stem: r for r in data}

    def dist(a_, b_):
        return float(np.hypot(a_[0] - b_[0], a_[1] - b_[1]))

    acc = {"python_od": [], "python_fovea": [], "matlab_od": [], "matlab_fovea": []}
    per = []
    for r in rows:
        m = mat.get(r["name"])
        e = {"image": r["name"],
             "python_od_px": round(dist(r["py_od"], r["od_true"]), 2),
             "python_fovea_px": round(dist(r["py_fv"], r["fv_true"]), 2)}
        acc["python_od"].append(e["python_od_px"])
        acc["python_fovea"].append(e["python_fovea_px"])
        if m and m.get("ok"):
            e["matlab_od_px"] = round(dist((m["disc_x"], m["disc_y"]), r["od_true"]), 2)
            e["matlab_fovea_px"] = round(dist((m["fovea_x"], m["fovea_y"]), r["fv_true"]), 2)
            acc["matlab_od"].append(e["matlab_od_px"])
            acc["matlab_fovea"].append(e["matlab_fovea_px"])
        per.append(e)

    summary = {}
    for k, v in acc.items():
        if v:
            summary[k] = {
                "n": len(v),
                "mean_error_px": round(statistics.mean(v), 2),
                "median_error_px": round(statistics.median(v), 2),
                "mean_error_frac_of_width": round(statistics.mean(v) / SIZE, 4),
                "within_1_disc_radius_pct": round(
                    100.0 * sum(1 for d in v if d <= 0.07 * SIZE) / len(v), 1),
            }

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dataset": "IDRiD C. Localization, training set",
        "frame": f"{SIZE}px preprocessed working frame (both implementations see identical pixels)",
        "metric": "Euclidean distance from the annotated centre",
        "validity_note": (
            "Each implementation is scored against the SAME ground truth. The two "
            "detectors are NOT compared to each other: they use different algorithms, so "
            "a detector-vs-detector distance would not indicate which is correct."),
        "disc_radius_assumption": "within_1_disc_radius uses 0.07 x width as a typical disc radius",
        "n_images": len(per),
        "summary": summary,
        "per_image": per[:50],
    }
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"\n{'':<16}{'n':>5}{'mean px':>10}{'median px':>11}{'within 1DR':>12}")
    print("-" * 55)
    for k, s in summary.items():
        print(f"{k:<16}{s['n']:>5}{s['mean_error_px']:>10.1f}"
              f"{s['median_error_px']:>11.1f}{s['within_1_disc_radius_pct']:>11.1f}%")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
