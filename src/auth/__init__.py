"""Access-control layer for the DR screening service.

Deliberately self-contained: the medical pipeline (`src/api/pipeline.py`, `src/grading`,
`src/quality`, `src/segment`, `src/explain`) imports nothing from here, and nothing here
imports from them. Authentication decides WHO may call the service; it has no opinion
about what the service computes.

Layout
    config.py    environment-driven settings, with production guards
    models.py    Account, Role, mobile normalisation, request/response shapes
    otp.py       OTP generation, hashing, expiry, single use, rate limiting
    sms.py       send_otp(mobile, otp) — vendor-agnostic delivery
    security.py  session tokens + the FastAPI authorisation dependencies
    service.py   the use-cases (request OTP, verify, logout, approve doctor)
    storage.py   account / challenge / revocation persistence
    routes.py    the /v1/auth HTTP surface
"""
from src.auth.models import Account, Role            # noqa: F401
