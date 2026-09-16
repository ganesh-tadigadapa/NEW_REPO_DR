# `src/api/` — The receptionist

**Plain job:** receive an uploaded photo, run every station in the right order, and hand
back one complete answer.

## The files

| File | Plain job |
|---|---|
| `main.py` | The front desk — receives uploads, checks file size and type |
| `pipeline.py` | The conveyor belt — runs stations 1 to 7 in order |
| `store.py` | Remembers what it has processed |
| `evidence.py` | Keeps the full evidence for each scan, and the doctors' review notes |
| `reports.py` | The doctors' report window — anonymised, verified doctors only |

`src/delivery/` sits alongside it: the patient's own report, sent to their WhatsApp. It
is a courier, not a station on the belt — see that folder's docstring and
[docs/WHATSAPP.md](../../docs/WHATSAPP.md).

## Who is allowed in

The front desk now checks for a sign-in ticket before it accepts an upload. That check
lives entirely in `src/auth/` — see the folder's own README. `pipeline.py` never learns
who uploaded an image, and the screening result does not depend on it.

`reports.py` is where a verified doctor reads back what the system has produced. It
builds each row one field at a time from a fixed list, so a patient's name or phone
number cannot end up there even if someone later puts one in a scan record.

## Two rules built into `pipeline.py`

1. **A photo that fails the quality check is never graded.** It returns the refusal and
   stops. There is no "grade it anyway with low confidence" path.
2. **Every station can fail independently without killing the answer.** No AI available?
   Quality, damage counts and rules still run, and the answer says why the grade is
   missing. Heat-map fails? The grade still comes back.

## Sending the report, without making a second one

`pipeline.py` builds the one-page PDF and puts it in the answer. `main.py` also hands
those exact bytes to `src/delivery/`, so the patient can have that same report sent to
their WhatsApp later without the AI, the heat-map or the PDF being made a second time.
The delivery layer cannot change a grade, a referral or anything else on the page.

## What "HTTP 422" means

When you see a photo refused, the engine returns a code called 422. That is **not an
error** — it is a successful refusal. The system is working exactly as designed.
