"""District screening workflow — discrete-event simulation.

Insurance against MATLAB access falling through, and a way to sanity-check the Simulink
model against an independent implementation. Same pipeline, same parameters:

    arrivals -> upload -> quality gate -> [fail] recapture loop
                                       -> [pass] AI grading
                                          -> [cleared]  done
                                          -> [referable OR CNN/rule disagreement]
                                             -> ophthalmologist queue -> review

THE QUESTION: how many ophthalmologist FTEs does a district need to screen 100,000
diabetics a year, with and without AI triage in front of them?

Hand-rolled event loop, no third-party dependency, so it runs anywhere.

    python scripts/simulate_workflow.py --patients-per-year 100000

Writes results/simulation/workflow_simulation.json.
"""
from __future__ import annotations

import argparse
import heapq
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.common.config import RESULTS_DIR


@dataclass
class Params:
    patients_per_year: int = 100_000
    working_days: int = 250
    hours_per_day: float = 6.0
    upload_s: float = 5.5
    quality_gate_s: float = 0.05
    grading_s: float = 1.4
    recapture_s: float = 45.0
    # TWO DIFFERENT HUMAN TASKS, and conflating them destroys the economic argument.
    #   review_s      — verifying an AI-annotated report: grade, heatmap and lesion table
    #                   are already on screen. This is the <30 s target we MEASURE in the
    #                   review screen.
    #   manual_read_s — an unaided read of a raw fundus photograph: the ophthalmologist
    #                   locates lesions themselves, grades, and documents. Several times
    #                   slower. This is a PLACEHOLDER pending a citation or a timed
    #                   observation; the FTE saving is highly sensitive to it, so it is
    #                   reported with a sensitivity analysis rather than as a point claim.
    review_s: float = 30.0
    manual_read_s: float = 120.0
    ungradeable_rate: float = 0.12
    referable_rate: float = 0.22
    disagreement_rate: float = 0.06
    max_recaptures: int = 2
    n_upload_channels: int = 8
    n_ai_workers: int = 4
    source: str = "PLACEHOLDER — run scripts/export_simulink_params.py against the live API"


@dataclass(order=True)
class Event:
    t: float
    seq: int
    kind: str = field(compare=False)
    pid: int = field(compare=False)
    data: dict = field(compare=False, default_factory=dict)


class Sim:
    """Single-server-pool discrete-event simulation with FIFO queues."""

    def __init__(self, p: Params, n_ophthalmologists: int, ai_enabled: bool, seed=0):
        self.p = p
        self.n_oph = n_ophthalmologists
        self.ai = ai_enabled
        self.rng = np.random.default_rng(seed)
        self.q: list[Event] = []
        self.seq = 0
        self.horizon = p.working_days * p.hours_per_day * 3600

        # Service time depends on the arm: verifying an AI report is not the same task
        # as reading a raw photograph from scratch.
        self.service_s = p.review_s if ai_enabled else p.manual_read_s
        self.review_queue: list[float] = []      # arrival times waiting for a human
        self.busy_oph = 0
        self.oph_busy_time = 0.0

        self.waits: list[float] = []
        self.n_arrived = 0
        self.n_auto_cleared = 0
        self.n_reviewed = 0
        self.n_ungradeable_final = 0
        self.n_recaptures = 0

    # ---------------------------------------------------------------- helpers
    def push(self, t, kind, pid, **data):
        self.seq += 1
        heapq.heappush(self.q, Event(t, self.seq, kind, pid, data))

    def exp(self, mean):
        return float(self.rng.exponential(mean))

    # ------------------------------------------------------------------- run
    def run(self) -> dict:
        mean_gap = self.horizon / self.p.patients_per_year
        t = 0.0
        pid = 0
        while True:
            t += self.exp(mean_gap)
            if t > self.horizon:
                break
            pid += 1
            self.push(t, "arrive", pid)
        self.n_arrived = pid

        while self.q:
            e = heapq.heappop(self.q)
            getattr(self, f"_on_{e.kind}")(e)

        return self.summary()

    # ---------------------------------------------------------------- events
    def _on_arrive(self, e):
        if not self.ai:
            # Without AI there is no automated quality gate: the ophthalmologist is the
            # one who discovers an unreadable image, having already spent time on it, and
            # only then asks for a retake. That wasted time is a real cost of the
            # status quo and the model should not quietly hand it to the AI-less arm.
            self.push(e.t + self.exp(self.p.upload_s), "manual_read", e.pid)
            return
        # upload + quality gate modelled as delays; both pools are far from saturated at
        # this load, so contention there is not the bottleneck and is not modelled as a
        # queue. The ophthalmologist IS the bottleneck, and that is modelled properly.
        t = e.t + self.exp(self.p.upload_s) + self.p.quality_gate_s
        self.push(t, "gate", e.pid, tries=0)

    def _on_gate(self, e):
        tries = e.data["tries"]
        if self.rng.random() < self.p.ungradeable_rate:
            if tries + 1 > self.p.max_recaptures:
                # exhausted retries: this patient is referred manually, which is a
                # human cost the AI did NOT save. Counting it honestly matters.
                self.n_ungradeable_final += 1
                self._enqueue_review(e.t)
                return
            self.n_recaptures += 1
            t = e.t + self.p.recapture_s + self.p.quality_gate_s
            self.push(t, "gate", e.pid, tries=tries + 1)
            return
        self.push(e.t + self.p.grading_s, "graded", e.pid)

    def _on_manual_read(self, e):
        # Every image reaches a human; ungradeable ones cost a read before the retake.
        self._enqueue_review(e.t)
        if self.rng.random() < self.p.ungradeable_rate:
            self.n_ungradeable_final += 1

    def _on_graded(self, e):
        referable = self.rng.random() < self.p.referable_rate
        disagree = self.rng.random() < self.p.disagreement_rate
        if referable or disagree:
            self._enqueue_review(e.t)
        else:
            self.n_auto_cleared += 1

    def _enqueue_review(self, t):
        if self.busy_oph < self.n_oph:
            self.busy_oph += 1
            self.waits.append(0.0)
            dur = self.exp(self.service_s)
            self.oph_busy_time += dur
            self.push(t + dur, "review_done", -1)
        else:
            self.review_queue.append(t)

    def _on_review_done(self, e):
        self.n_reviewed += 1
        if self.review_queue:
            arrived = self.review_queue.pop(0)
            self.waits.append(max(e.t - arrived, 0.0))
            dur = self.exp(self.service_s)
            self.oph_busy_time += dur
            self.push(e.t + dur, "review_done", -1)
        else:
            self.busy_oph -= 1

    # --------------------------------------------------------------- results
    def summary(self) -> dict:
        waits = np.array(self.waits) if self.waits else np.array([0.0])
        backlog = len(self.review_queue)
        capacity_s = self.n_oph * self.horizon
        util = self.oph_busy_time / max(capacity_s, 1e-9)
        return {
            "n_ophthalmologists": self.n_oph,
            "ai_enabled": self.ai,
            "n_arrived": self.n_arrived,
            "n_sent_to_human": self.n_reviewed + backlog,
            "n_auto_cleared": self.n_auto_cleared,
            "n_reviewed": self.n_reviewed,
            "n_unreviewed_backlog": backlog,
            "n_ungradeable_after_retries": self.n_ungradeable_final,
            "n_recaptures": self.n_recaptures,
            "human_workload_fraction": round(
                (self.n_reviewed + backlog) / max(self.n_arrived, 1), 4),
            "mean_wait_hours": round(float(waits.mean()) / 3600, 3),
            "p95_wait_hours": round(float(np.percentile(waits, 95)) / 3600, 3),
            "utilisation": round(float(util), 4),
            # "Feasible" means the district actually clears its year: the queue does not
            # end with a backlog, the mean wait is under a working week, and the
            # ophthalmologists are not pinned at capacity (no slack = no resilience).
            "feasible": bool(backlog == 0 and waits.mean() / 3600 < 30 and util < 0.85),
        }


def min_feasible(p: Params, ai: bool, max_staff: int, seed: int) -> tuple[int | None, list]:
    rows = []
    found = None
    for n in range(1, max_staff + 1):
        r = Sim(p, n, ai, seed=seed).run()
        rows.append(r)
        if r["feasible"] and found is None:
            found = n
    return found, rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patients-per-year", type=int, default=100_000)
    ap.add_argument("--max-staff", type=int, default=20)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--params", default="matlab/simulink/measured_params.json")
    a = ap.parse_args()

    p = Params(patients_per_year=a.patients_per_year)
    pf = Path(a.params)
    if pf.exists():
        m = json.loads(pf.read_text())
        for k, v in m.items():
            key = {"uploadSeconds": "upload_s", "qualityGateSeconds": "quality_gate_s",
                   "gradingSeconds": "grading_s", "recaptureSeconds": "recapture_s",
                   "reviewSeconds": "review_s", "manualReadSeconds": "manual_read_s",
                   "ungradeableRate": "ungradeable_rate",
                   "referableRate": "referable_rate",
                   "disagreementRate": "disagreement_rate"}.get(k)
            if key:
                setattr(p, key, float(v))
        p.source = f"MEASURED via {pf}"
        print(f"using measured parameters from {pf}")
    else:
        print(f"WARNING: {pf} not found — using documented PLACEHOLDER parameters.\n"
              f"         Run scripts/export_simulink_params.py against the live API "
              f"before quoting any of these numbers.")

    with_ai, rows_ai = min_feasible(p, True, a.max_staff, a.seed)
    without_ai, rows_no = min_feasible(p, False, a.max_staff, a.seed)

    # The FTE saving depends heavily on manual_read_s, which is the least certain
    # parameter in the model. Report the sensitivity rather than a single number.
    sens = []
    for mr in (60.0, 90.0, 120.0, 180.0, 240.0):
        pp = Params(**{**p.__dict__, "manual_read_s": mr})
        w, _ = min_feasible(pp, True, a.max_staff, a.seed)
        wo, _ = min_feasible(pp, False, a.max_staff, a.seed)
        sens.append({"manual_read_s": mr, "with_ai": w, "without_ai": wo,
                     "fte_saved": (None if (w is None or wo is None) else wo - w)})
    out_sens = sens

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "implementation": "python discrete-event simulation (scripts/simulate_workflow.py)",
        "note": ("Independent re-implementation of the Simulink model in matlab/simulink/. "
                 "The graded deliverable is the Simulink model; this exists as a "
                 "cross-check and as insurance against MATLAB access failing."),
        "parameters": p.__dict__,
        "parameters_are_measured": p.source.startswith("MEASURED"),
        "min_ophthalmologists_with_ai": with_ai,
        "min_ophthalmologists_without_ai": without_ai,
        "fte_saved": (None if (with_ai is None or without_ai is None)
                      else without_ai - with_ai),
        "sensitivity_to_manual_read_time": out_sens,
        "sweep_with_ai": rows_ai,
        "sweep_without_ai": rows_no,
    }
    d = RESULTS_DIR / "simulation"; d.mkdir(parents=True, exist_ok=True)
    (d / "workflow_simulation.json").write_text(json.dumps(out, indent=2))

    print(f"\nTo clear {a.patients_per_year:,} patients/year:")
    print(f"  without AI triage : {without_ai} ophthalmologists")
    print(f"  with AI triage    : {with_ai} ophthalmologists")
    if out["fte_saved"] is not None:
        print(f"  FTEs saved        : {out['fte_saved']}")
    ai_row = next((r for r in rows_ai if r["n_ophthalmologists"] == with_ai), None)
    if ai_row:
        print(f"  human workload with AI: {ai_row['human_workload_fraction']:.1%} of images")
    print("\n  sensitivity to unaided read time (the least certain parameter):")
    for r in out_sens:
        print(f"    manual read {r['manual_read_s']:5.0f}s -> "
              f"without AI {r['without_ai']}, with AI {r['with_ai']}, saved {r['fte_saved']}")
    print(f"\nwrote {d/'workflow_simulation.json'}")
    if not out["parameters_are_measured"]:
        print("PARAMETERS ARE PLACEHOLDERS — not quotable.")


if __name__ == "__main__":
    main()
