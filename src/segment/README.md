# `src/segment/` — Station 4: "Find the landmarks and count the damage"

**Plain job:** look at the photo and find things, using ordinary image processing.
**There is no AI in this folder at all.**

## What it finds

| Thing | Plain meaning |
|---|---|
| **Optic disc** | The bright circle where the nerve leaves the eye. A landmark. |
| **Fovea** | The dark spot at the centre of vision. A landmark. |
| **Blood vessels** | Traced so they aren't mistaken for bleeding. |
| **Microaneurysms** | Tiny dark dots — earliest damage. |
| **Haemorrhages** | Larger dark blots — bleeds. |
| **Exudates** | Bright yellow-white spots — leaked deposits. |

It also splits the eye into four quadrants and counts damage **per quadrant**, because
the official medical rules care where the damage is, not just how much.

## Why "no AI" matters

This folder is what gives the **second opinion**. If it used AI too, and the same AI,
the two opinions would agree by construction and prove nothing. Because this is plain
image processing, it is genuinely independent evidence.

## The files

- `structures.py` — optic disc, fovea, quadrants
- `lesions.py` — vessels and damage spots

## Four bugs were fixed here — do not undo them

Each one gave confident, well-formed, completely wrong answers:

1. Blur measurement confused "smooth healthy eye" with "blurry photo"
2. Vessel finder flagged 99% of the eye, deleting every damage spot
3. Then it found nothing at all on diseased eyes
4. It treated microaneurysms as tiny vessels and erased all 18 test cases

All four are now locked down by automatic tests.
