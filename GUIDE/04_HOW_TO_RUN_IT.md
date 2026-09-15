# How to run it

Every command below is copy-paste. Open the **Terminal** app first, then paste.

---

## The one thing to know

The project has **two halves** that must both be running:

1. **The engine** (backend) — does the thinking. No visuals.
2. **The website** (frontend) — what you see and click.

You need **two Terminal windows**, one for each. Leave both open.

---

## Start it (the normal way)

**Terminal window 1 — the engine:**

```bash
cd ~/Downloads/SIH_PROJECT
make api
```

Wait until it stops printing. Leave this window open.

**Terminal window 2 — the website:**

```bash
cd ~/Downloads/SIH_PROJECT
make web
```

Then open **http://localhost:3000** in your browser.

**To stop either one:** click that window and press `Control` + `C`.

---

## Check the engine is alive

```bash
curl -s http://localhost:8080/health
```

You want to see `"model_id":"aptos-kaggle-run1"` and `"synthetic_demo_model":false`.

- `aptos-kaggle-run1` = the **real** AI trained on real photos. Correct.
- If it ever says `SYNTHETIC-DEMO-not-a-real-model`, something is wrong — that is the old
  fake model. Tell me.

---

## Prove nothing is broken

```bash
cd ~/Downloads/SIH_PROJECT
make test
```

Takes ~30 seconds. You want **`45 passed`**. If you see any failure, stop and tell me.

Run this after any change, before any demo.

---

## Demo script — what to click

1. Open **http://localhost:3000**
2. Go to the **Screen** page
3. Seven sample photos are built in. Use them in this order:

| Click this | What should happen | What to say |
|---|---|---|
| `aptos-grade0` | Green, "No DR", not referable | "Healthy eye, correctly cleared." |
| `aptos-grade4` | Red, "Proliferative DR", referable | "Worst grade, correctly caught." |
| `aptos-ungradeable-focus` | **Refused** with a retake message | "A bad photo never gets a grade. It tells the health worker how to retake it." |
| `aptos-ungradeable-fov` | **Refused**, different message | "Different problem, different instruction." |
| `aptos-grade2` | Referable + heat-map + damage counts | "Here is why it said that." |

4. Scroll down on any graded photo to show the **heat-map**, the **damage-spot table**,
   and the **second-opinion box**.
5. Click **Download PDF**.

**All five graded samples are real photos the AI has never seen, and it gets all five
right.** That is worth saying out loud.

---

## If something goes wrong

| Symptom | Fix |
|---|---|
| Website loads but everything says "not run yet" | The engine isn't running. Do Terminal 1 again. |
| "Address already in use" | Something is already running. `pkill -f uvicorn` then retry. |
| Website won't start | `cd ~/Downloads/SIH_PROJECT/web && npm install` then retry. |
| Tests fail | Stop. Do not demo. Tell me the message. |

---

## Commands you will probably never need

These exist but are only for rebuilding results. **Do not run these before a demo.**

| Command | What it does | Careful |
|---|---|---|
| `python scripts/eval_quality_gate.py` | Re-scores the photo checker | Safe |
| `python scripts/compare_matlab_python.py` | Re-checks MATLAB vs Python | Safe, slow |
| `python scripts/run_holdout.py ...` | The external exam | **Only once, ever. Already done.** |
| Training on Kaggle | Re-teaches the AI | **Do not.** The current AI is frozen and validated. |
