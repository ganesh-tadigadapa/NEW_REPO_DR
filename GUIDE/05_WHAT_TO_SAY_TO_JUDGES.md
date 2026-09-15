# What to say to judges

MathWorks set this problem. Their engineers are likely on the panel.

---

## Your 30-second opening

> "India has 77 million diabetics and about one eye doctor per 100,000 rural people.
> We built a screening aid: a health worker uploads an eye photo and in five seconds gets
> a severity grade, a referral decision, a heat-map showing why, and a one-page report.
>
> What makes ours different is that we do not trust the AI on its own. A separate
> rule-checker independently counts the damage in the photo and applies the official
> medical criteria. When the two disagree, the case goes to a human doctor. We measured
> it: they disagree on 7 out of 10 photos, and every one of those escalates."

## The five questions you will definitely get

### 1. "Did you hit the 90% sensitivity target?"

> "On the standard validation set, yes — 92%. On a completely different hospital's
> dataset, no — 86%. We're telling you the second number because we ran that test once,
> on a frozen model, and logged it. Most submissions only quote the first."

**Do not get defensive.** This is your credibility moment.

### 2. "Why isn't the AI in MATLAB? We're MathWorks."

> "Three reasons, and one of them is a licence fact.
>
> One — MATLAB does real work here. It's our control arm: we built the old-fashioned
> non-AI pipeline in MATLAB and ran both on identical photos to prove the AI version is
> better. 0.54 versus 0.92. Your problem statement asks for that proof.
>
> Two — our Simulink model answers the resource question: 3 eye doctors without AI,
> 1 with.
>
> Three — we checked our MATLAB licence. It has no MATLAB Compiler and no Compiler SDK,
> and it's a trial licence. So MATLAB physically cannot be deployed as a public web
> service from this machine. The live system had to be Python. We also rebuilt our
> image-processing in MATLAB and verified it agrees with the Python to eight decimal
> places, so MATLAB validates the thing we actually ship."

### 3. "How do we know the AI isn't a black box?"

> "Three layers. A heat-map showing where it looked. A table of the actual damage spots
> we counted, by region of the eye. And an independent rule-checker that grades the same
> photo from those counts using the published medical criteria, with no AI at all. If the
> two disagree we escalate rather than pick one."

### 4. "What about grade 3 / severe cases?"

> "That's our weakest class — only 29 training examples existed. We often call it grade 2.
> But both grade 2 and grade 3 mean 'refer to a doctor', so the referral decision is
> unaffected. We'd rather tell you that than hide it."

### 5. "What can't it do?"

> "Four things. It can't detect neovascularisation, so our rule-checker can never confirm
> grade 4 on its own — it reports 'unknown' rather than 'absent', because treating
> 'can't see it' as 'not there' would under-grade the sickest patients. Its fovea
> detection is weak. It refuses about 1 in 5 good photos, which we chose deliberately.
> And no clinician has formally rated our heat-maps yet."

## Say these three things unprompted

They make you look rigorous rather than lucky:

1. **"Every number we show points to a file on disk. If we haven't measured something,
   our dashboard literally prints 'not run yet'. There is no placeholder that could
   accidentally ship."**

2. **"We opened the external test set exactly once, and the script logs it permanently so
   you can check we didn't peek twice."**

3. **"Turning on our quality checker did *not* improve our accuracy scores. We report that
   as a negative result. Its value is practical — it stops the system giving a confident
   answer on an unreadable photo — not statistical."**

## Things to NEVER say

| Don't say | Because |
|---|---|
| "We achieve 92% sensitivity" | Only on the practice set. Always give the external number too. |
| "We trained on Kaggle and Vertex AI" | Kaggle yes; Google Cloud never ran. |
| "Our quality gate improves accuracy" | We measured it. It doesn't. |
| "We detect all lesion types" | No neovascularisation detector. |
| "It's validated" | It's *externally tested*. Clinical validation needs a clinical trial. |
| "SimEvents model" | That version has never run — the toolbox isn't installed. Say "Simulink". |
| "It's a diagnostic tool" | **Never.** It is a screening triage aid. |

## If a judge finds a flaw you didn't mention

Say: *"You're right, and it's in our limitations slide."* Then show it. Every weakness in
this document is already written into `docs/BENCHMARKS.md` and `docs/STATE.md`.

A team that already knows its own flaws looks stronger than one that doesn't.

## The closing line

> "We'd rather show you an honest 86% on unfamiliar data than a polished 92% that only
> works on photos we trained near. In screening, the number that matters is the one you
> get in the field."
