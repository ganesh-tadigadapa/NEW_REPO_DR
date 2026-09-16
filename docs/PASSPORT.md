# CareBridge Eye Health Passport

Diabetic retinopathy is a disease of **change over time**. A single screening answers
"what does this photograph show?"; it cannot answer the question that actually decides
whether someone keeps their sight, which is "what has changed since last time, and when
should this person come back?"

The Eye Health Passport is that second question. It is the loop:

```
SCREEN → SAVE → FOLLOW-UP PLAN → REMINDER → RETURN → NEW SCREENING
      → COMPARE → COMPARISON REPORT → WHATSAPP → UPDATED FOLLOW-UP PLAN → ⟲
```

---

## What it is not

**It does not touch the AI.** No file in `src/passport/` imports the model, loads a
weight, reads a pixel or evaluates a threshold. EfficientNetV2-S, CORAL, the frozen
weights, the quality gate, Grad-CAM, the calibration and the ICDR rule engine are byte-for-byte
unchanged, and `src/api/pipeline.py` does not know this package exists.

Every clinical value the passport handles was produced by the existing pipeline and is
copied **verbatim**. The entire cleverness of `comparison.py` is that it subtracts two
integers the model already decided and names the difference.

**It does not diagnose.** See "The sentence problem" below.

---

## Architecture

Mounted as a router from `src/api/main.py`, exactly like `src/delivery` and
`src/carefinder`, so it stays entirely outside the medical pipeline.

| File | What it owns |
|---|---|
| `store.py` | the longitudinal record: screenings, follow-ups, access grants |
| `comparison.py` | one subtraction, and the words that may be said about it |
| `followup.py` | the configured guideline table and the precedence rules |
| `service.py` | the loop, assembled — save → compare → re-plan |
| `report.py` | the comparison PDF, on the existing reportlab layer |
| `message.py` | the WhatsApp text, in the four CareBridge languages |
| `media.py` | the comparison PDF inside the existing report media store |
| `routes.py` | the HTTP surface and its three authorisation rules |

### Ownership lives here, not on the scan

`/v1/analyze` still refuses to write the caller onto the medical record — the screening
result must not depend on who uploaded the image. So the patient↔screening link is a row
in the passport store, exactly as report ownership is a row in the delivery store. The
pipeline still knows nothing about accounts.

### The analyse contract did not move

The comparison is fetched by its own endpoint after `/v1/analyze` returns. A screening
result must not begin to depend on how many times the person has been screened before,
and `tests/test_carebridge_i18n.py::test_the_analyze_contract_was_not_changed_for_a_ui_feature`
pins the response shape against exactly this kind of drift.

---

## The sentence problem

This is the part of the feature that could do real harm, so it is worth stating plainly.

Grade 1 last year and grade 2 today is **a fact about two screening results**. Between
them sit a different day, a different camera, a different pupil, a different photographer,
and a model with its own error rate. It is *not* proof that the disease progressed.

So every sentence the system produces is phrased about the screening result:

> The current screening result is one ICDR category higher than the previous screening.

and never about the eye. The permitted wording lives in `comparison.py::_STATEMENTS` and
nowhere else. `tests/test_passport_longitudinal.py::test_no_comparison_ever_claims_the_disease_changed`
runs all 25 pairs of grades on the scale and asserts that "worsened", "progressed",
"deteriorated", "improved" and "definitely" appear in none of them.

Every comparison also carries its own caveat, in the API, in the PDF, in the WhatsApp
message and on the card:

> This compares two screening results. It is not a diagnosis, and it is not by itself
> evidence that the disease has changed. Only an eye-care professional can say that.

### The ordinal problem

ICDR grade is an ordinal **category** (0–4), not a measurement. One category between 0 and
1 is not the same clinical quantity as one between 3 and 4. So nothing in this feature
averages grades, fits a trend, computes a rate of change per month, or draws a sloped line
between two visits. The timeline is a **step**: it holds each grade until the next
screening changes it. A pie chart would be worse still — these are not parts of a whole.

### Ungradeable is not a result

A photograph the quality gate refused is a real event on the timeline and is shown there,
as a hollow marker on the axis floor. It is never one half of a comparison, and it does not
become the "previous result" for the visit after it — that visit is compared with the last
one that was actually graded. It gets a repeat-photograph suggestion rather than a
screening interval.

---

## The follow-up table

There is deliberately **no single universal interval**. `followup.py::GUIDELINE_WINDOWS`
is a table keyed by ICDR grade, in one place, so a programme can retune it to its own
protocol without touching a route, a UI or a test:

| grade | window | priority |
|---|---|---|
| 0 | 12–24 months | routine |
| 1 | 12 months | routine |
| 2 | 6 months | soon |
| 3 | 1–3 months | prompt |
| 4 | within 1 month | urgent |
| *(refused image)* | within 1 month, repeat photograph | prompt |

Grades 3 and 4 are expressed as **prompt specialist referral**, not as a long-term
reminder: a severe or proliferative result is not something to put a date on months away.

These are labelled defaults for a demo and a deployment is expected to replace them with
its own programme's protocol. The system says "suggested follow-up", never "you must
return in X months".

### Precedence, strictly in this order

1. **An explicit clinician recommendation wins outright.** The table is not consulted.
2. **A clinician's own grade replaces the model's** as the input to the table.
3. **Otherwise the table decides**, brought forward one step when the category has risen.

---

## Authorisation

Three audiences, three *different* rules.

**A patient reaches their own record by ownership, not by role.** No patient-facing
endpoint takes an account id, so a patient cannot ask for someone else's timeline by
editing a URL; the only id they can supply names a screening, and a screening that is not
theirs answers `404`.

**A doctor needs a care relationship, not just a role.** A verified doctor can already
read the anonymised report collection. A longitudinal record is a different kind of object
— it links several screenings to one person over time — so it additionally requires an
access grant for that specific patient. Exactly two things create one:

* the doctor **records a clinician review** on one of that patient's screenings, which is
  precisely the act that makes their history relevant to that doctor, or
* an **administrator** assigns it.

**404, not 403, for a record that is not yours.** A different status would turn these
endpoints into an oracle confirming that a screening id or an account id exists.

**The doctor view is anonymised by construction.** It is a whitelist with no name, no
mobile number and no patient reference; the patient is identified by the internal account
id only, the same class of opaque value as a scan id.

**Nothing medical is logged.** No grade, no comparison, no patient id and no count of
anybody's screenings appears in a log line from this package.

---

## WhatsApp

Uses the **existing** `WhatsAppReportService` and its provider abstraction, unchanged and
unextended — this feature knows nothing about Twilio or Meta, and adding a third provider
would not touch it. The comparison PDF is stored in the existing report media store under
`cmp_<screening_id>`, so it inherits the signed short-lived media URL, the ownership
check, the delivery log and the resend cooldown with no second mechanism.

The two documents are not interchangeable: the metadata carries
`kind: "comparison_report"`, and the screening-report endpoint refuses to send anything
that is not a screening report — it composes screening-report wording and must not be able
to attach a comparison to it.

`success: true` means the provider **accepted** the message. It never asserts receipt.
When delivery fails for any reason, the comparison is still on the website, the PDF is
still downloadable, and the status shown is the true one.

The follow-up reminder goes out over the same `send_report` path with the patient's own
most recent report attached. A reminder names no grade, no severity and no referral status
— it is read on a lock screen, and by whoever is holding the phone.

---

## Configuration

| Variable | Default | What it does |
|---|---|---|
| `PASSPORT_ENABLED` | `1` | switch the whole feature off without touching a route |
| `PASSPORT_STORE_DIR` | `data/interim/passport` | where the longitudinal record lives |
| `PASSPORT_MAX_HISTORY` | `200` | bound on one patient's timeline |
| `PASSPORT_RESEND_COOLDOWN_SECONDS` | `60` | duplicate protection for the comparison send |

---

## Tests

| File | Covers |
|---|---|
| `tests/test_passport_longitudinal.py` | save, retrieve, compare (same / higher / lower / multi-visit), timeline ordering, the absent cases, follow-up creation and update, both kinds of clinician override, and the full acceptance scenario |
| `tests/test_passport_delivery.py` | comparison report generation, message content in every language, provider success and every failure mode, duplicate protection, the reminder, and that the PDF survives a delivery failure |
| `tests/test_passport_authorization.py` | patient ownership, doctor grants, the 404-not-403 rule, admin assignment, and anonymity of the doctor view |
| `web/tests/passport.test.tsx` | the comparison card, the step timeline, the journey list, the follow-up card, comparison delivery, the returning-patient banner, and dictionary parity |

No test sends a real WhatsApp message. The provider is a callable that records what it was
asked to do.
