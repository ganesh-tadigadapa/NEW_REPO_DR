# `src/api/` — The receptionist

**Plain job:** receive an uploaded photo, run every station in the right order, and hand
back one complete answer.

## The files

| File | Plain job |
|---|---|
| `main.py` | The front desk — receives uploads, checks file size and type |
| `pipeline.py` | The conveyor belt — runs stations 1 to 7 in order |
| `store.py` | Remembers what it has processed |

## Two rules built into `pipeline.py`

1. **A photo that fails the quality check is never graded.** It returns the refusal and
   stops. There is no "grade it anyway with low confidence" path.
2. **Every station can fail independently without killing the answer.** No AI available?
   Quality, damage counts and rules still run, and the answer says why the grade is
   missing. Heat-map fails? The grade still comes back.

## What "HTTP 422" means

When you see a photo refused, the engine returns a code called 422. That is **not an
error** — it is a successful refusal. The system is working exactly as designed.
