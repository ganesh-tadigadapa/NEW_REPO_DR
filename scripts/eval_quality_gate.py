"""Evaluate the fitted quality gate on the HELD-OUT subset.

Thresholds were fitted on the `fit` subset only (scripts/fit_quality_thresholds.py).
This scores them on images whose SOURCE retina never appeared in the fit subset, so the
numbers are not a re-reading of the fitting data.

Reports overall gradeable/ungradeable performance plus per-defect recall, false accept
rate and false reject rate.

    python scripts/eval_quality_gate.py
"""
from __future__ import annotations

import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.quality import gate                      # noqa: E402
from src.common.config import quality_thresholds  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--labels", default=str(ROOT / "data/interim/quality_real_labels.csv"))
    ap.add_argument("--subset", default="heldout")
    ap.add_argument("--out", default=str(ROOT / "results/quality_gate/heldout_eval.json"))
    a = ap.parse_args()

    rows = [r for r in csv.DictReader(open(a.labels)) if r["subset"] == a.subset]
    if not rows:
        raise SystemExit(f"no rows with subset={a.subset}")

    tp = tn = fp = fn = 0
    per_defect: dict[str, dict] = {}
    per_check_fire: dict[str, int] = {}
    misses = []

    for r in rows:
        img = cv2.imread(r["path"])
        if img is None:
            continue
        q = gate.assess(img)
        pred_ungradeable = not q["gradeable"]
        true_ungradeable = r["gradeable"] == "0"

        if true_ungradeable and pred_ungradeable:
            tp += 1
        elif true_ungradeable and not pred_ungradeable:
            fn += 1
            misses.append({"path": Path(r["path"]).name, "defect": r["defect"]})
        elif (not true_ungradeable) and pred_ungradeable:
            fp += 1
            failed = [k for k, v in q["checks"].items() if not v["passed"]]
            misses.append({"path": Path(r["path"]).name, "defect": "FALSE_REJECT",
                           "fired": failed})
        else:
            tn += 1

        if true_ungradeable:
            d = r["defect"]
            s = per_defect.setdefault(d, {"n": 0, "caught": 0, "caught_by_right_check": 0})
            s["n"] += 1
            if pred_ungradeable:
                s["caught"] += 1
                failed = [k for k, v in q["checks"].items() if not v["passed"]]
                want = {"focus": "focus", "fov": "field_of_view",
                        "illumination": "illumination"}[d]
                if want in failed:
                    s["caught_by_right_check"] += 1
                for f in failed:
                    per_check_fire[f] = per_check_fire.get(f, 0) + 1

    n = tp + tn + fp + fn
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    spec = tn / (tn + fp) if (tn + fp) else 0.0
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    f1 = 2 * prec * recall / (prec + recall) if (prec + recall) else 0.0
    far = fn / (tp + fn) if (tp + fn) else 0.0      # ungradeable wrongly accepted
    frr = fp / (tn + fp) if (tn + fp) else 0.0      # gradeable wrongly refused

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "subset": a.subset,
        "n": n,
        "thresholds_used": quality_thresholds(),
        "label_provenance": (
            "Ground truth BY CONSTRUCTION, not human-graded: real APTOS test_images with "
            "controlled degradations (scripts/make_quality_labelset.py). Thresholds were "
            "fitted on a disjoint 'fit' subset split by source image."),
        "positive_class": "ungradeable (the gate should refuse it)",
        "confusion": {"tp": tp, "fn": fn, "fp": fp, "tn": tn},
        "overall": {
            "recall_ungradeable": round(recall, 4),
            "specificity_gradeable": round(spec, 4),
            "precision": round(prec, 4),
            "f1": round(f1, 4),
            "accuracy": round((tp + tn) / n, 4) if n else 0.0,
            "false_accept_rate": round(far, 4),
            "false_reject_rate": round(frr, 4),
        },
        "per_defect_recall": {
            k: {"n": v["n"], "caught": v["caught"],
                "recall": round(v["caught"] / v["n"], 4) if v["n"] else 0.0,
                "caught_by_the_matching_check": v["caught_by_right_check"]}
            for k, v in sorted(per_defect.items())
        },
        "check_fire_counts_on_true_ungradeable": per_check_fire,
        "errors": misses,
        "caveat": (
            "The gradeable class assumes unmodified APTOS images are gradeable. APTOS is "
            "noisy and some genuinely are not, so false rejects may include correct "
            "refusals. Reported specificity is therefore a LOWER bound."),
    }

    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2))

    print(f"=== quality gate, held-out subset (n={n}) ===")
    print(f"  confusion: TP {tp}  FN {fn}  FP {fp}  TN {tn}")
    o = payload["overall"]
    print(f"  recall(ungradeable) {o['recall_ungradeable']}   specificity {o['specificity_gradeable']}")
    print(f"  precision {o['precision']}   F1 {o['f1']}   accuracy {o['accuracy']}")
    print(f"  false ACCEPT rate {o['false_accept_rate']}   false REJECT rate {o['false_reject_rate']}")
    print("  per-defect recall:")
    for k, v in payload["per_defect_recall"].items():
        print(f"    {k:<13} {v['caught']}/{v['n']}  recall {v['recall']}"
              f"  (matching check fired on {v['caught_by_the_matching_check']})")
    print(f"\nwrote {out}")


if __name__ == "__main__":
    main()
