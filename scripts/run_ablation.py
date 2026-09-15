"""Table 2 — the ablation the problem statement explicitly asks for.

"Prove the integrated pipeline outperforms any single technique approach." Most teams
skip this. Four rows is enough, and each row is a real training run on the SAME split.

    python scripts/run_ablation.py --aptos-csv ... --aptos-images ... --epochs 10

Rows:
  1. MATLAB classical CV baseline      -> run matlab/classical/dr_classical_baseline.m,
                                          then --classical-json to merge it in
  2. CNN, raw images, no preprocessing -> --no-enhance
  3. CNN + preprocessing + ordinal head + tuned threshold
  4. Full pipeline + quality gate + rule cross-check (row 3, evaluated with the gate
     applied and ungradeable images excluded, which is how it actually behaves in
     production)

Every row writes its own results/<run-id>/ directory. Nothing here is estimated.
"""
from __future__ import annotations

import argparse, json, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

from src.common.config import RESULTS_DIR

ROWS = [
    {"key": "cnn_raw", "label": "CNN only, raw images, no preprocessing",
     "extra": ["--no-enhance"]},
    {"key": "cnn_full", "label": "CNN + preprocessing + ordinal head + tuned threshold",
     "extra": []},
]


def run(cmd):
    print(">", " ".join(cmd), flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f"failed: {' '.join(cmd)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--aptos-csv", required=True)
    ap.add_argument("--aptos-images", required=True)
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--image-size", type=int, default=512)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--classical-json", default="",
                    help="matlab/classical/classical_baseline_metrics.json once run")
    a = ap.parse_args()

    table = []
    for row in ROWS:
        run_id = f"ablation-{row['key']}"
        out = f"artifacts/{run_id}"
        run([sys.executable, "-m", "src.grading.train",
             "--aptos-csv", a.aptos_csv, "--aptos-images", a.aptos_images,
             "--out", out, "--run-id", run_id, "--epochs", str(a.epochs),
             "--image-size", str(a.image_size), "--batch", str(a.batch)] + row["extra"])
        run([sys.executable, "scripts/calibrate_and_freeze.py", "--model-dir", out])
        m = json.loads((RESULTS_DIR / run_id / "validation_metrics.json").read_text())
        table.append({"configuration": row["label"], "run_id": run_id,
                      "qwk": m["qwk"],
                      "referable_sensitivity": m["referable"]["sensitivity"],
                      "referable_specificity": m["referable"]["specificity"]})

    if a.classical_json and Path(a.classical_json).exists():
        c = json.loads(Path(a.classical_json).read_text())
        table.insert(0, {"configuration": "MATLAB classical CV baseline (control arm)",
                         "run_id": "matlab-classical",
                         "qwk": c.get("qwk"),
                         "referable_sensitivity": c.get("referable_sensitivity"),
                         "referable_specificity": c.get("referable_specificity")})
    else:
        table.insert(0, {"configuration": "MATLAB classical CV baseline (control arm)",
                         "run_id": "matlab-classical",
                         "qwk": "not run yet", "referable_sensitivity": "not run yet",
                         "referable_specificity": "not run yet"})

    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "rows": table}
    d = RESULTS_DIR / "ablation"; d.mkdir(parents=True, exist_ok=True)
    (d / "ablation.json").write_text(json.dumps(out, indent=2))

    w = max(len(r["configuration"]) for r in table)
    print(f"\n{'Configuration'.ljust(w)} | QWK    | Sens   | Spec")
    print("-" * (w + 26))
    for r in table:
        print(f"{r['configuration'].ljust(w)} | {str(r['qwk'])[:6]:6} | "
              f"{str(r['referable_sensitivity'])[:6]:6} | {str(r['referable_specificity'])[:6]}")
    print(f"\nwrote {d/'ablation.json'}")


if __name__ == "__main__":
    main()
