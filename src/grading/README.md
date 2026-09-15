# `src/grading/` — Station 3: The AI itself

**Plain job:** look at a cleaned-up photo and say how severe the disease is, 0 to 4.

## The files

| File | Plain job |
|---|---|
| `model.py` | The AI's *design* — its shape and wiring |
| `data.py` | How photos are fed in during learning |
| `train.py` | The teaching process |
| `predict.py` | Answering one new photo |
| `evaluate.py` | Scoring how well it did |

## Our design choice, in plain terms

Most AIs would ask: *"which of these 5 boxes does it go in?"* — treating "said 0, truth
4" and "said 3, truth 4" as equally wrong.

Clinically those are wildly different. Ours asks **4 yes/no questions instead**:

- Worse than 0? Worse than 1? Worse than 2? Worse than 3?

The grade is just how many answers were yes. Two benefits:

1. It can never skip a grade or contradict itself.
2. **"Does this person need a doctor?"** is literally the answer to question 2 — a single
   number we can tune directly, rather than something we work out afterwards.

## The trained AI is not in this folder

The AI's actual learned "brain" is a 234 MB file at `artifacts/model/model.keras`.
This folder holds the *instructions* for building and using it.

## It is frozen

The AI was trained once, on 3,112 real photos, on a free Kaggle GPU, in 73 minutes.
It has been locked ever since so our test results stay honest. **Do not retrain it.**
