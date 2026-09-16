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

from fastapi import Depends, FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.api.evidence import get_evidence_store
from src.api.pipeline import analyze
from src.api.reports import get_scan_store as _reports_scan_store
from src.api.reports import router as reports_router
from src.api.store import get_store
from src.auth import config as auth_config
from src.auth.models import Account
from src.auth.routes import router as auth_router
from src.auth.security import optional_or_required_account
from src.carefinder import config as care_finder_config
from src.carefinder.routes import router as care_finder_router
from src.common.config import DISCLAIMER, RESULTS_DIR
from src.common.imaging import decode_image
from src.delivery import config as delivery_config
from src.delivery.media import get_media_store
from src.delivery.routes import router as delivery_router
from src.grading import predict as predict_mod
from src.passport import config as passport_config
from src.passport import service as passport_service
from src.passport.routes import router as passport_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dr-api")

MAX_UPLOAD_BYTES = 12 * 1024 * 1024
ALLOWED_TYPES = {"image/jpeg", "image/png", "image/jpg", "image/webp",
                 "image/tiff", "application/octet-stream"}
API_VERSION = "v1"

app = FastAPI(title="DR Screening API", version=API_VERSION,
              description=DISCLAIMER)

@app.middleware("http")
async def _json_errors(request, call_next):
    """Turn an unhandled exception into a JSON error the BROWSER can actually read.

    Registered BEFORE the CORS middleware below, which matters and is not cosmetic.
    `add_middleware` inserts at the front, so the last one added is the outermost: this
    ordering puts CORS *outside* this handler, and the response produced here therefore
    picks up the Access-Control-Allow-Origin header on its way out.

    Without this, an unhandled exception is caught by Starlette's ServerErrorMiddleware,
    which sits OUTSIDE the CORS layer and answers `text/plain` "Internal Server Error"
    with no CORS headers at all. The browser then refuses to expose that response to
    JavaScript and `fetch()` rejects with `TypeError: Failed to fetch` — so a plain
    server-side bug reaches the user as a network error naming nothing. That is the
    mechanism behind the "Failed to fetch" reports on /login.

    The message is deliberately generic and the traceback goes to the server log only:
    this is a public endpoint and an exception string can carry internals.
    """
    try:
        return await call_next(request)
    except Exception:                               # noqa: BLE001
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={"detail": {"error": {
                "code": "internal_error",
                "message": ("The server hit an unexpected error handling this request. "
                            "Check the API logs for the traceback."),
            }}},
        )


_CORS_ORIGINS = [o for o in os.getenv("CORS_ORIGINS", "*").split(",") if o]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # Credentialed CORS is incompatible with a wildcard origin, and the session token is
    # sent as an Authorization header rather than a cookie in the split-origin (Vercel +
    # Cloud Run) deployment. Cookies are only enabled when the origin list is explicit.
    allow_credentials=_CORS_ORIGINS != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- access-control layer -------------------------------------------------------
# Mounted as routers so authentication stays entirely outside the medical pipeline.
app.include_router(auth_router)
app.include_router(reports_router)
# Report DELIVERY (WhatsApp). A communication layer, mounted like the others so it stays
# outside the medical pipeline entirely — see src/delivery/__init__.py.
app.include_router(delivery_router)
# Smart Care Finder (where to go next). An ACCESS layer, mounted like the others so it
# stays outside the medical pipeline entirely — see src/carefinder/__init__.py. It
# cannot see an image, a grade or a report, and nothing it does can change one.
app.include_router(care_finder_router)
# CareBridge Eye Health Passport (what has changed since last time). A LONGITUDINAL
# layer, mounted like the others so it stays outside the medical pipeline entirely —
# see src/passport/__init__.py. It cannot grade an image and nothing it does can change
# a grade, a referral or a report; it subtracts two grades the model already decided.
app.include_router(passport_router)
# The reports router reads scans through this seam so it can be tested without a model.
app.dependency_overrides[_reports_scan_store] = lambda: STORE

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
    log.info("auth env=%s protect_analyze=%s",
             auth_config.AUTH_ENV, auth_config.PROTECT_ANALYZE)
    log.info("sign-in: no verification (any mobile number opens a session)")
    # Says whether a report could be delivered, and why not when it could not. Names
    # missing variables, never their values.
    wa = delivery_config.status()
    # `provider` is in this line because WHATSAPP_PROVIDER defaults to "twilio" while
    # .env.example ships "meta": an .env that simply omits the variable gets Twilio
    # without saying so, and a Twilio TRIAL cannot send a PDF at all (it refuses
    # MediaUrl outright). "configured=True" only means the credentials are present, so
    # naming the active provider here is what tells an operator which failure to expect.
    log.info("whatsapp delivery enabled=%s provider=%s configured=%s%s", wa["enabled"],
             wa["provider"], wa["configured"],
             "" if wa["configured"] else f" reason={wa['reason']}")
    # Same rule for Smart Care Finder: says whether a nearby-care search could run, and
    # names the missing variable when it could not. Never its value.
    cf = care_finder_config.status()
    log.info("care finder enabled=%s configured=%s%s", cf["enabled"], cf["configured"],
             "" if cf["configured"] else f" reason={cf['reason']}")
    # Whether longitudinal history is being kept. No patient id, no grade and no count
    # of anybody's screenings appears in this line.
    pp = passport_config.status()
    log.info("eye health passport enabled=%s max_history=%s", pp["enabled"],
             pp["max_history"])


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
        "auth": {
            # A session is still required for the protected endpoints; what changed is
            # how easy it is to get one.
            "required": auth_config.PROTECT_ANALYZE,
            "env": auth_config.AUTH_ENV,
            # Stated plainly so nobody reads this deployment as verified.
            "verification": "none",
            "note": ("Sign-in accepts any mobile number without verification. "
                     "The number is a claim, not a proof."),
        },
        # Whether the optional WhatsApp delivery channel would work. No credential, no
        # sender number and no URL appears in this block — see delivery/config.status().
        "whatsapp": delivery_config.status(),
        # Whether Smart Care Finder could search. No Google key, no key prefix and no
        # key length appears in this block -- see carefinder/config.status().
        "care_finder": care_finder_config.status(),
        # Whether the Eye Health Passport is keeping longitudinal history. No patient
        # data of any kind appears in this block -- see passport/config.status().
        "passport": passport_config.status(),
        "disclaimer": DISCLAIMER,
    }


@app.get("/")
def root():
    return {"service": "DR Screening API", "contract": "docs/API_CONTRACT.md",
            "docs": "/docs", "health": "/health", "disclaimer": DISCLAIMER}


@app.post(f"/{API_VERSION}/analyze")
async def analyze_endpoint(file: UploadFile = File(...),
                           patient_ref: str | None = Form(default=None),
                           account: Account | None = Depends(optional_or_required_account)):
    """Unchanged medical behaviour; a session is now required to reach it.

    The account is used for nothing except deciding whether the request is allowed. It
    is not passed to `analyze()`, not stored on the scan, and not visible to any part of
    the pipeline — the screening result must not depend on who uploaded the image.
    """
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

    # Full evidence, written separately, so a verified doctor can reopen this scan with
    # its images and Grad-CAM later. Best effort by design: see src/api/evidence.py.
    get_evidence_store().save(result)

    # Keep THIS report — the exact PDF bytes already in `result` — so the patient can
    # have it delivered later without anything being generated a second time. The owner
    # is recorded in the delivery store, never on the scan record: the screening result
    # still does not know or depend on who uploaded the image. Best effort, like the
    # evidence write; a failure here cannot affect the response.
    _retain_report_pdf(result, account)

    # The patient's longitudinal record: this screening added to their Eye Health
    # Passport, the previous result found, the two compared, and the next follow-up
    # window planned. Best effort by design, like the two writes above — a patient
    # losing a timeline entry must never turn a successful screening into an error for
    # the health worker standing in front of them. The response is not altered by it:
    # see the comment in `_record_passport_entry`.
    _record_passport_entry(result, account)

    return JSONResponse(status_code=status, content=result)


def _retain_report_pdf(result: dict, account: Account | None) -> None:
    if account is None:
        return
    pdf_b64 = ((result.get("report") or {}).get("pdf_b64") or "")
    if not pdf_b64:
        return
    try:
        import base64
        get_media_store().save(result, base64.b64decode(pdf_b64),
                               account_id=account.account_id)
    except Exception:                               # noqa: BLE001
        log.exception("report retention failed (the screening result is unaffected)")


def _record_passport_entry(result: dict, account: Account | None) -> None:
    """Add this screening to the caller's longitudinal record.

    Note what this does NOT do: it does not put anything into `result`. The
    `/v1/analyze` response contract is unchanged and the comparison is fetched by its
    own endpoint — a screening result must not start depending on how many times the
    person has been screened before, and the frontend contract test in
    `tests/test_carebridge_i18n.py` pins that the response shape did not move.

    Ownership is recorded in the passport store, never on the scan record, exactly as
    report retention records it in the delivery store.
    """
    if account is None:
        return
    try:
        passport_service.record_screening(result, account.account_id)
    except Exception:                               # noqa: BLE001
        log.exception("passport write failed (the screening result is unaffected)")


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
def review(scan_id: str, body: Review,
           account: Account | None = Depends(optional_or_required_account)):
    ok = STORE.save_review(scan_id, body.model_dump())
    if not ok:
        raise HTTPException(404, detail={"error": {
            "code": "unknown_scan", "message": f"no scan {scan_id}"}})
    return {"ok": True, "scan_id": scan_id,
            "recorded_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")}


@app.get(f"/{API_VERSION}/scans")
def scans(limit: int = 50,
          account: Account | None = Depends(optional_or_required_account)):
    """The in-session review queue. Requires a session, and `patient_ref` is stripped.

    That field is free text with no PII enforced by us, so it may hold a name. The
    review UI never displayed it; removing it from the payload means a screening
    identifier cannot leak to a screen that does not need it. The doctor-facing
    collection is /v1/reports, which is verified-doctor only.
    """
    rows = STORE.list_scans(min(max(limit, 1), 200))
    safe = [{k: v for k, v in r.items() if k != "patient_ref"} for r in rows]
    return {"scans": safe, "count": len(safe)}


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
