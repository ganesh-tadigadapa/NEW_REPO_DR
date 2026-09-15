# Start here — what this project actually is

Written for someone with no coding or medical background.

---

## The problem, in one paragraph

India has ~77 million diabetic adults. Diabetes slowly damages blood vessels at the back
of the eye. This is called **diabetic retinopathy**. Caught early, 90% of the resulting
blindness is preventable. Caught late, it is not.

To catch it you photograph the back of the eye and an eye doctor looks at the photo.
Rural India has roughly **one eye doctor per 100,000 people**. There are not nearly
enough doctors to look at every photo.

## What we built

A system where a health worker uploads an eye photo and gets back, in about 5 seconds:

1. **Is this photo even usable?** If it is blurry or badly framed, we refuse it and tell
   the worker how to retake it. A bad photo must never get a confident-looking answer.
2. **How severe is the disease?** A score from 0 (healthy) to 4 (worst).
3. **Does this person need to see a doctor?** Yes/no.
4. **Why did the computer say that?** A heat-map showing which parts of the photo drove
   the decision, plus a count of the actual damage spots found.
5. **A second opinion.** A completely separate check, using written medical rules, that
   looks at the damage spots and produces its own severity score. If the two disagree,
   we send the case to a human doctor instead of guessing.
6. **A one-page PDF** the doctor can sign off in under 30 seconds.

## The one thing that makes our project different

Most teams build: *photo → AI → answer → heat-map*. The AI is a black box and nobody
can check it.

We build **two independent opinions**:

- **Opinion A** — the AI, which learned from 3,662 real labelled photos.
- **Opinion B** — a rule-checker that counts actual damage spots and applies the official
  medical grading rules. **No AI involved at all.**

Then we compare them. **When they disagree, we escalate to a human rather than picking
one.** We measured this: they disagree on about 7 out of 10 real photos, and every one of
those goes to a doctor.

That is the honest answer to "how do we know the AI isn't wrong?" — we don't fully trust
it, so we built something to argue with it.

## The second thing that makes us different

**We never make a number up.**

- If we have not measured something, the screen literally says "not run yet".
- Every number in our slides points to a file on disk that produced it.
- We tested our system on a completely different hospital's photos and **our score got
  worse** — and we published that instead of hiding it.

Most submissions show you their best number. We show you the one that counts.

## Words you will hear, in one line each

| Word | Plain meaning |
|---|---|
| **Fundus photo** | A photograph of the back of the eye |
| **Retinopathy** | Damage to the back of the eye caused by diabetes |
| **Grade 0–4** | Severity: 0 = healthy, 4 = worst |
| **Referable** | Grade 2 or worse — this person must see a doctor |
| **Model** | The AI that learned from examples |
| **Training** | Showing the AI thousands of labelled photos so it learns |
| **Heat-map (Grad-CAM)** | A colour overlay showing where the AI was looking |
| **Lesion** | A spot of damage in the eye |

Full glossary: `02_WORDS_EXPLAINED.md`

## Where to go next

| You want to... | Read |
|---|---|
| Know what each folder holds | `01_WHAT_EACH_FOLDER_DOES.md` |
| Understand a word | `02_WORDS_EXPLAINED.md` |
| Understand our results | `03_OUR_NUMBERS_EXPLAINED.md` |
| Run the thing | `04_HOW_TO_RUN_IT.md` |
| Prepare for judges | `05_WHAT_TO_SAY_TO_JUDGES.md` |
