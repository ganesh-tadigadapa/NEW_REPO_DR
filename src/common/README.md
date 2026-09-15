# `src/common/` — Shared basics

**Plain job:** the small helpers every other station needs. Nothing clever happens here.

## The files

| File | Plain job |
|---|---|
| `imaging.py` | Opening photo files, cropping to the round eye, brightening, saving |
| `config.py` | Settings in one place — where files live, what the labels are |

## Why it exists separately

The *exact same* cleaning steps must be applied when teaching the AI and when answering a
real photo. If those two ever drifted apart, the AI would be shown something different
from what it learned on, and accuracy would quietly drop with no error message.

Keeping them in one shared file makes that mistake impossible.

## One rule worth knowing

`config.py` never hard-codes a result. Scores are always read from files in `results/`.
That is what makes it impossible for us to accidentally show a made-up number.
