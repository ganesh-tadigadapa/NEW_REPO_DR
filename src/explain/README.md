# `src/explain/` — Stations 5–7: "Show your working"

**Plain job:** make the AI's answer checkable by a human. This is the heart of the
project — the problem statement specifically complains that existing tools are black
boxes.

## The four files

| File | Plain job |
|---|---|
| `gradcam.py` | The **heat-map** — which parts of the photo drove the decision |
| `icdr_rules.py` | The **second opinion** — our most important file (see below) |
| `calibration.py` | Makes the confidence **honest** |
| `report.py` | Builds the **one-page PDF** |

## `icdr_rules.py` — the one to understand

This is our main innovation.

- The AI says "grade 3". A heat-map is not a *reason*.
- So this file works out the grade a **second time**, from the actual damage counts, using
  the official published medical rules. **No AI involved.**
- Then it compares the two.

**When they disagree, it sends the case to a human doctor** rather than averaging them or
trusting the AI. The reasoning is deliberately lopsided: a false alarm costs one wasted
appointment; a missed severe case costs someone their sight.

## The honesty rule inside it

We cannot detect three things: venous beading, IRMA, and neovascularisation.

So for those, the rule-checker reports **"unknown"** — never **"absent"**.

That difference matters enormously. Saying "I can't see it, so it isn't there" would
systematically under-grade the sickest patients — exactly the failure that blinds people.
The rule-checker also refuses to ever confirm grade 4, because it has no way to see the
sign that defines grade 4.

## What "calibration" means

An AI that says "90% sure" should be right 90% of the time. Often they're overconfident.
`calibration.py` measures and corrects this. Ours was already nearly honest — the
correction factor was 0.99, i.e. almost no change needed.
