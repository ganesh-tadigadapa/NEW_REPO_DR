"""HTTP surface for authentication. Thin: every decision lives in service.py.

    POST /v1/auth/sign-in              open a session for a mobile number
    POST /v1/auth/logout
    GET  /v1/auth/me
    GET  /v1/auth/admin/doctors        (admin)
    POST /v1/auth/admin/doctors/{id}/verify   (admin)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from src.auth import config as cfg
from src.auth import service
from src.auth.models import Account, Role, SignInIn, mask_mobile
from src.auth.security import (current_account, mint_token, optional_account,
                               require_admin)
from src.auth.storage import get_auth_store

log = logging.getLogger("dr-auth.routes")

router = APIRouter(prefix="/v1/auth", tags=["auth"])

# HTTP status for each refusal the service can return. The list is short because
# sign-in has almost nothing left to refuse: there is no code to get wrong, no provider
# to be down and no rate limit to trip.
_STATUS = {
    "account_suspended": 403,
    "invalid_mobile": 400,
}


def _session_payload(out) -> dict:
    """The body sign-in returns. Unchanged from the OTP era on purpose: every client,
    guard and test downstream reads this shape."""
    acc = out.account
    return {
        "ok": True,
        "created": out.created,
        "token": out.token,
        "token_type": "bearer",
        "expires_at": out.expires_at,
        "account": acc.to_public(),
        # Where the frontend should land. Computed by the backend from the stored role,
        # so the client is not the thing deciding what a doctor may see.
        "next": "/reports" if acc.can_read_reports else "/screen",
        "doctor_verification_pending": (acc.role == Role.DOCTOR.value
                                        and not acc.doctor_verified),
    }


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        "dr_session", token, httponly=True, samesite="lax",
        secure=cfg.IS_PRODUCTION, max_age=cfg.SESSION_TTL_SECONDS, path="/",
    )


@router.post("/sign-in")
def sign_in(body: SignInIn, response: Response):
    """Open a session for a mobile number. No code, no password, no provider.

    Returns exactly the shape the old /verify-otp returned, so nothing downstream of
    sign-in changed: the session token, the role system, `Guard`, and every protected
    endpoint are as they were.

    The number is taken as claimed. See the module docstring in `service.py` for what
    that does and does not guarantee.
    """
    out = service.sign_in(
        body.mobile,
        intent=body.intent,
        role=body.role,
        doctor_profile=body.doctor_profile.model_dump() if body.doctor_profile else None,
    )
    if not out.ok:
        raise HTTPException(
            _STATUS.get(out.error, 400),
            detail={"error": {"code": out.error, "message": out.message}},
        )
    # Also set the token as an HttpOnly cookie. That is the safer transport for a
    # same-site deployment; the bearer token in the body is what makes the split
    # Vercel/Cloud Run origin work. See docs/AUTH.md.
    _set_session_cookie(response, out.token)
    return _session_payload(out)


@router.post("/logout")
def logout(request: Request, response: Response,
           account: Account = Depends(current_account)):
    jti = getattr(request.state, "jti", None)
    exp = getattr(request.state, "token_exp", 0)
    if jti:
        service.logout(jti, float(exp or 0))
    response.delete_cookie("dr_session", path="/")
    return {"ok": True, "message": "Signed out."}


@router.get("/me")
def me(account: Account = Depends(current_account)):
    return {
        "authenticated": True,
        "account": account.to_public(),
        "permissions": {
            "can_screen": True,
            "can_review": True,
            "can_read_reports": account.can_read_reports,
            "can_approve_doctors": account.is_admin,
        },
        "doctor_verification_pending": (account.role == Role.DOCTOR.value
                                        and not account.doctor_verified),
    }


@router.get("/session")
def session(account: Account | None = Depends(optional_account)):
    """Unauthenticated-safe variant of /me, so the frontend shell can render without
    treating 'signed out' as an error."""
    if account is None:
        return {"authenticated": False, "account": None}
    return {"authenticated": True, "account": account.to_public(),
            "doctor_verification_pending": (account.role == Role.DOCTOR.value
                                            and not account.doctor_verified)}


# ------------------------------------------------------------------- admin
class VerifyDoctorIn(BaseModel):
    approved: bool = True
    reason: str | None = Field(default=None, max_length=300)


@router.get("/admin/doctors")
def list_doctors(admin: Account = Depends(require_admin)):
    """Doctor accounts and their verification state. Admin only.

    This DOES show the doctor's own claimed credentials — that is the point of the
    queue — but it never touches patient data of any kind.
    """
    store = get_auth_store()
    return {
        "doctors": [
            {
                "account_id": a.account_id,
                "mobile_masked": mask_mobile(a.mobile),
                "doctor_verified": a.doctor_verified,
                "created_at": a.created_at,
                "profile": a.doctor_profile,
            }
            for a in store.list_accounts(Role.DOCTOR.value)
        ]
    }


@router.post("/admin/doctors/{account_id}/verify")
def verify_doctor(account_id: str, body: VerifyDoctorIn,
                  admin: Account = Depends(require_admin)):
    acc = service.approve_doctor(account_id, approved=body.approved,
                                 by=admin.account_id, reason=body.reason)
    if acc is None:
        raise HTTPException(404, detail={"error": {
            "code": "unknown_doctor_account",
            "message": f"no doctor account {account_id}"}})
    return {"ok": True, "account_id": acc.account_id,
            "doctor_verified": acc.doctor_verified}
