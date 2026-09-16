# API contract — FROZEN at build hour 2

The frontend builds against this. The backend fills it in. **Changing a field name after this point
costs more than it saves.** Version: `v1`.

Base URL: `${NEXT_PUBLIC_API_BASE}` (local: `http://localhost:8080`)

---

## `GET /health`

```json
{ "status": "ok", "version": "v1", "model_loaded": true, "model_id": "stub|run-YYYYMMDD-xxx" }
```
`model_loaded: false` means the API is up but no trained weights are present. The UI must still work —
it shows a "model not loaded" banner. This is what lets us deploy on hour 1.

---

## `POST /v1/analyze`

`multipart/form-data`, field `file` = the fundus image (JPEG/PNG, ≤ 12 MB).
Optional field `patient_ref` (string, free text, no PII enforced by us).

### 200 — graded

```json
{
  "scan_id": "sc_01J8...",
  "created_at": "2026-09-11T14:03:22Z",
  "model_id": "run-20260911-a1",
  "disclaimer": "Screening triage aid. Not a diagnostic device.",

  "quality": {
    "gradeable": true,
    "overall_score": 0.81,
    "checks": {
      "focus":        { "passed": true,  "value": 142.7, "threshold": 55.0,  "unit": "laplacian_var" },
      "illumination": { "passed": true,  "value": 0.22,  "threshold": 0.45,  "unit": "grid_cv" },
      "field_of_view":{ "passed": true,  "value": 0.87,  "threshold": 0.60,  "unit": "retina_frac" }
    },
    "enhanced": true,
    "recapture_instruction": null
  },

  "grading": {
    "icdr_grade": 2,
    "icdr_label": "Moderate NPDR",
    "referable": true,
    "ordinal_score": 2.13,
    "confidence": 0.88,
    "confidence_calibrated": true,
    "per_grade_probability": [0.02, 0.09, 0.61, 0.24, 0.04],
    "threshold_set": "val-tuned-2026-09-11"
  },

  "lesions": {
    "microaneurysms": { "count": 14, "by_quadrant": {"ST": 4, "SN": 3, "IT": 5, "IN": 2} },
    "haemorrhages":   { "count": 9,  "by_quadrant": {"ST": 2, "SN": 1, "IT": 4, "IN": 2} },
    "hard_exudates":  { "count": 6,  "by_quadrant": {"ST": 1, "SN": 0, "IT": 3, "IN": 2} },
    "method": "classical-cv"
  },

  "rule_check": {
    "rule_grade": 2,
    "rule_label": "Moderate NPDR",
    "criteria_fired": ["microaneurysms_present", "haemorrhages_present"],
    "four_two_one": { "haemorrhages_4q": false, "venous_beading_2q": false, "irma_1q": false, "severe": false },
    "agrees_with_cnn": true,
    "flag": null
  },

  "explain": {
    "gradcam_png_b64": "iVBORw0KGgo...",
    "overlay_png_b64": "iVBORw0KGgo...",
    "lesion_overlay_png_b64": "iVBORw0KGgo...",
    "attention_summary": "Attention concentrated in the inferotemporal quadrant, co-located with 5 detected microaneurysms."
  },

  "report": { "pdf_b64": "JVBERi0x...", "filename": "dr-report-sc_01J8.pdf" },

  "timing_ms": { "quality": 41, "preprocess": 88, "grading": 1320, "gradcam": 410, "lesions": 690, "report": 180, "total": 2729 }
}
```

### 422 — ungradeable (this is a SUCCESS path, not an error)

The single most important response in the demo. HTTP 422, and the body is still well-formed:

```json
{
  "scan_id": "sc_01J8...",
  "created_at": "2026-09-11T14:03:22Z",
  "disclaimer": "Screening triage aid. Not a diagnostic device.",
  "quality": {
    "gradeable": false,
    "overall_score": 0.19,
    "checks": {
      "focus":        { "passed": false, "value": 12.4, "threshold": 55.0, "unit": "laplacian_var" },
      "illumination": { "passed": true,  "value": 0.31, "threshold": 0.45, "unit": "grid_cv" },
      "field_of_view":{ "passed": true,  "value": 0.79, "threshold": 0.60, "unit": "retina_frac" }
    },
    "enhanced": false,
    "recapture_instruction": "Image is out of focus. Clean the camera lens, ask the patient to fixate on the target, and retake."
  },
  "grading": null, "lesions": null, "rule_check": null, "explain": null, "report": null,
  "timing_ms": { "quality": 38, "total": 38 }
}
```

**Rule: we never grade an image that failed the gate.** `grading` is `null`, not a guess.

### 400 / 413 / 500

```json
{ "error": { "code": "unsupported_media_type|file_too_large|internal", "message": "human readable" } }
```

---

## `POST /v1/review/{scan_id}`

The ophthalmologist's decision. Times the <30 s requirement instead of asserting it.

```json
{ "agrees": true, "corrected_grade": null, "notes": "", "seconds_to_decide": 21.4 }
```
→ `{ "ok": true, "scan_id": "...", "recorded_at": "..." }`

## `GET /v1/scans?limit=50`

Dashboard feed. `{ "scans": [ { "scan_id", "created_at", "icdr_grade", "referable", "gradeable", "reviewed", "agrees" } ] }`

## `GET /v1/metrics`

Everything on the dashboard comes from here so **no number is hardcoded in the UI**.
Returns the contents of the active `results/<run>/metrics.json`, or `{"available": false, "reason": "not run yet"}`.

---

# Addendum — access control (added after the freeze)

**The v1 medical contract above is unchanged.** Every field, shape and status code is
exactly as frozen. What changed is *who may call it*: `POST /v1/analyze`,
`GET /v1/scans` and `POST /v1/review/{scan_id}` now require a session, and `/v1/scans`
no longer echoes `patient_ref` (a field the UI never displayed). Everything below is
additive. Architecture and rationale: `docs/AUTH.md`.

Authentication is `Authorization: Bearer <token>`, or the `dr_session` HttpOnly cookie on
a same-site deployment.

## `POST /v1/auth/request-otp`

```json
{ "mobile": "+919876543210", "intent": "login|signup",
  "role": "user|doctor",
  "doctor_profile": { "doctor_name": "...", "registration_number": "...", "hospital": "..." } }
```

`role` and `doctor_profile` are read only when `intent` is `signup`, and are held with
the challenge so the redemption cannot change them. `intent: "login"` on an unknown
number is `404 no_account`; `intent: "signup"` on a known one is `409 account_exists`.

→ `200`

```json
{ "ok": true, "message": "OTP sent to +91 ***** 43210",
  "mobile_masked": "+91 ***** 43210", "expires_in": 300, "resend_after": 30,
  "otp_length": 6, "intent": "signup", "delivery": "sms",
  "dev_otp": "418203", "dev_warning": "DEVELOPMENT MODE: ..." }
```

`dev_otp` / `dev_warning` appear **only** when the API runs with `OTP_MODE=development`,
which cannot be combined with `AUTH_ENV=production` — the service refuses to start.

→ `429` with `Retry-After` for `resend_too_soon` / `too_many_requests`.

## `POST /v1/auth/verify-otp`

```json
{ "mobile": "+919876543210", "otp": "123456" }
```

→ `200`

```json
{ "ok": true, "created": true, "token": "<session token>", "token_type": "bearer",
  "expires_at": 1789000000.0,
  "account": { "account_id": "acc_...", "mobile": "+919876543210",
               "mobile_masked": "+91 ***** 43210", "role": "doctor",
               "doctor_verified": false, "status": "active", "created_at": "...",
               "can_read_reports": false, "doctor_profile": { ... } },
  "next": "/screen", "doctor_verification_pending": true }
```

`next` is computed by the **backend** from the stored role, so the client is not the
thing deciding where a doctor may go. Errors: `400 otp_expired | otp_already_used |
no_otp_requested`, `401 invalid_otp`, `429 too_many_attempts`.

## `POST /v1/auth/logout` · `GET /v1/auth/me` · `GET /v1/auth/session`

`logout` revokes the token's id until its natural expiry. `me` returns the account plus a
`permissions` block and requires a session; `session` is the unauthenticated-safe variant
that returns `{"authenticated": false}` instead of a 401.

## `GET /v1/reports` — verified doctor only

Anonymised by construction: the response is built field by field from a whitelist. No
`patient_ref`, no name, no mobile number, at any depth.

```json
{ "reports": [ { "scan_id": "sc_01d9...", "created_at": "...",
                 "ai_grade": 2, "ai_label": "Moderate NPDR", "referable": true,
                 "confidence": 0.91, "rule_grade": 2, "rule_flag": null,
                 "escalated": false, "quality_status": "pass", "quality_score": 0.81,
                 "explanation_available": true, "screening_reviewed": false,
                 "review_status": "pending", "review_status_label": "Pending",
                 "reviewed_at": null } ],
  "count": 1, "anonymised": true, "note": "..." }
```

Optional `?limit=`, `?referable=`, `?status=`.

`403` carries the reason so the UI can distinguish the two cases:
`doctor_access_required` ("Doctor access required.") and
`doctor_verification_pending` ("Doctor verification pending.").

## `GET /v1/reports/{scan_id}` — verified doctor only

The same scan with its full evidence, in five sibling blocks that mirror the medical data
model: `ai`, `quality` + `lesions` + `explain` (clinical evidence, including the Grad-CAM
and lesion overlay PNGs), `rule_engine`, `screening_recommendation`, and
`clinician_review` + `clinician_review_history`.

## `POST /v1/reports/{scan_id}/review` — verified doctor only

```json
{ "status": "reviewed|needs_further_review|confirmed|disagreed",
  "notes": "", "clinician_grade": 3 }
```

Appends one entry to a review ledger held in a **different file** from the scan record.
The AI grade, rule grade and referral decision are untouched — the response echoes
`ai_grade_unchanged` and `ai_referable_unchanged` so a caller can verify it.

## `GET /v1/auth/admin/doctors` · `POST /v1/auth/admin/doctors/{id}/verify` — admin only

The doctor verification queue and decision. `doctor_verified` is writable through no
other endpoint.

---

# Addendum — report delivery (added after the freeze)

A **communication layer**, not a clinical one. It moves an already-generated report; it
cannot produce, alter or reinterpret one. `POST /v1/analyze` and every response shape
above are unchanged. Full notes: [docs/WHATSAPP.md](WHATSAPP.md).

## `POST /v1/reports/{scan_id}/whatsapp` — the report's own patient

```json
{ "language": "en|hi|te|pa" }
```

Delivers the PDF the pipeline **already generated** for that scan to the caller's own
registered mobile number, with a short message composed from that same result.

There is deliberately **no recipient field**. The number is read from the authenticated
session, so a caller cannot direct a report to a number of their choosing, and the patient
never has to type theirs. Ownership is recorded in the delivery layer (not on the scan
record, which still has no owner by design); a report belonging to another account answers
`404 report_not_found`, identical to a report that does not exist.

```json
{ "success": true, "channel": "whatsapp", "message": "Report sent successfully",
  "to_masked": "+91 ***** 40001", "sent_at": "…", "duplicate": false }
```

Failures use the same shape with `success: false` and a stable `code`
(`not_configured`, `recipient_not_reachable`, `session_window_closed`, `rate_limited`,
`media_unreachable`, `provider_unreachable`, …) which the frontend maps to a translated
sentence. Provider detail never reaches the client. `duplicate: true` means the report had
just been delivered and was **not** sent a second time.

`success: true` means the provider ACCEPTED the message. It does not assert delivery or
receipt, and no UI claims otherwise.

## `GET /v1/reports/media/{scan_id}.pdf?token=…`

Serves one report to the messaging provider, which fetches media itself and cannot carry a
session token. The token is an HMAC signature over the scan id and an expiry (default 15
minutes), minted only by the send path for a report the caller has just proved they own.
No token, a wrong token, an expired token, a token for a different report and a missing
report all return an identical `404`. Excluded from the OpenAPI schema.

## `GET /health` — one added block

```json
{ "whatsapp": { "enabled": true, "mode": "live", "configured": false,
                "reason": "missing TWILIO_WHATSAPP_FROM", "report_pdf_retained": true } }
```

Whether delivery would work, and which variable is missing when it would not. No
credential, sender number or URL appears here.

---

# Addendum — Smart Care Finder (added after the freeze)

An **access layer**, not a clinical one. It moves nobody's data and produces no medical
value; it answers "where can this person go next". `POST /v1/analyze` and every response
shape above are unchanged. Full notes: [docs/CARE_FINDER.md](CARE_FINDER.md).

## `GET /v1/care-finder/nearby` — any authenticated account

```
?latitude=16.5062&longitude=80.6480&radius_m=5000&language=te
?area=Vijayawada&radius_m=10000&language=hi
```

Eye-care facilities near a device position, or near a locality the patient typed. A
session is required for spend control only — the account reaches the rate limiter and
nothing else, and is never sent to Google.

`latitude` is validated to −90…90 and `longitude` to −180…180 (`422` outside, before any
Google call). `radius_m` is clamped server-side to the configured minimum and maximum.

```json
{ "ok": true, "center": {"latitude": 16.5062, "longitude": 80.648},
  "center_source": "device", "area_label": null, "radius_m": 5000,
  "count": 1, "cached": false, "attribution": "Powered by Google",
  "disclaimer": "…not a recommendation or an endorsement…",
  "results": [{ "place_id": "ChIJ…", "name": "Vasan Eye Care",
                "latitude": 16.508, "longitude": 80.649, "distance_meters": 1240,
                "badges": ["nearby", "eye_focused", "open_now"],
                "address": "…", "rating": 4.5, "review_count": 312,
                "open_now": true, "phone": "…", "website": "…",
                "maps_url": "…", "types": ["ophthalmologist"] }] }
```

**Every field after `badges` is optional and absent when Google did not return it.** No
placeholder, no default, no estimate. `distance_meters` is a straight-line distance
computed by this API from two coordinates Google returned, labelled approximate in the UI.

A `200` with `"results": []` means nothing eye-related is listed inside the radius — a
real answer, not an error. It never asserts that the region has none.

Failures use `{"ok": false, "code": "…"}` with a stable code the frontend maps to a
translated sentence (`not_configured`, `api_disabled`, `invalid_key`, `billing_problem`,
`quota_exceeded`, `rate_limited`, `provider_unreachable`, `provider_error`,
`area_not_found`). Google's own error text never reaches the client.

Nothing about the screening travels on this request. There is no field for a scan id, a
grade, a patient reference or a report, and the request body sent on to Google carries
only a coordinate, a radius, a fixed eye-care phrase and a language code.

## `GET /v1/care-finder/status` — any authenticated account

Whether a search would work, plus the radius limits the UI draws its buttons from. No
key, no key prefix, no key length.

## `GET /health` — one added block

```json
{ "care_finder": { "enabled": true, "configured": false,
                   "reason": "missing GOOGLE_MAPS_API_KEY",
                   "default_radius_m": 5000, "max_radius_m": 25000,
                   "max_results": 20, "detail_fields": true } }
```

---

# Addendum — CareBridge Eye Health Passport (added after the freeze)

A **longitudinal layer**, not a clinical one. It records the screenings a patient has
already had, compares two results the model already produced, and plans when they should
come back. It cannot grade an image, cannot load a model, and nothing it does can change a
grade, a referral or a report. `POST /v1/analyze` and every response shape above are
**unchanged** — the comparison is fetched by its own endpoint, because a screening result
must not begin to depend on how many times the person has been screened before. Full
notes: [docs/PASSPORT.md](PASSPORT.md).

**Ownership.** The scan record still has no owner, by design. The patient↔screening link is
a row in the passport store, exactly as report ownership is a row in the delivery store.

**Authorisation, in three different rules.** A patient reaches their own record by
OWNERSHIP, never by role. A verified doctor additionally needs an access GRANT for that
specific patient — created when they record a clinician review on one of that patient's
screenings, or by an administrator. A record that is not yours answers `404`, never `403`:
a different status would confirm that the screening id or the account id exists.

## `GET /v1/passport` — the caller's own record

```json
{ "history_count": 2, "has_history": true,
  "timeline": [ { "screening_id": "sc_…", "date": "…", "icdr_grade": 1,
                  "severity_label": "Mild NPDR", "quality_status": "pass",
                  "gradeable": true, "referable": false, "confidence": 0.77,
                  "report_available": true, "clinician_review_status": "pending",
                  "clinician_grade": null } ],
  "latest_screening": { … }, "latest_comparison": { … }, "follow_up": { … },
  "follow_up_history": [ … ], "disclaimer": "…" }
```

`icdr_grade` is `null` and `quality_status` is `"refused"` for a visit whose photograph
the quality gate rejected. Such a visit **is** on the timeline — it happened — but it is
never one half of a comparison, because it produced no result.

## `GET /v1/passport/status` — the returning-patient probe

What the screening page asks *before* an upload, so "Your previous screening is available"
is true rather than decorative. `{ has_history, history_count, last_screening, follow_up }`.

## `GET /v1/passport/screenings/{screening_id}/comparison`

```json
{ "available": true,
  "previous": { "screening_id": "…", "date": "…", "icdr_grade": 1,
                "severity_label": "Mild NPDR", "referable": false, … },
  "current":  { …, "icdr_grade": 2, "severity_label": "Moderate NPDR", "referable": true },
  "previous_grade": 1, "current_grade": 2, "grade_change": 1,
  "change_direction": "higher",
  "change_label": "One ICDR category higher",
  "statement": "The current screening result is one ICDR category higher than the previous screening.",
  "quality_change":  { "previous": "pass", "current": "pass", "changed": false },
  "referral_change": { "previous": false, "current": true,
                       "newly_referable": true, "no_longer_referable": false },
  "clinician_review_change": { "previous": "pending", "current": "confirmed" },
  "interval_days": 181,
  "disclaimer": "This compares two screening results. It is not a diagnosis, …" }
```

`grade_change` is one subtraction of two grades the model already decided. Every sentence
is phrased about the **screening result** and never about the eye or the disease; the
vocabulary lives in `src/passport/comparison.py` and nowhere else, and the test suite
asserts the forbidden claims appear in none of it for any pair of grades on the scale.

Two states answer `200` with `available: false` and a `reason`, because neither is an
error:

| `reason` | when |
|---|---|
| `no_previous_screening` | this is the patient's first screening |
| `current_screening_ungradeable` | the quality gate refused this photograph |

## `GET /v1/passport/screenings/{screening_id}/comparison.pdf`

The comparison report, served through the session. Generated lazily on first request, by
the same reportlab layer as the screening report (`src/explain/report.py` owns the page
geometry and the palette; there is no second PDF architecture). This is what makes
"downloadable whether or not WhatsApp worked" true.

## `POST /v1/passport/screenings/{screening_id}/comparison/whatsapp`

```json
{ "language": "en|hi|te|pa" }
```

Delivers the comparison report through the **existing** `WhatsAppReportService` and its
provider abstraction, with the same response shape, the same stable error codes, the same
duplicate cooldown and the same rule as the screening report: `success: true` means the
provider ACCEPTED the message, never that the patient received it. No recipient field, for
the same reason. `409 comparison_not_available` when there is nothing to compare.

## `GET /v1/passport/follow-up` · `POST /v1/passport/follow-up/{id}/reminder`

The plan in force, whether it has come due, and the reminder that brings the same account
back. A follow-up record carries its window, target date, status, reminder status,
channel, basis and reason:

```json
{ "follow_up_id": "fu_…", "screening_id": "sc_…",
  "recommended_window": { "min_months": 3, "max_months": 3, "label": "in about 3 months",
                          "priority": "prompt",
                          "headline": "Prompt specialist assessment suggested" },
  "due_at": "…", "basis": "guideline_escalated",
  "basis_label": "Guideline-informed follow-up window, brought forward",
  "reason": "…", "clinician_override": false,
  "status": "scheduled", "reminder_status": "pending", "channel": "whatsapp",
  "priority": "prompt", "referral_indicated": true, "specialist_referral": true }
```

The window comes from a configured table keyed by ICDR grade
(`src/passport/followup.py::GUIDELINE_WINDOWS`), brought forward one step when the
category has risen. There is deliberately no single universal interval, and grades 3-4 are
expressed as prompt specialist referral rather than as a long-term reminder. `reminder_status`
becomes `sent` only when a provider accepted the message.

## `GET /v1/passport/patients` · `GET /v1/passport/patients/{account_id}` · `GET /v1/passport/by-scan/{scan_id}` — granted doctor only

The longitudinal record for a patient this doctor is authorised for. Anonymised by
construction: the shape is a whitelist and there is no name, mobile number or patient
reference anywhere in it — the patient is identified by the internal account id only, the
same class of opaque value as a scan id. `by-scan` is the route the report page uses:
from one scan it answers "what else do we know about this person over time?".

## `POST /v1/passport/patients/{account_id}/follow-up` — granted doctor only

```json
{ "screening_id": "sc_…", "follow_up_months": 2,
  "reason": "…", "priority": "routine|soon|prompt|urgent" }
```

A clinician recommendation, which takes precedence over the guideline window outright. It
sets the follow-up PLAN and nothing else; the response echoes `ai_grade_unchanged` and
`ai_referable_unchanged` so a caller can see for itself that nothing clinical moved.

## `POST /v1/passport/access` — admin only

Assigns a patient's longitudinal record to a verified doctor. Refuses `400
not_a_verified_doctor` for any other account.

## `GET /health` — one added block

```json
{ "passport": { "enabled": true, "store_dir_configured": true, "max_history": 200 } }
```
