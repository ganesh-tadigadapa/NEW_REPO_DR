"""Fit the quality-gate thresholds against human labels.

This is the script that turns "we picked 55 because a blog said so" into "we swept the
threshold against 200 images a clinician labelled and took the operating point that
maximised agreement". It is a small script and it is worth a slide.

Input: a CSV with columns `path,gradeable` where gradeable is 1 (a human would grade
this image) or 0 (a human would ask for a retake).

    python scripts/fit_quality_thresholds.py --labels data/raw/quality_labels.csv

Output: results/quality_gate/thresholds.json  (+ a metrics block with the agreement,
sensitivity and specificity of the fitted gate, and the provenance of the labels).

Each of the three checks is fitted INDEPENDENTLY against the same binary label, by
sweeping candidate cut points and maximising Youden's J (sensitivity + specificity - 1).
Independent fitting is the right call here because the checks are meant to be
independently interpretable — a joint fit would let a lax focus threshold be masked by a
strict FOV one, and then the recapture message would name the wrong problem.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from src.common.config import RESULTS_DIR
from src.common.imaging import crop_to_retina, square_pad
from src.quality.gate import focus_score, illumination_score, fov_score

OUT = RESULTS_DIR / "quality_gate"


def measure_all(path: str) -> dict | None:
    img = cv2.imread(path)
    if img is None:
        return None
    cropped, mask = crop_to_retina(img)
    cropped, mask = square_pad(cropped, mask)
    side = 1024
    cropped = cv2.resize(cropped, (side, side), interpolation=cv2.INTER_AREA)
    mask = cv2.resize(mask.astype(np.uint8), (side, side),
                      interpolation=cv2.INTER_NEAREST).astype(bool)
    frac, off = fov_score(mask)
    return {"focus": focus_score(cropped, mask),
            "illumination": illumination_score(cropped, mask),
            "field_of_view": frac,
            "centre_offset": off}


def sweep(values: np.ndarray, labels: np.ndarray, direction: str) -> dict:
    """direction='higher' -> pass when value >= t; 'lower' -> pass when value <= t.

    Returns a **max-margin** threshold, not merely an optimal one. Youden's J is a step
    function of the cut point: every threshold between two adjacent observed values
    scores identically. Taking the first such value puts the cut flush against a training
    observation, and the gate then rejects an image that differs by a rounding error —
    which is exactly what happened on the first fit, where a 768px render of an image
    that passed at 1024px was refused.

    So among all thresholds achieving the best J we take the MIDPOINT of that range. Same
    fit, same J, but the decision boundary sits as far as possible from every image we
    trained it on. On a small label set this is the difference between a gate that
    generalises and one that memorises.
    """
    lo, hi = float(np.min(values)), float(np.max(values))
    pad = (hi - lo) * 0.05 + 1e-9
    cands = np.unique(np.concatenate([
        [lo - pad, hi + pad],
        np.quantile(values, np.linspace(0, 1, 201)),
    ]))
    scored = []
    for t in cands:
        pred = values >= t if direction == "higher" else values <= t
        tp = int(((pred == 1) & (labels == 1)).sum())
        tn = int(((pred == 0) & (labels == 0)).sum())
        fp = int(((pred == 1) & (labels == 0)).sum())
        fn = int(((pred == 0) & (labels == 1)).sum())
        sens = tp / max(tp + fn, 1)
        spec = tn / max(tn + fp, 1)
        scored.append({"threshold": float(t), "sensitivity": round(sens, 4),
                       "specificity": round(spec, 4),
                       "youden_j": round(sens + spec - 1, 4),
                       "tp": tp, "tn": tn, "fp": fp, "fn": fn})

    best_j = max(r["youden_j"] for r in scored)
    optimal = [r for r in scored if r["youden_j"] >= best_j - 1e-12]
    ts = [r["threshold"] for r in optimal]
    chosen = float((min(ts) + max(ts)) / 2.0)

    # report the stats actually obtained AT the chosen midpoint
    pred = values >= chosen if direction == "higher" else values <= chosen
    tp = int(((pred == 1) & (labels == 1)).sum()); tn = int(((pred == 0) & (labels == 0)).sum())
    fp = int(((pred == 1) & (labels == 0)).sum()); fn = int(((pred == 0) & (labels == 1)).sum())
    sens = tp / max(tp + fn, 1); spec = tn / max(tn + fp, 1)
    return {"threshold": chosen, "sensitivity": round(sens, 4),
            "specificity": round(spec, 4), "youden_j": round(sens + spec - 1, 4),
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
            "optimal_range": [round(min(ts), 4), round(max(ts), 4)],
            "n_optimal_cuts": len(optimal)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", required=True,
                    help="CSV: path,gradeable(1|0)")
    ap.add_argument("--provenance", default="",
                    help="who labelled these and how (goes in the output file)")
    ap.add_argument("--tag", default="", help="e.g. 'synthetic' to mark a non-clinical fit")
    args = ap.parse_args()

    rows = list(csv.DictReader(open(args.labels)))
    if not rows:
        raise SystemExit("no rows in labels csv")

    feats, labels, skipped = [], [], []
    for r in rows:
        m = measure_all(r["path"])
        if m is None:
            skipped.append(r["path"]); continue
        feats.append(m); labels.append(int(r["gradeable"]))
    labels = np.array(labels)
    if len(set(labels.tolist())) < 2:
        raise SystemExit("labels must contain both 0 and 1")

    spec = {
        "focus_tenengrad_min": ("focus", "higher"),
        "illumination_grid_cv_max": ("illumination", "lower"),
        "fov_retina_fraction_min": ("field_of_view", "higher"),
    }
    thresholds, per_check = {}, {}
    for key, (feat, direction) in spec.items():
        vals = np.array([f[feat] for f in feats])
        best = sweep(vals, labels, direction)
        thresholds[key] = round(best["threshold"], 4)
        per_check[key] = best

    # agreement of the COMBINED gate (all three must pass)
    pred = np.ones(len(labels), dtype=int)
    for key, (feat, direction) in spec.items():
        vals = np.array([f[feat] for f in feats])
        ok = vals >= thresholds[key] if direction == "higher" else vals <= thresholds[key]
        pred &= ok.astype(int)
    tp = int(((pred == 1) & (labels == 1)).sum()); tn = int(((pred == 0) & (labels == 0)).sum())
    fp = int(((pred == 1) & (labels == 0)).sum()); fn = int(((pred == 0) & (labels == 1)).sum())

    payload = {
        "fitted_at": datetime.now(timezone.utc).isoformat(),
        "labels_file": args.labels,
        "n_images": int(len(labels)),
        "n_skipped_unreadable": len(skipped),
        "n_gradeable": int(labels.sum()),
        "provenance": args.provenance or "NOT RECORDED - fill this in",
        "tag": args.tag,
        "synthetic": args.tag == "synthetic",
        "thresholds": thresholds,
        "per_check_fit": per_check,
        "combined_gate": {
            "agreement_with_human": round((tp + tn) / max(len(labels), 1), 4),
            "sensitivity_keeps_gradeable": round(tp / max(tp + fn, 1), 4),
            "specificity_rejects_ungradeable": round(tn / max(tn + fp, 1), 4),
            "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        },
    }
    if args.tag == "synthetic":
        payload["WARNING"] = (
            "Fitted on SYNTHETIC images. Valid for demo plumbing only. "
            "No number derived from this file may appear in the deck. "
            "Re-run against human-labelled real fundus images before reporting anything."
        )

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "thresholds.json").write_text(json.dumps(payload, indent=2))
    print(json.dumps(payload, indent=2))
    print(f"\nwrote {OUT / 'thresholds.json'}")


if __name__ == "__main__":
    main()
