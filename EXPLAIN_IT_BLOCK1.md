# What I just built — block 1, in plain English

Per rule 6. Read this once; it is the vocabulary you need for the first ten minutes of
any conversation about this project.

---

## The one-sentence version

The entire pipeline is built and tested end to end — you can upload a fundus photo right
now and get back a grade, a heatmap, a lesion table, a clinical-rule cross-check and a
PDF — but it is running on a **model trained on fake images** (efficientnetv2b0 @128px,
60 synthetic images, 23 seconds). No GPU training run has ever happened.

That distinction is the whole story of where we are. **The plumbing is done. The science
is waiting on data.**

---

## The five things worth understanding

### 1. The ordinal head — your single best answer to any judge

The grades 0–4 are *ordered*. Normal image classifiers treat "predicted 0, actually 4"
and "predicted 3, actually 4" as equally wrong. Clinically the first could blind someone
and the second barely matters.

So instead of asking "which of 5 categories?", our model answers four yes/no questions:
*is it worse than 0? worse than 1? worse than 2? worse than 3?* The grade is just how
many of those are yes.

**Why this is the best answer you have:** the second question — *is it worse than grade
1?* — **is exactly the referral decision**. So "should this patient see a specialist" is
not something we calculate afterwards; it is a number the network was directly trained to
produce, with its own dial we can turn to hit the 90% sensitivity target.

> Say: *"Standard classifiers throw away the fact that the grades are ordered. We use an
> ordinal head, which means the referral decision is a direct output of the model with
> its own tunable threshold, not something we derive afterwards."*

### 2. The quality gate refuses images, and tells the worker why

Three checks: is it in focus, is it evenly lit, is the whole retina in frame. A failure
returns HTTP 422 with a specific instruction — *"Image is out of focus. Clean the camera
lens, ask the patient to look steadily at the fixation target, and retake."*

**A real bug I found and fixed, which is worth telling:** the textbook sharpness measure
(Laplacian variance) confuses *blurry* with *smooth*. A healthy retina has no lesions and
so has few edges — it scored as blurrier than a diseased out-of-focus one. The gate would
have quietly rejected healthy eyes and biased every prevalence number we report. I
switched to a contrast-normalised measure that ranks them correctly, and there is a test
pinning it.

> Say: *"We measure sharpness relative to the image's own contrast, because the naive
> measure confuses a healthy smooth retina with a blurred one — which would have
> systematically rejected healthy patients."*

### 3. Two independent opinions, and we show you when they disagree

The neural network gives a grade. Separately, classical computer vision counts the actual
lesions and runs them through the **real published ICDR criteria** — including the 4-2-1
rule, which needs lesion counts *per quadrant*, which is why we locate the optic disc and
fovea at all.

When the two disagree we surface it as "clinician review recommended" instead of hiding it.

**The honest part that will earn you credit:** our detectors cannot see venous beading,
IRMA, or new vessels. So the rule engine can never confirm grade 4. Rather than treat
"I can't see it" as "it isn't there" — which would under-grade the sickest patients — it
returns *unknown* and flags for review.

> Say: *"We compute the grade a second time from the explicit clinical criteria. Where
> the rules physically cannot assess something, we say unknown rather than absent,
> because the alternative under-grades the sickest patients."*

### 4. The system refuses to invent numbers, and this is enforced in code

The dashboard's numbers come from `/v1/metrics`, which reads a results file. No file → the
page prints **"not run yet"**. There is no placeholder anywhere to accidentally ship.

The demo model is branded `SYNTHETIC-DEMO-not-a-real-model`; that flag travels from the
model file, through the API, into an amber warning bar across the top of the UI. You
cannot show a synthetic result and forget to mention it.

> Say: *"Every number in the UI is fetched from a results file. If we haven't run the
> evaluation, it says 'not run yet'. We couldn't fake a number without deleting code."*

### 5. Why there is no fancy model-serving tier

Grad-CAM needs the *gradients* inside the model. A managed prediction endpoint hands back
only the answer. So the explainability requirement makes the fashionable architecture
impossible — we load the model inside our own server instead. It is also cheaper.

> Say: *"A managed endpoint returns logits, not gradients, so the heatmap would have been
> impossible. We load the model in-process. It was a constraint, and it happened to be
> the cheaper option too."*

---

## The economic slide, and its honest caveat

The simulation says AI triage cuts the images a human must read to **26.8%**, taking a
100,000-patient district from **3 ophthalmologists to 1**.

The caveat you must volunteer: that depends on how long an unaided read takes, which we
have not measured. So it is reported as a **range** — 1 to 5 FTEs saved across 60 to 240
seconds per unaided read. Saying this before you are asked is worth more than the number.

---

## Three questions to test yourself

1. Why is confusing grade 0 with grade 4 worse than confusing 3 with 4 — and what did we
   do about it?
2. Our lesion detector cannot see new blood vessels. Why does that make the system report
   *unknown* rather than *no disease*?
3. Why can't the heatmap be produced by a managed prediction service?

If you can answer these in your own words, you can defend block 1.
