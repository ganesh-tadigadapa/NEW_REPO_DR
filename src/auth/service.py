"""Sign-in use-cases: open a session, log out, approve a doctor.

This layer owns the decisions; `routes.py` owns only HTTP. Keeping them apart is what
lets the tests exercise the rules without a web server, and what keeps the medical
pipeline free of any account code.

WHAT THIS MODULE NO LONGER DOES, AND THE HONEST CONSEQUENCE
-----------------------------------------------------------
There is no OTP, no password and no verification provider. `sign_in()` takes a mobile
number and opens a session for it immediately.

So the number is a CLAIM, not a proof. Anyone who types a number gets that number's
account and everything attached to it — screening history, reports, follow-ups. The
AUTHORISATION layer is untouched and still works exactly as before (a patient still
cannot read another account's records, a doctor still needs a grant), but it is now
enforcing boundaries between *claimed* identities rather than *verified* ones.

That is a deliberate product decision for a demo build, and it is written here rather
than left for someone to discover. Restoring real verification means putting one check
back in front of `sign_in()`; nothing else in this file would change.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from src.auth.models import Account, Role, mask_mobile
from src.auth.security import mint_token
from src.auth.storage import LocalAuthStore, get_auth_store

log = logging.getLogger("dr-auth.service")


@dataclass
class VerifyOutcome:
    ok: bool
    error: str | None = None
    message: str = ""
    account: Account | None = None
    token: str | None = None
    expires_at: float = 0.0
    created: bool = False
    attempts_remaining: int = 0


_HUMAN = {
    "account_suspended": ("This account is not active. "
                          "Contact the programme administrator."),
    "invalid_mobile": "That does not look like a valid mobile number.",
}


def sign_in(mobile: str, *, intent: str = "login", role: str = Role.USER.value,
            doctor_profile: dict | None = None,
            store: LocalAuthStore | None = None) -> VerifyOutcome:
    """Open a session for `mobile`, creating the account if it does not exist yet.

    Succeeds for any well-formed number. The only refusal is a SUSPENDED account, which
    is an administrator's decision and is still honoured — a demo without verification
    is not a reason to let a disabled account back in.

    The role is a request, never a grant: `store.create` coerces anything but
    user/doctor down to user and creates every doctor unverified, so choosing "Doctor"
    on the form buys nothing until an administrator approves it.

    An EXISTING account keeps the role it already has. Signing up again as a doctor
    against an account that is already a user changes nothing, which is what stops the
    browser upgrading itself by replaying signup.
    """
    store = store or get_auth_store()
    account = store.get_by_mobile(mobile)
    created = False

    if account is None:
        requested_role = role if intent == "signup" else Role.USER.value
        profile = (doctor_profile if (intent == "signup"
                                      and requested_role == Role.DOCTOR.value) else None)
        account = store.create(mobile, requested_role, doctor_profile=profile)
        created = True
        log.info("account created %s role=%s doctor_verified=%s",
                 account.account_id, account.role, account.doctor_verified)

    if account.status != "active":
        return VerifyOutcome(False, "account_suspended", _HUMAN["account_suspended"])

    store.touch_login(account.account_id)
    account = store.get(account.account_id) or account
    session = mint_token(account.account_id)
    log.info("sign-in for %s account=%s created=%s", mask_mobile(mobile),
             account.account_id, created)
    return VerifyOutcome(True, account=account, token=session.token,
                         expires_at=session.expires_at, created=created,
                         message="Signed in.")


def logout(jti: str, expires_at: float, *, store: LocalAuthStore | None = None) -> None:
    (store or get_auth_store()).revoke(jti, expires_at)


def approve_doctor(account_id: str, *, approved: bool = True, by: str = "admin",
                   reason: str | None = None,
                   store: LocalAuthStore | None = None) -> Account | None:
    """The doctor-verification decision, in one function.

    Every route into doctor privileges goes through here: the admin API endpoint and the
    local approval script. There is no other writer of `doctor_verified`, which is what
    makes "a person cannot gain doctor privileges by choosing Doctor" true rather than
    merely intended.
    """
    store = store or get_auth_store()
    acc = store.set_doctor_verified(account_id, approved, by=by, reason=reason)
    if acc:
        log.info("doctor %s %s by %s", account_id,
                 "approved" if approved else "revoked", by)
    return acc


def pending_doctors(store: LocalAuthStore | None = None) -> list[Account]:
    store = store or get_auth_store()
    return [a for a in store.list_accounts(Role.DOCTOR.value) if not a.doctor_verified]
