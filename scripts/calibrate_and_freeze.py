"""Step 2-4 of the protocol: tune thresholds, fit temperature, FREEZE.

Everything here reads ONLY `val_logits.npz` from the training run. The holdout is not
touched and is not even referenced in this file.

    python scripts/calibrate_and_freeze.py --model-dir artifacts/model
"""
from __future__ import annotations

import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.common.config import RESULTS_DIR
from src.explain.calibration import (apply_temperature, brier_score,
                                     expected_calibration_error, fit_temperature)
from src.grading.evaluate import evaluate_split, tune_all_cuts, tune_referable_cut
from src.grading.model import logits_to_cumulative


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", default="artifacts/model")
    ap.add_argument("--target-sensitivity", type=float, default=0.90)
    ap.add_argument("--min-specificity", type=float, default=0.85)
    a = ap.parse_args()

    d = Path(a.model_dir)
    z = np.load(d / "val_logits.npz", allow_pickle=True)
    logits, levels, grades = z["logits"], z["levels"], z["grades"]
    run = json.loads((d / "run.json").read_text()) if (d / "run.json").exists() else {}
    run_id = run.get("run_id", d.name)

    # ---- temperature FIRST: the cut points must be chosen on the calibrated
    # probabilities that will actually be used at inference, otherwise the tuned
    # operating point does not correspond to the deployed one.
    T = fit_temperature(logits, levels)
    cal = apply_temperature(logits, T)
    cum_raw, cum_cal = logits_to_cumulative(logits), logits_to_cumulative(cal)

    y_ref = (grades >= 2).astype(int)
    ece_before = expected_calibration_error(cum_raw[:, 1], y_ref)
    ece_after = expected_calibration_error(cum_cal[:, 1], y_ref)

    tuned = tune_referable_cut(cum_cal, grades, a.target_sensitivity, a.min_specificity)
    ref_cut = tuned["chosen"]["cut"]
    cuts = tune_all_cuts(cum_cal, grades, ref_cut)
    val_metrics = evaluate_split(cal, grades, cuts, "validation")

    (d / "temperature.json").write_text(json.dumps({
        "temperature": T,
        "fitted_on": "validation split only",
        "ece_before": ece_before["ece"], "ece_after": ece_after["ece"],
        "mce_before": ece_before["mce"], "mce_after": ece_after["mce"],
        "brier_before": round(brier_score(cum_raw[:, 1], y_ref), 5),
        "brier_after": round(brier_score(cum_cal[:, 1], y_ref), 5),
        "reliability_bins_after": ece_after["bins"],
    }, indent=2))

    (d / "thresholds.json").write_text(json.dumps({
        "cumulative_cuts": cuts,
        "referable_cut": ref_cut,
        "tuning_status": tuned["status"],
        "tuned_on": "validation split only",
        "target_sensitivity": a.target_sensitivity,
        "min_specificity": a.min_specificity,
        "validation_operating_point": tuned["chosen"],
        "validation_auc": tuned["auc"],
    }, indent=2))

    # ---- the freeze record: a hash of the exact config the holdout will be run against
    frozen = {"run_id": run_id, "cuts": cuts, "temperature": T,
              "image_size": run.get("image_size"), "backbone": run.get("backbone"),
              "git_commit": run.get("git_commit")}
    fingerprint = hashlib.sha256(
        json.dumps(frozen, sort_keys=True).encode()).hexdigest()[:16]
    (d / "FROZEN.json").write_text(json.dumps({
        "frozen_at": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fingerprint, **frozen,
        "statement": ("Thresholds and temperature are fitted on the validation split "
                      "only. The external holdout has not been evaluated at this point."),
    }, indent=2))

    out = RESULTS_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "validation_metrics.json").write_text(json.dumps({
        "run_id": run_id, "fingerprint": fingerprint,
        "temperature": T, "ece_before": ece_before, "ece_after": ece_after,
        "threshold_tuning": tuned, **val_metrics}, indent=2))

    print(f"temperature T = {T:.4f}   ECE {ece_before['ece']:.4f} -> {ece_after['ece']:.4f}")
    print(f"cuts = {[round(c,4) for c in cuts]}   referable cut = {ref_cut:.4f}  ({tuned['status']})")
    print(f"VALIDATION  QWK {val_metrics['qwk']}  "
          f"sens {val_metrics['referable']['sensitivity']}  "
          f"spec {val_metrics['referable']['specificity']}")
    print(f"FROZEN fingerprint {fingerprint}")
    print(f"wrote {out/'validation_metrics.json'}")
    # Validation numbers go on the dashboard until the holdout is run, clearly labelled
    # as validation — they are tuned-on numbers and must never be called external.
    publish_active({**val_metrics, "run_id": run_id, "fingerprint": fingerprint,
                    "is_external_validation": False,
                    "synthetic_demo_model": bool(run.get("synthetic_demo_model", False)),
                    "caveat": ("Validation split — thresholds and temperature were tuned "
                               "on this data. Not an external validation.")},
                   f"results/{run_id}/validation_metrics.json")


def publish_active(metrics: dict, source: str) -> None:
    """Publish a metrics file as the one the dashboard shows.

    The API's /v1/metrics reads results/active/metrics.json and nothing else. Making
    "which numbers are on the dashboard" an explicit, single, overwritable file means the
    UI can never drift from the results directory, and swapping which run is on display
    is one deliberate action rather than an edit in three places.
    """
    import json as _json
    from src.common.config import RESULTS_DIR as _R
    d = _R / "active"
    d.mkdir(parents=True, exist_ok=True)
    (d / "metrics.json").write_text(_json.dumps({**metrics, "_source": source}, indent=2))
    print(f"published -> {d / 'metrics.json'}  (source: {source})")


if __name__ == "__main__":
    main()
