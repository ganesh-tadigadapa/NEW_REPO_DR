"""Session tokens and the FastAPI dependencies that enforce authorisation.

Tokens are HMAC-SHA256 signed, JWT-shaped, and built from the standard library only —
no extra dependency lands in the serving image for this.

**The token carries an account id and nothing else that matters.** It does not carry the
role. Every request re-reads the role and `doctor_verified` from the account store, so:

  * a client cannot grant itself a role by editing a token (it is signed), and
  * a client cannot grant itself a role by editing a request body (the body is never
    consulted), and
  * revoking a doctor's verification takes effect on the very next request rather than
    whenever their token happens to expire.

The role a caller claims is never read from anywhere except the server's own store.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request

from src.auth import config as cfg
from src.auth.models import Account, AccountStatus, Role
from src.auth.storage import LocalAuthStore, get_auth_store

log = logging.getLogger("dr-auth.security")


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(payload_b64: str) -> str:
    return _b64e(hmac.new(cfg.AUTH_SECRET.encode(), payload_b64.encode(),
                          hashlib.sha256).digest())


@dataclass
class SessionToken:
    token: str
    jti: str
    expires_at: float


def mint_token(account_id: str, ttl: int | None = None) -> SessionToken:
    now = datetime.now(timezone.utc).timestamp()
    ttl = ttl or cfg.SESSION_TTL_SECONDS
    jti = uuid.uuid4().hex
    payload = {"sub": account_id, "jti": jti, "iat": int(now), "exp": int(now + ttl)}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return SessionToken(f"{body}.{_sign(body)}", jti, now + ttl)


def read_token(token: str) -> dict | None:
    """Verify the signature and expiry. Returns the payload, or None for any problem —
    callers must not be able to distinguish 'bad signature' from 'expired'."""
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        return None
    if not hmac.compare_digest(_sign(body), sig):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:                                # noqa: BLE001
        return None
    if datetime.now(timezone.utc).timestamp() > float(payload.get("exp", 0)):
        return None
    return payload


# ---------------------------------------------------------------- dependencies
def _store() -> LocalAuthStore:
    return get_auth_store()


def _unauthorised(message: str, code: str = "not_authenticated"):
    return HTTPException(401, detail={"error": {"code": code, "message": message}},
                         headers={"WWW-Authenticate": "Bearer"})


def _forbidden(message: str, code: str, **extra):
    return HTTPException(403, detail={"error": {"code": code, "message": message, **extra}})


def _bearer(request: Request) -> str | None:
    header = request.headers.get("Authorization") or ""
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    # Cookie fallback, for a same-site deployment where the token can be HttpOnly.
    return request.cookies.get("dr_session")


def optional_account(request: Request) -> Account | None:
    """Resolve the caller if they present a valid session; never raises."""
    token = _bearer(request)
    if not token:
        return None
    payload = read_token(token)
    if not payload:
        return None
    store = _store()
    if store.is_revoked(payload.get("jti", "")):
        return None
    acc = store.get(payload.get("sub", ""))
    if acc is None or acc.status != AccountStatus.ACTIVE.value:
        return None
    request.state.jti = payload.get("jti")
    request.state.token_exp = payload.get("exp")
    return acc


def current_account(request: Request) -> Account:
    """Any authenticated, active account."""
    acc = optional_account(request)
    if acc is None:
        raise _unauthorised("sign in with your mobile number to continue")
    return acc


def require_roles(*roles: str):
    """Dependency factory. The role is read from the store, never from the request."""
    allowed = {r.value if isinstance(r, Role) else str(r) for r in roles}

    def _dep(account: Account = Depends(current_account)) -> Account:
        if account.role not in allowed:
            raise _forbidden("your account does not have access to this area",
                             "role_required", required=sorted(allowed),
                             role=account.role)
        return account

    return _dep


def require_report_access(account: Account = Depends(current_account)) -> Account:
    """Gate for everything under /v1/reports.

    Three distinct outcomes, because the UI has to say three different things:
      * not a doctor          -> "Doctor access required."
      * doctor, not verified  -> "Doctor verification pending."
      * verified doctor/admin -> allowed
    """
    if account.can_read_reports:
        return account
    if account.role == Role.DOCTOR.value and not account.doctor_verified:
        raise _forbidden("Doctor verification pending.", "doctor_verification_pending",
                         role=account.role, doctor_verified=False)
    raise _forbidden("Doctor access required.", "doctor_access_required",
                     role=account.role)


def require_admin(account: Account = Depends(current_account)) -> Account:
    if not account.is_admin:
        raise _forbidden("administrator access required", "admin_required",
                         role=account.role)
    return account


def optional_or_required_account(request: Request) -> Account | None:
    """Used by the existing medical endpoints.

    Authentication is enforced when AUTH_PROTECT_ANALYZE is on (the default). The switch
    exists so an offline pipeline benchmark can run without standing up an account
    store; it is documented as such and is not reachable from any request.
    """
    if not cfg.PROTECT_ANALYZE:
        return optional_account(request)
    return current_account(request)
