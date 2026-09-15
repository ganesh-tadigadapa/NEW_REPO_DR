# MATLAB / Simulink

Two deliverables live here, and both are load-bearing rather than decorative.

## 1. `simulink/` — the district workflow model (graded requirement #5)

> **LICENCE REALITY, verified with `ver` on R2026a:** this install has MATLAB, Simulink,
> Computer Vision, Deep Learning, Image Processing, Medical Imaging, and Statistics &
> ML. It does **NOT** have **SimEvents**. `build_dr_workflow_model.m` is built entirely
> from SimEvents blocks and therefore **cannot run here**.

**Run this one — it works on our licence:**

```matlab
cd matlab/simulink
build_dr_workflow_basic          % saves dr_district_workflow_basic.slx
run_sweeps_basic                 % staffing sweep -> results/simulation/simulink_sweep.json
```

`build_dr_workflow_model.m` (SimEvents, discrete-**event**) is kept in the repo because it
is the textbook-correct abstraction and runs unmodified if a SimEvents licence appears.
`build_dr_workflow_basic.m` (base Simulink, discrete-**time** flow model) is the one we
can actually execute, and it answers the same staffing question.

**The honest line for a judge:** "Discrete-event is the right abstraction and we wrote
that model. Our trial licence lacks SimEvents, so the model we can run is a discrete-time
fluid approximation. It answers the staffing question, and it agrees with our independent
Python discrete-event simulation — two implementations, same answer."

Both are built **programmatically from `.m` files** rather than shipped as binary `.slx`,
so the model is diffable and reproducible from source — the same argument we make about
versioned training runs.

**Feed it real numbers first.** `scripts/export_simulink_params.py` pulls the measured
service times out of the running API (`GET /v1/operational`) and writes
`simulink/measured_params.json`. Without that file the model runs on documented
placeholders and prints a warning; placeholder-driven output must not appear in the deck.

## 2. `classical/` — the control arm (the ablation table's first row)

```matlab
cd matlab/classical
dr_classical_baseline('../../artifacts/model/split.csv')
```

Top-hat exudates, extended-minima microaneurysms, matched-filter vessels, SVM grading —
run on the **identical split** the CNN used. The problem statement asks for proof the
integrated pipeline beats any single-technique approach; this is that single technique.

Toolboxes: Image Processing, Statistics and Machine Learning, SimEvents, Simulink.

## If MATLAB access falls through

`scripts/simulate_workflow.py` is a SimPy re-implementation of the same discrete-event
model with the same parameters. It exists as insurance, it is **not** a substitute for
the graded deliverable, and if we end up using it we say so plainly rather than implying
a Simulink model we did not build. Exhaust MATLAB Online first.
