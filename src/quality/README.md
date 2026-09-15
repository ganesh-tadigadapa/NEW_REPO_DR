# `src/quality/` — Station 1: "Is this photo usable?"

**Plain job:** look at an uploaded eye photo and decide whether it is good enough to
grade. If not, refuse it and tell the health worker exactly how to retake it.

## The three checks

| Check | Plain meaning | Fails when |
|---|---|---|
| **Focus** | Is it sharp? | Blurry — you can't see the tiny damage spots |
| **Illumination** | Is the lighting even? | One side washed out or in shadow |
| **Field of view** | Is the whole round eye in frame? | Camera too far back or off-centre |

## Why this station exists at all

A blurry photo given a confident grade is the most dangerous thing this system could do.
**A photo that fails here is never graded.** There is no "grade it anyway" path.

## The file

- `gate.py` — all three checks, plus the retake messages.

## What the numbers mean

The pass/fail cut-offs are not guesses. They were fitted on 200 real photos and then
tested on 60 the fitting never saw:

- Catches **89%** of bad photos (was 44% before we refit)
- Wrongly refuses **21%** of good photos — a deliberate trade

We accept refusing some good photos because the patient is still in the room and can
simply retake it. Letting a bad photo through gives a confident wrong answer to someone
who has already gone home.
