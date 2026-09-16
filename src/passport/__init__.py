"""CareBridge Eye Health Passport — the longitudinal layer.

One patient, many screenings, over years. This package is what turns a sequence of
independent one-off results into a record that can be compared, followed up and carried
forward:

    SCREEN -> SAVE -> FOLLOW-UP PLAN -> REMINDER -> RETURN -> NEW SCREENING
           -> COMPARE -> COMPARISON REPORT -> WHATSAPP -> UPDATED FOLLOW-UP PLAN -> ...

**What this package does not do, and must never do.** It does not grade an image, does
not load a model, does not touch a pixel and does not change a clinical value. Every
grade, label, quality verdict and referral decision it handles was produced by the
existing pipeline and is copied VERBATIM. `comparison.py` subtracts two integers the
model already decided and names the difference; that is the whole of its cleverness.

Like `src/delivery` and `src/carefinder`, it is mounted as a router from
`src/api/main.py` so it stays entirely outside the medical pipeline. `src/api/pipeline.py`
is unchanged and knows nothing about accounts, history or follow-ups.

Ownership lives here, not on the scan record. `/v1/analyze` still refuses to write the
caller onto the medical record — the screening result must not depend on who uploaded
the image — so the patient↔screening link is a separate row in a separate store, exactly
as `src/delivery/media.py` already does for report delivery.
"""
from __future__ import annotations

__all__ = ["comparison", "followup", "store", "routes"]
