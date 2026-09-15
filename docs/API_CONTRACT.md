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
