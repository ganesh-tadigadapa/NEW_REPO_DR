"""Feed the workflow simulation with MEASURED service times from the live API.

    python scripts/export_simulink_params.py --api http://localhost:8080

Writes matlab/simulink/measured_params.json, which both the Simulink model and
scripts/simulate_workflow.py pick up automatically. Until this has run, both print a
warning and their output is not quotable — a simulation fed on invented inputs tells you
nothing, and a judge is entitled to ask where each number came from.
"""
from __future__ import annotations

import argparse, json
from datetime import datetime, timezone
from pathlib import Path

import urllib.request

from src.common.config import REPO_ROOT


def get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return json.loads(r.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api", default="http://localhost:8080")
    ap.add_argument("--manual-read-seconds", type=float, default=None,
                    help="unaided read time. NOT measurable from our own service — "
                         "supply a timed observation or a citation, or leave unset.")
    a = ap.parse_args()

    op = get(f"{a.api}/v1/operational")
    scans = get(f"{a.api}/v1/scans?limit=200")["scans"]
    if not op.get("available"):
        raise SystemExit(f"no operational data yet: {op.get('reason')}")

    def med(key):
        vals = [s["timing_ms"][key] / 1000 for s in scans
                if isinstance(s.get("timing_ms"), dict) and key in s["timing_ms"]]
        return round(sorted(vals)[len(vals) // 2], 4) if vals else None

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": f"MEASURED from {a.api} over {len(scans)} scans",
        "n_scans": len(scans),
        "qualityGateSeconds": med("quality"),
        "gradingSeconds": round((med("grading") or 0) + (med("preprocess") or 0)
                                + (med("gradcam") or 0) + (med("lesions") or 0), 4),
        "ungradeableRate": op.get("ungradeable_rate"),
        "reviewSeconds": op.get("median_seconds_to_decide"),
        # not measurable from our own traffic — documented as assumptions
        "uploadSeconds": 5.5,
        "uploadSeconds_basis": "350 kB downscaled JPEG over a 512 kbit/s rural link",
        "recaptureSeconds": 45.0,
        "recaptureSeconds_basis": "assumption: health worker repositions and retakes",
        "referableRate": None,
        "disagreementRate": None,
        "NOTE": ("referableRate and disagreementRate must come from a dataset "
                 "evaluation, not from demo traffic. Fill them from "
                 "results/<run>/holdout_metrics.json once the holdout has been run."),
    }
    if a.manual_read_seconds:
        out["manualReadSeconds"] = a.manual_read_seconds
        out["manualReadSeconds_basis"] = "supplied on the command line"

    p = REPO_ROOT / "matlab" / "simulink" / "measured_params.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nwrote {p}")


if __name__ == "__main__":
    main()
