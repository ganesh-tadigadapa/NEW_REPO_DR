# What each folder does

Think of the project as a **factory line**. A photo goes in one end, a report comes out
the other. Each folder is one station on that line.

---

## The journey of one photo

```
  Health worker uploads a photo
            |
            v
  [1] Is the photo usable?  ---- NO ---->  Refuse + "retake it like this"
            |                              (STOP. Never graded.)
           YES
            |
            v
  [2] Clean the photo up (brightness, contrast)
            |
            v
  [3] AI reads it  ------->  severity 0-4  +  "needs a doctor?"  +  confidence
            |
            v
  [4] Find landmarks + count damage spots (no AI - plain image processing)
            |
            v
  [5] Rule-checker gives its OWN severity from those spot counts
            |
            v
  [6] Compare AI vs rules.  Disagree?  ->  send to a human doctor
            |
            v
  [7] Draw the heat-map, build the PDF
            |
            v
  Report shown on screen
```

---

## The folders that DO the work

| Folder | Station | What it does, plainly |
|---|---|---|
| `src/quality/` | **[1]** | Decides if a photo is good enough. Checks 3 things: is it sharp, is the lighting even, is the whole eye in frame. Writes the "retake it like this" message. |
| `src/common/` | **[2]** | Shared basics: opening image files, cropping to the round eye area, brightening, saving. Used by every other station. |
| `src/grading/` | **[3]** | The AI itself. How it is built, how it was taught, and how it answers a new photo. |
| `src/segment/` | **[4]** | Finds eye landmarks (optic disc, fovea) and blood vessels, then counts damage spots by region. **No AI — plain image processing.** |
| `src/explain/` | **[5][6][7]** | The "show your working" station. The rule-checker second opinion, the heat-map, the confidence adjustment, and the PDF. |
| `src/api/` | — | The receptionist. Receives the uploaded photo, runs stations 1–7 in order, hands back the result. |
| `web/` | — | The website you see in a browser. Buttons, pages, pictures. |
| `matlab/` | — | Our "control group" and the hospital-planning simulation. See below. |

## The folders that HOLD things (no work happens here)

| Folder | What is inside |
|---|---|
| `artifacts/model/` | **The trained AI brain itself** (a 234 MB file) plus its settings. This is the valuable output of training. |
| `results/` | **Every number we can quote.** One folder per experiment. If a number is not in here, we are not allowed to say it. |
| `data/` | Working image files. The big datasets live outside the project. |
| `docs/` | The detailed technical write-ups. |
| `GUIDE/` | These plain-English notes. |
| `tests/` | 45 automatic checks that prove the code still works after any change. |
| `scripts/` | One-off jobs you run by hand (train, evaluate, compare). |
| `notebooks/` | The file we pasted into Kaggle to train the AI on a free GPU. |
| `deploy/` | Instructions and settings for putting the site on the internet. |

## What the MATLAB part is for

MathWorks (who make MATLAB) set this problem, so MATLAB matters politically as well as
technically. Ours does two real jobs:

1. **The control group** (`matlab/classical/`). We built an old-fashioned,
   non-AI version of the same system. Then we ran both on the *same* photos to prove the
   AI version is actually better. It is: **0.54 vs 0.92** on our main score. The problem
   statement explicitly asks for this proof.
2. **The hospital planner** (`matlab/simulink/`). A simulation of a whole district
   screening 100,000 people a year. It answers: *how many eye doctors do we need, with
   and without our AI?* Answer: **3 without, 1 with.**

There is also `matlab/reference/` — we rebuilt some of our image-processing in MATLAB and
checked it gives the *same answer* as the Python version. It matches to 0.00000000%.
That proves our Python version is correct.

## Why the folders have technical names

You may wonder why it is `src/segment/` and not `find_the_damage_spots/`.

- These names are written inside **108 places** in the code. Renaming them risks breaking
  a system that currently passes all 45 tests and has been validated on a second hospital's
  data.
- **This guide is the safer way** to give you the same understanding.
- Each folder also has its own plain-English `README.md` inside it.

If you still want the folders physically renamed, say so and I will do it carefully and
re-run every test to prove nothing broke. It is possible — it is just risk we do not need
to take this close to the deadline.
