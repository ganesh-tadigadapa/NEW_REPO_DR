# Our numbers, in plain English

Every number here comes from a real file in `results/`. Nothing is estimated.

---

## The two tests we ran — and why the second one matters more

We tested the AI twice:

| Test | What it is | Why it matters |
|---|---|---|
| **Validation** | 550 photos from the *same* collection it trained on, but hidden from it during learning | A fair-ish test |
| **External (IDRiD)** | 103 photos from a **completely different Indian hospital dataset** | **The real test.** Different camera, different patients. |

**Analogy:** validation is a practice exam from the same textbook. External is a surprise
exam set by a different school. The second one tells you what you actually know.

## The headline numbers

| What | Practice exam | **Real exam** | Plain meaning |
|---|---|---|---|
| Agreement with doctors (QWK) | 0.92 | **0.69** | Dropped a lot on unfamiliar photos |
| Caught the sick people (sensitivity) | 0.92 | **0.86** | We catch 86 of every 100 sick people |
| Left healthy people alone (specificity) | 0.93 | **0.90** | We correctly clear 90 of every 100 healthy people |
| Exactly right grade | 0.83 | **0.41** | Exact grade is hard; see below |
| Within one grade | 0.98 | **0.89** | Almost always very close |

## The target we were given, and whether we hit it

The problem statement demands **sensitivity above 90%** and **specificity above 85%**.

| | Practice exam | **Real exam** |
|---|---|---|
| Sensitivity > 90% | 0.92 ✅ | **0.86 ❌ MISSED** |
| Specificity > 85% | 0.93 ✅ | **0.90 ✅ met** |

**Say this out loud, do not hide it:**

> "On the standard test we hit both targets. On a completely different hospital's data we
> get 86% sensitivity, below the 90% target. We are reporting that because we tested a
> frozen model we never tuned against it. Most teams quote the first number only."

**Why this is a strength, not just a weakness:** we could have quoted 0.92 and stopped.
We ran the harder test, on a locked model, once, and logged it. That is what "clinical
validation rigour" — a phrase in the problem statement — actually means.

## What "exactly right 41%" really means

That sounds terrible. It isn't as bad as it sounds:

- **Within one grade: 89%.** We are almost always very close.
- The decision that matters is **"does this person need a doctor?"** — and there we are at
  86% / 90%.
- Getting grade 2 when the truth is grade 3 barely matters. Both mean "see a doctor".

## The one number that worries us most

On the external test, out of 64 people who genuinely needed a doctor, **we missed 9**.

That is the number to be honest about. In screening, a missed sick person is far worse
than a false alarm.

## Where the AI is weakest

| Grade | How well we do | Comment |
|---|---|---|
| 0 (healthy) | Excellent internally, **poor externally** | On IDRiD we called 24 of 34 healthy eyes "mild". We over-call disease on unfamiliar photos. |
| 1 (mild) | Weak | Mild is genuinely hard — the damage is tiny. |
| 2 (moderate) | Good | The most common referable case. |
| **3 (severe)** | **Weakest of all** | Only 29 examples existed to learn from. We often call it grade 2. |
| 4 (worst) | Moderate | |

**Expect a judge to ask about grade 3.** Answer: *"It is our weakest class because there
were only 29 training examples. But it still gets referred, because both grade 2 and grade
3 mean 'see a doctor'. The referral decision is unaffected."*

## The photo-quality checker

We refit it on 200 real photos. Big improvement:

| | Before | After |
|---|---|---|
| Caught bad photos | 44% | **89%** |
| Caught blurry ones | 1 in 14 | **11 in 14** |
| Caught bad-lighting ones | 0 in 7 | **6 in 7** |
| Wrongly refused good photos | 0% | **21%** |

**The honest trade:** we now catch far more bad photos, but we also refuse about 1 in 5
good ones. That is deliberate — a refused good photo just means "take it again while the
patient is still here". A bad photo that slips through gets a confident wrong answer.

**And an honest negative finding:** turning the quality checker on did **not** improve our
grading scores. If it were catching genuinely harder photos, scores on the rest should
rise. They didn't. So we say its value is *practical* (stops nonsense answers in the
field), not statistical. We do not claim it boosts accuracy.

## Proof the AI beats the old-fashioned way

The problem statement demands we prove this. We built a non-AI version and ran both on the
same photos:

| Method | Agreement with doctors | Caught the sick |
|---|---|---|
| Old-fashioned (no AI) | 0.54 | 0.70 |
| **Our AI pipeline** | **0.92** | **0.92** |

**Clear win.** The old method literally never predicted grade 3 or 4 — it lumped
everything into 0, 1 and 2.

## The hospital-planning simulation

For a district screening 100,000 diabetics a year:

- **Without our AI: 3 eye doctors needed.**
- **With our AI: 1 eye doctor needed.**
- **Saving: 2 doctors per 100,000 people.**

Why: an AI-assisted review takes 18 seconds; reading a raw photo from scratch takes ~120.

*Caveat to state:* one input (how long an unaided read takes) is an estimate, not measured.

## Other measured numbers

| What | Value | Meaning |
|---|---|---|
| Blood-vessel tracing (Python) | 0.60 | Published best is ~0.80, but ours does a different job — hiding vessels so they aren't mistaken for bleeds |
| Blood-vessel tracing (MATLAB) | 0.55 | Our MATLAB cross-check |
| Finding the optic disc | 97% within one disc-width | Works well |
| Finding the fovea | 50% | **Weak. Say so.** |
| MATLAB vs Python agreement | **0.00000000%** difference | Our two implementations agree exactly — proof the code is right |
| Speed | 4–7 seconds per photo | |
| How often the two opinions disagree | **72.5%** | High — the safety net is very active |
