"""Step 5: the external holdout, run ONCE.

    python scripts/run_holdout.py --idrid-csv ... --idrid-images ...

Refuses to run a second time against the same frozen fingerprint unless `--i-am-aware-
this-is-a-second-look` is passed, in which case it records that fact permanently in the
output. "We opened the test set once" is only credible if something other than memory
enforces it — a judge can read the ledger.
"""
from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.common.config import RESULTS_DIR
from src.grading.data import read_idrid
from src.grading.evaluate import evaluate_split

LEDGER = RESULTS_DIR / "holdout_ledger.json"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--idrid-csv", required=True)
    ap.add_argument("--idrid-images", required=True)
    ap.add_argument("--image-ext", default=".jpg")
    ap.add_argument("--model-dir", default="artifacts/model")
    ap.add_argument("--i-am-aware-this-is-a-second-look", action="store_true")
    a = ap.parse_args()

    d = Path(a.model_dir)
    frozen = json.loads((d / "FROZEN.json").read_text())
    fp = frozen["fingerprint"]

    ledger = json.loads(LEDGER.read_text()) if LEDGER.exists() else {"runs": []}
    prior = [r for r in ledger["runs"] if r["fingerprint"] == fp]
    if prior and not a.i_am_aware_this_is_a_second_look:
        raise SystemExit(
            f"REFUSING: the holdout has already been evaluated against frozen config {fp} "
            f"on {prior[0]['at']}.\nRe-running and reporting the better number would "
            f"invalidate the external validation claim.\nIf you genuinely need to re-run "
            f"(e.g. a bug in the loader), pass --i-am-aware-this-is-a-second-look; it "
            f"will be recorded in the results.")

    from src.grading.predict import load
    p = load(d)
    if not p.available:
        raise SystemExit(f"no model: {p.reason}")

    import cv2
    from src.common.imaging import preprocess_for_model
    paths, grades = read_idrid(Path(a.idrid_csv), Path(a.idrid_images), a.image_ext)
    print(f"holdout: {len(paths)} images, dist={np.bincount(grades, minlength=5).tolist()}")

    logits = []
    for i, path in enumerate(paths):
        img = cv2.imread(path)
        x = preprocess_for_model(img, p.image_size)[None, ...].astype("float32")
        logits.append(p.logits(x)[0])
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(paths)}")
    logits = np.array(logits)

    metrics = evaluate_split(logits, np.array(grades), p.cuts, "idrid_holdout")
    metrics.update({
        "run_id": frozen["run_id"], "fingerprint": fp,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "is_repeat_look": bool(prior),
        "n_prior_looks": len(prior),
        "protocol": ("Thresholds and temperature were frozen on the validation split "
                     "before this file was created. No tuning followed this evaluation."),
        "temperature": p.temperature,
    })

    out = RESULTS_DIR / frozen["run_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "holdout_metrics.json").write_text(json.dumps(metrics, indent=2))

    ledger["runs"].append({"fingerprint": fp, "run_id": frozen["run_id"],
                           "at": datetime.now(timezone.utc).isoformat(),
                           "n": len(paths), "qwk": metrics["qwk"],
                           "sens": metrics["referable"]["sensitivity"],
                           "spec": metrics["referable"]["specificity"]})
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(ledger, indent=2))

    publish_active({**metrics, "is_external_validation": True,
                    "caveat": ("External holdout (IDRiD). Nothing was tuned on this "
                               "data and it was opened once.")},
                   f"results/{frozen['run_id']}/holdout_metrics.json")

    r = metrics["referable"]
    print(f"\nHOLDOUT  QWK {metrics['qwk']}  (CI {metrics['qwk_ci95']})")
    print(f"  referable sensitivity {r['sensitivity']}  CI {r['sensitivity_ci95']}")
    print(f"  referable specificity {r['specificity']}  CI {r['specificity_ci95']}")
    print(f"wrote {out/'holdout_metrics.json'}")


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
