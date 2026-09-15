"""FastAPI service. Implements docs/API_CONTRACT.md v1.

Deployment note that is also a design principle: the model is loaded **in-process**, not
called over the network from a Vertex prediction endpoint. Grad-CAM needs the gradient of
an output with respect to an intermediate activation, and a managed endpoint returns only
the output tensor. The explainability requirement therefore rules that architecture out.
It is also cheaper, and it is a good answer to give when a judge asks why there is no
"proper" model-serving tier.

The service starts and answers `/health` with `model_loaded: false` when no weights are
present. That is deliberate: it lets the URL be live from hour 1.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.pipeline import analyze
from src.api.store import get_store
from src.common.config import DISCLAIMER, RESULTS_DIR
from src.common.imaging import decode_image
from src.grading import predict as predict_mod

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dr-api")

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp",
                 "image/tiff", "application/octet-stream"}
API_VERSION = "v1"

app = FastAPI(title="DR Screening API", version=API_VERSION,
              description=DISCLAIMER)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

PREDICTOR = None
STORE = None


@app.on_event("startup")
def _startup():
    global PREDICTOR, STORE
    t = time.perf_counter()
    PREDICTOR = predict_mod.load()
    STORE = get_store()
    log.info("model_loaded=%s reason=%s store=%s (%.1fs)",
             PREDICTOR.available, PREDICTOR.reason, STORE.backend,
             time.perf_counter() - t)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": API_VERSION,
        "model_loaded": bool(PREDICTOR and PREDICTOR.available),
        "model_id": PREDICTOR.model_id if PREDICTOR else "none",
        "model_unavailable_reason": (None if (PREDICTOR and PREDICTOR.available)
                                     else (PREDICTOR.reason if PREDICTOR else "starting")),
        "synthetic_demo_model": bool(PREDICTOR and PREDICTOR.synthetic),
        "store": STORE.backend if STORE else None,
        "disclaimer": DISCLAIMER,
    }


@app.get("/")
def root():
    return {"service": "DR Screening API", "contract": "docs/API_CONTRACT.md",
            "docs": "/docs", "health": "/health", "disclaimer": DISCLAIMER}


@app.post(f"/{API_VERSION}/analyze")
async def analyze_endpoint(file: UploadFile = File(...),
                           patient_ref: str | None = Form(default=None)):
    if file.content_type and file.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, detail={"error": {
            "code": "unsupported_media_type",
            "message": f"{file.content_type} is not a supported image type"}})

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, detail={"error": {
            "code": "file_too_large",
            "message": f"image is {len(data)//1024//1024} MB; limit is 12 MB"}})
    if not data:
        raise HTTPException(400, detail={"error": {
            "code": "empty_file", "message": "no image data received"}})

    try:
        bgr = decode_image(data)
    except ValueError:
        raise HTTPException(400, detail={"error": {
            "code": "undecodable_image",
            "message": "the file could not be read as an image"}})

    try:
        result, status = analyze(bgr, PREDICTOR, patient_ref=patient_ref)
    except Exception as e:                          # noqa: BLE001
        log.exception("analyze failed")
        raise HTTPException(500, detail={"error": {
            "code": "internal", "message": str(e)}})

    try:
        STORE.save_scan(_summarise(result))
    except Exception:                               # noqa: BLE001
        log.exception("store write failed (continuing — the result is still valid)")

    return JSONResponse(status_code=status, content=result)


def _summarise(result: dict) -> dict:
    """What we persist: everything except the base64 blobs, which are large and
    reproducible from the image."""
    g = result.get("grading") or {}
    q = result.get("quality") or {}
    r = result.get("rule_check") or {}
    return {
        "scan_id": result["scan_id"],
        "created_at": result["created_at"],
        "patient_ref": result.get("patient_ref"),
        "model_id": result.get("model_id"),
        "gradeable": q.get("gradeable"),
        "quality_score": q.get("overall_score"),
        "recapture_instruction": q.get("recapture_instruction"),
        "icdr_grade": g.get("icdr_grade"),
        "referable": g.get("referable"),
        "confidence": g.get("confidence"),
        "rule_grade": r.get("rule_grade"),
        "rule_flag": r.get("flag"),
        "lesions": result.get("lesions"),
        "timing_ms": result.get("timing_ms"),
        "reviewed": False,
    }


class Review(BaseModel):
    agrees: bool
    corrected_grade: int | None = Field(default=None, ge=0, le=4)
    notes: str = ""
    seconds_to_decide: float = Field(ge=0)


@app.post(f"/{API_VERSION}/review/{{scan_id}}")
def review(scan_id: str, body: Review):
    ok = STORE.save_review(scan_id, body.model_dump())
    if not ok:
        raise HTTPException(404, detail={"error": {
            "code": "unknown_scan", "message": f"no scan {scan_id}"}})
    return {"ok": True, "scan_id": scan_id,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


@app.get(f"/{API_VERSION}/scans")
def scans(limit: int = 50):
    rows = STORE.list_scans(min(max(limit, 1), 200))
    return {"scans": rows, "count": len(rows)}


@app.get(f"/{API_VERSION}/metrics")
def metrics():
    """Serves the ACTIVE evaluation results so no number is hardcoded in the UI.

    Returns `available: false` when no evaluation has been run. The dashboard renders
    that as "not run yet" rather than inventing a plausible number — this endpoint is
    the technical enforcement of the project's anti-fabrication rule.
    """
    import json
    active = RESULTS_DIR / "active" / "metrics.json"
    if not active.exists():
        return {"available": False, "reason": "not run yet",
                "expected_path": str(active)}
    try:
        return {"available": True, **json.loads(active.read_text())}
    except Exception as e:                          # noqa: BLE001
        return {"available": False, "reason": f"metrics file unreadable: {e}"}


@app.get(f"/{API_VERSION}/operational")
def operational():
    """Live operational stats computed from what the service has actually served.

    These ARE real measurements — they come from the scans in the store — so they are
    allowed in the deck, clearly labelled as demo-session traffic rather than a dataset
    evaluation.
    """
    rows = STORE.list_scans(200)
    if not rows:
        return {"available": False, "reason": "no scans yet"}
    total = [r["timing_ms"]["total"] for r in rows
             if isinstance(r.get("timing_ms"), dict) and "total" in r["timing_ms"]]
    ungradeable = [r for r in rows if r.get("gradeable") is False]
    reviews = [r["review"] for r in rows if r.get("review")]
    secs = sorted(x["seconds_to_decide"] for x in reviews if "seconds_to_decide" in x)
    med = (lambda a: None if not a else
           (sorted(a)[len(a) // 2] if len(a) % 2 else
            (sorted(a)[len(a) // 2 - 1] + sorted(a)[len(a) // 2]) / 2))
    agree = [x["agrees"] for x in reviews if "agrees" in x]
    return {
        "available": True,
        "n_scans": len(rows),
        "median_latency_ms": med(total),
        "ungradeable_rate": round(len(ungradeable) / len(rows), 4),
        "n_reviews": len(reviews),
        "median_seconds_to_decide": med(secs),
        "clinician_agreement_rate": (round(sum(agree) / len(agree), 4) if agree else None),
        "note": "Measured from this deployment's own traffic, not from a dataset.",
    }
