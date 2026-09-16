# SIH26038 — Explainable AI for Diabetic Retinopathy Screening

Upload a fundus photograph → ICDR grade 0–4, referable yes/no, Grad-CAM heatmap, lesion
evidence checked against the ICDR clinical rules, calibrated confidence, and a one-page
PDF an ophthalmologist signs off in under 30 seconds. A blurry image is **refused** with a
specific instruction for retaking it.

> **Screening triage aid. Not a diagnostic device.**

## New here, or not a coder? Read `GUIDE/` first

`GUIDE/00_START_HERE.md` explains this whole project in plain English with no jargon —
what it does, what each folder holds, what every number means, how to run it, and what to
say to judges. Every code folder also has a plain-English `README.md` inside it.

## Status

The pipeline is built and verified end to end. It runs today with no cloud account and no
datasets — on a model trained on **synthetic images**, which is branded as such from the
model file through the API into a warning bar in the UI. The plumbing is done; the science
is waiting on data.

**Read `docs/BLOCKERS.md` first** — four things need your accounts, and one is a 5-second
folder rename that unblocks the entire frontend.

## Run it

```bash
make setup                 # venv + npm install
make synth                 # generate test images
cp .env.example .env       # API settings; the defaults are fine for local work
make api                   # http://localhost:8080
make web                   # http://localhost:3000   (see BLOCKERS.md #1 first)
make test                  # backend + translation-integrity tests
make web-test              # frontend tests (CareBridge)
make smoke                 # end-to-end: expects 401; add TOKEN=... for the 200/422 part
```

> **Do not run `npm run build` while `make web` is running.** `next build` and `next dev`
> share `web/.next`; running both mixes production and dev artifacts and the site then
> fails with `Cannot find module './NNN.js'`. Use `make web-build`, which refuses to run
> while a dev server is live. To recover: `pkill -f 'next dev' && rm -rf web/.next && make web`.

The app has **no login step**. Open <http://localhost:3000/login>, type any mobile
number, and you are in — there is no code to enter, no password and no SMS provider.

The number is still asked for because it is the record key: it owns your screening
history and your Eye Health Passport, and it is the number your WhatsApp report goes to.
What it no longer does is prove anything.

To try the doctor side:

```bash
make doctors                              # list doctor accounts + verification state
make approve-doctor MOBILE=+919876543210  # approve one
```

Signing in is free; becoming a **doctor** is not — that still needs an administrator.

## Signing in

Identity is a **mobile number, taken as claimed**. There are no passwords and no
one-time codes anywhere in the system. Nothing verifies that the person typing a number
owns it, so the per-account boundaries below separate *claimed* identities rather than
verified ones — see `docs/AUTH.md` §1.

| Account type | Can do |
|---|---|
| **User** | screen images, see their own results and the review queue |
| **Doctor**, unverified | the same; the reports area says "Doctor verification pending." |
| **Doctor**, verified | the above, plus `/reports`: every screening report, anonymised |
| **Admin** | approve doctor accounts (`ADMIN_MOBILES` in the environment) |

Choosing "Doctor Account" at signup **grants nothing**. It creates an account with
`doctor_verified = false` and files a verification request; only an admin endpoint or the
local `scripts/approve_doctor.py` can flip that flag. The role is read from the server's
account store on every request, never from the token or the request body.

The doctor report view is anonymised by construction: it is built field by field from a
whitelist, so no patient name, mobile number or free-text `patient_ref` can reach it.

Full architecture, the production guards, and an honest limitations list:
**`docs/AUTH.md`**. Configuration: **`.env.example`**.

## CareBridge — the result, in the patient's language

A screening service whose result only exists in English is not usable by most of the
people it was built for. CareBridge is the accessibility layer over the whole patient
journey: **English, हिन्दी, తెలుగు, ਪੰਜਾਬੀ**, chosen once and remembered, with voice
playback and a Simple ⇄ Clinical switch over the same result.

It is a presentation layer and nothing else. No grade, probability, threshold, referral
decision, Grad-CAM or lesion count is computed or changed by it, and the model is never
called a second time — `web/components/carebridge/CareResult.tsx` re-orders and translates
the `AnalyzeResult` the API already returned, rendering the existing clinical components
unchanged inside its clinical section.

Three things it refuses to do:

- **Guess.** An image the quality gate refused gets the translated recapture flow — no
  grade, no follow-up interval, no nutrition guidance.
- **Pretend.** A device with no Telugu voice keeps the Telugu text and says why it cannot
  speak it, rather than reading Telugu aloud in an English voice.
- **Drift.** A missing key fails `tsc`; a blank one, a dropped `{placeholder}` or a
  "translation" that is the English text copied across fails `make test`.

Open <http://localhost:3000/carebridge> — no sign-in required. Details in
`docs/CAREBRIDGE.md`.

## 🪪 CareBridge Eye Health Passport — what changed since last time

Diabetic retinopathy is a disease of **change over time**. One screening answers "what
does this photograph show?" It cannot answer the question that actually decides whether
someone keeps their sight: *what has changed since last time, and when should this person
come back?*

The Eye Health Passport is that second question, and it is a loop rather than a feature:

```
SCREEN → SAVE → FOLLOW-UP PLAN → REMINDER → RETURN → NEW SCREENING
      → COMPARE → COMPARISON REPORT → WHATSAPP → UPDATED FOLLOW-UP PLAN → ⟲
```

A returning patient is told their previous screening is available *before* they upload.
The new result is compared with the last one that was actually graded, a step timeline
grows by one point, the follow-up window is recalculated from the current result, and a
comparison PDF goes to the WhatsApp number they already proved is theirs.

What it refuses to do is the interesting part:

- **Diagnose.** Grade 1 then grade 2 is a fact about two screening RESULTS, not proof the
  disease progressed — different day, different camera, different pupil, and a model with
  its own error rate. So the system says *"the current screening result is one ICDR
  category higher than the previous screening"* and never *"your disease has worsened"*.
  A test runs all 25 pairs of grades and asserts the forbidden vocabulary appears in none
  of them.
- **Interpolate.** ICDR grade is an ordinal CATEGORY, so the timeline is a **step** that
  holds each grade until the next screening changes it. Nothing averages grades or fits a
  trend through them.
- **Compare a refusal.** A photograph the quality gate rejected is on the timeline — the
  visit happened — but it is never half of a comparison, and the visit after it is
  compared with the last result that was actually graded.
- **Prescribe.** Follow-up windows come from a configured table keyed by ICDR grade, not
  from one universal interval, and a clinician's recommendation overrides the table
  outright. The wording is "suggested follow-up", never "you must return".
- **Touch the model.** Nothing in `src/passport/` loads a weight, reads a pixel or
  evaluates a threshold.

A verified doctor can read the anonymised report collection already. Reading one patient's
history *over time* needs more than a role — it needs a care relationship, created by
recording a clinician review on one of that patient's screenings, or by an administrator.

Open <http://localhost:3000/passport>. Details in `docs/PASSPORT.md`.

## 📍 Smart Care Finder — from screening to the next step of care

A result that tells someone their eyes need looking at, and then leaves them to work out
where, has done half a job. Smart Care Finder is the other half, and it is **one
CareBridge feature**, not four: it takes the patient's location (only after they press
the button), finds real eye-care facilities near it on the **Google Places API (New)**,
draws them on an interactive map beside a synchronised list, shows what Google actually
knows about each one — distance, rating, open/closed, phone, website — and hands over
directions that open in Google Maps on desktop, Android and iPhone.

It is an **access** layer. It reads two things off the result the page already has — the
grade, and the existing clinician-review signal — and both choose a sentence and how
prominent the section is. It cannot change a grade, a referral, an overlay or a report,
and `src/carefinder/` imports none of the medical pipeline.

Three things it refuses to do:

- **Invent.** A field Google did not return is rendered as missing — never as "Unknown",
  never as a placeholder, and never as another facility's value.
- **Recommend.** The ranking is about access (relevance, distance, open now, reviews,
  listing completeness), every weight is declared in `src/carefinder/ranking.py`, and the
  words "best", "recommended" and "highest quality" appear nowhere in any language.
- **Leak.** Google receives a coordinate, a radius, a fixed eye-care phrase and a
  language code. No name, no mobile number, no scan id, no grade, no report — asserted
  field by field in `tests/test_care_finder.py`.

Optional: with no key configured it says so in the patient's language and everything else
on the page is unaffected.

```bash
# .env
GOOGLE_MAPS_API_KEY=AIza...             # server-side; Places API (New) + billing enabled

make care-finder-check                  # configuration only, no API call
make care-finder-check AREA=Vijayawada  # ONE real Places call, end to end
```

Setup, the field mask and its billing tiers, the ranking weights, the privacy rules and
why the map is Leaflet rather than a second Google key: `docs/CARE_FINDER.md`.

## The five graded requirements

| # | Requirement | Where | Evidence it produces |
|---|---|---|---|
| 1 | Image quality + enhancement | `src/quality/` | 3 checks (thresholds fitted on SYNTHETIC data — refit needed); HTTP 422 + a recapture instruction naming the failed criterion |
| 2 | Structure segmentation | `src/segment/` | optic disc, fovea, Frangi vessels (Dice vs DRIVE — *not yet measured*), lesion counts by quadrant |
| 3 | DR severity grading | `src/grading/` | CORAL ordinal head; QWK + referable sens/spec with bootstrap CIs (*code ready; no real run yet*) |
| 4 | Explainability | `src/explain/` | Grad-CAM measured against lesion masks, ICDR rule cross-check, temperature scaling, PDF |
| 5 | Simulink workflow | `matlab/` | ophthalmologist FTEs with and without AI triage |

## The decisions worth defending

- **Ordinal (CORAL) head, not softmax.** The grades are ordered, so `P(grade ≥ 2)` — the
  referral decision — is a direct model output with its own tunable threshold.
- **Contrast-normalised sharpness, not Laplacian variance.** The textbook measure
  confuses a healthy smooth retina with a blurred one and would have quietly rejected
  healthy eyes. Pinned by a test.
- **The rule engine returns *unknown*, not *absent*,** for venous beading, IRMA and
  neovascularisation, which it cannot detect. Treating those as absent would under-grade
  the sickest patients.
- **The model runs in-process, not behind a hosted prediction endpoint.** Grad-CAM needs
  gradients an endpoint will not return. Cheaper too.
- **Vessel suppression only fires on elongated structures.** Frangi at small scales treats
  a microaneurysm as a ridge; suppressing on the raw mask deleted the lesions we count.
- **No number can be faked.** The dashboard reads `/v1/metrics`; no results file means the
  UI prints "not run yet". There is no placeholder to accidentally ship.

## Layout

```
src/quality/   quality gate + enhancement        src/api/      FastAPI backend
src/segment/   disc, fovea, vessels, lesions     web/          Next.js frontend
src/grading/   CORAL model, trainer, evaluation  matlab/       Simulink + classical baseline
src/explain/   Grad-CAM, calibration, ICDR rules, PDF
web/lib/i18n/  CareBridge translation layer        web/components/carebridge/  its UI
results/       every run's config + metrics      docs/         contract, blockers, clock, cost
```

## Documents

| File | What it is |
|---|---|
| `docs/BLOCKERS.md` | **what I need from you**, ordered by leverage |
| `EXPLAIN_IT_BLOCK1.md` | plain-English brief for defending this to a judge |
| `docs/API_CONTRACT.md` | the frozen v1 contract both tracks build against |
| `docs/CLOCK.md` | the 36-hour plan and what is already done |
| `docs/JUSTIFICATION.md` | why Kaggle GPU for the CNN and where MATLAB stays |
| `docs/BENCHMARKS.md` | the result tables — empty cells say "not run yet" |
| `docs/COST_LOG.md` | cloud spend. Currently $0.00 — this build is free-tier only |
| `docs/CAREBRIDGE.md` | the multilingual + voice + patient-explanation layer |
| `docs/PASSPORT.md` | longitudinal tracking: compare, follow up, remind, repeat |
