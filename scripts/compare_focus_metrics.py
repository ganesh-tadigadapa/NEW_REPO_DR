"""Evidence for the focus-metric choice. Writes results/quality_gate/focus_metric_comparison.json.

Run against ANY labelled set (real or synthetic). Reports, per candidate metric, how well
it separates gradeable from ungradeable images (Youden's J over a threshold sweep).
"""
from __future__ import annotations
import argparse, csv, json
from datetime import datetime, timezone
import cv2, numpy as np
from src.common.config import RESULTS_DIR
from src.common.imaging import crop_to_retina, square_pad
from scripts.fit_quality_thresholds import sweep


def metrics(path):
    img = cv2.imread(path)
    if img is None:
        return None
    c, m = crop_to_retina(img); c, m = square_pad(c, m)
    c = cv2.resize(c, (1024, 1024), interpolation=cv2.INTER_AREA)
    m = cv2.resize(m.astype(np.uint8), (1024, 1024), interpolation=cv2.INTER_NEAREST).astype(bool)
    g = cv2.cvtColor(c, cv2.COLOR_BGR2GRAY)
    var = g[m].astype(np.float64).var() + 1e-6
    lap = cv2.Laplacian(g, cv2.CV_64F, ksize=3)[m]
    gx = cv2.Sobel(g, cv2.CV_64F, 1, 0, ksize=3); gy = cv2.Sobel(g, cv2.CV_64F, 0, 1, ksize=3)
    return {
        "laplacian_var": float(lap.var()),
        "laplacian_var_normalised": float(lap.var() / var * 100),
        "tenengrad_norm": float((gx[m] ** 2 + gy[m] ** 2).mean() / var * 100),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    rows = list(csv.DictReader(open(a.labels)))
    feats, labels = [], []
    for r in rows:
        m = metrics(r["path"])
        if m: feats.append(m); labels.append(int(r["gradeable"]))
    labels = np.array(labels)
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "labels_file": a.labels,
           "tag": a.tag, "n_images": len(labels), "candidates": {}}
    for name in feats[0]:
        vals = np.array([f[name] for f in feats])
        res = sweep(vals, labels, "higher")
        # Youden's J is a step function and ties are common on small label sets. Break
        # ties on the normalised margin between the two classes: a metric that separates
        # the classes by a wide gap is more robust to a new camera than one that merely
        # happens to put the cut in the same place.
        pos, neg = vals[labels == 1], vals[labels == 0]
        pooled = np.sqrt((pos.var() + neg.var()) / 2) + 1e-9
        res["separation_margin"] = round(float((pos.mean() - neg.mean()) / pooled), 4)
        out["candidates"][name] = res
    best = max(out["candidates"],
               key=lambda k: (out["candidates"][k]["youden_j"],
                              out["candidates"][k]["separation_margin"]))
    out["selected"] = best
    out["rationale"] = ("Selected on separability (Youden's J) between human-gradeable and "
                        "human-rejected images. Raw Laplacian variance conflates blur with "
                        "low retinal texture; contrast-normalisation decouples them. Ties on J are "
                        "broken by the standardised separation margin between the classes.")
    d = RESULTS_DIR / "quality_gate"; d.mkdir(parents=True, exist_ok=True)
    (d / "focus_metric_comparison.json").write_text(json.dumps(out, indent=2))
    for k, v in out["candidates"].items():
        print(f"{k:28s} J={v['youden_j']:.3f} margin={v['separation_margin']:6.2f} thr={v['threshold']:.3f} sens={v['sensitivity']:.2f} spec={v['specificity']:.2f}")
    print("selected:", best)


if __name__ == "__main__":
    main()
