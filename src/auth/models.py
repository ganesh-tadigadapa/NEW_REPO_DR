"""Account and request/response shapes for the authentication layer.

Two rules encoded here rather than in prose:

  1. There is no password field anywhere. Authentication is possession of the mobile
     number, proved by OTP.
  2. `doctor_verified` is a property of the stored account, never of the request. A
     signup can ASK for the doctor role; it can never grant itself the privilege.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class Role(str, Enum):
    """The three roles, as they are STORED.

    `PATIENT` is an alias of `USER`, not a fourth role. "Patient" is the word the product
    and the brief use; `"user"` is the string in every account record written so far, and
    renaming it on disk would orphan those records for no security benefit. Reading
    `Role.PATIENT` and comparing against `account.role` therefore both work, and neither
    requires a migration.
    """
    USER = "user"
    PATIENT = "user"            # alias — same value, same stored role
    DOCTOR = "doctor"
    ADMIN = "admin"


class AccountStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"


# E.164-ish. Deliberately permissive about country code, strict about shape: a leading
# "+", 8-15 digits, no separators. The frontend normalises 10-digit Indian numbers to
# +91XXXXXXXXXX before sending.
MOBILE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


def normalise_mobile(raw: str) -> str:
    """Canonical form, so '+91 98765 43210' and '9876543210' are the same account.

    A bare 10-digit number is assumed to be Indian, which is the deployment context.
    Raises ValueError if the result is not a plausible E.164 number.
    """
    if not isinstance(raw, str):
        raise ValueError("mobile must be a string")
    s = re.sub(r"[\s\-()]", "", raw.strip())
    if s.startswith("00"):
        s = "+" + s[2:]
    if not s.startswith("+"):
        digits = re.sub(r"\D", "", s)
        if len(digits) == 10:
            s = "+91" + digits
        elif len(digits) == 12 and digits.startswith("91"):
            s = "+" + digits
        else:
            raise ValueError("mobile must include a country code, e.g. +919876543210")
    if not MOBILE_RE.match(s):
        raise ValueError("not a valid mobile number")
    return s


def mask_mobile(mobile: str) -> str:
    """+919876543210 -> +91 ***** 43210. Used in logs and in UI echoes."""
    if len(mobile) < 6:
        return "*****"
    return f"{mobile[:3]} ***** {mobile[-5:]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class DoctorProfile:
    """Prototype verification information. Collected at signup, checked by a human.

    This is claimed information, not proof. Nothing here grants a privilege — the only
    field that does is `Account.doctor_verified`, which this module cannot set.
    """
    doctor_name: str = ""
    registration_number: str = ""
    hospital: str = ""
    submitted_at: str = field(default_factory=_now)
    verified_at: str | None = None
    verified_by: str | None = None
    rejection_reason: str | None = None


@dataclass
class Account:
    account_id: str
    mobile: str
    role: str = Role.USER.value
    doctor_verified: bool = False
    status: str = AccountStatus.ACTIVE.value
    created_at: str = field(default_factory=_now)
    last_login_at: str | None = None
    doctor_profile: dict | None = None

    # ---- derived -----------------------------------------------------------
    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value

    @property
    def is_patient(self) -> bool:
        """A patient is an account with the ordinary `user` role — the default, and the
        only role a signup can obtain without an administrator."""
        return self.role == Role.USER.value

    @property
    def is_verified_doctor(self) -> bool:
        return self.role == Role.DOCTOR.value and bool(self.doctor_verified)

    @property
    def can_read_reports(self) -> bool:
        """The single place that answers 'may this account see the report collection?'"""
        return self.is_verified_doctor or self.is_admin

    def to_record(self) -> dict:
        return asdict(self)

    @classmethod
    def from_record(cls, rec: dict) -> "Account":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in rec.items() if k in known})

    def to_public(self) -> dict:
        """What /v1/auth/me returns. The mobile is the caller's own, so it is included;
        nothing else about the account is exposed, and no other account is ever
        reachable through this shape."""
        return {
            "account_id": self.account_id,
            "mobile": self.mobile,
            "mobile_masked": mask_mobile(self.mobile),
            "role": self.role,
            "doctor_verified": self.doctor_verified,
            "status": self.status,
            "created_at": self.created_at,
            "can_read_reports": self.can_read_reports,
            "doctor_profile": (
                {
                    "doctor_name": (self.doctor_profile or {}).get("doctor_name", ""),
                    "registration_number": (self.doctor_profile or {}).get("registration_number", ""),
                    "hospital": (self.doctor_profile or {}).get("hospital", ""),
                    "submitted_at": (self.doctor_profile or {}).get("submitted_at"),
                    "verified_at": (self.doctor_profile or {}).get("verified_at"),
                }
                if self.doctor_profile else None
            ),
        }


# ----------------------------------------------------------------- API payloads
class DoctorProfileIn(BaseModel):
    doctor_name: str = Field(min_length=2, max_length=120)
    registration_number: str = Field(min_length=3, max_length=60)
    hospital: str = Field(min_length=2, max_length=160)


class SignInIn(BaseModel):
    """Everything sign-in accepts. There is no code, and no password field.

    THE ONE THING THIS BODY CANNOT DO is grant a privilege. `role` is a REQUEST carried
    from the signup form: `LocalAuthStore.create` coerces anything but user/doctor down
    to user, refuses admin outright, and creates every doctor with
    `doctor_verified = False`. Promotion happens only through
    `service.approve_doctor()`, which a browser cannot reach.
    """
    mobile: str
    # "login" expects an existing account, "signup" creates one. Both succeed either
    # way — the distinction only decides whether the doctor details are read — but the
    # field is kept so the UI can say something accurate on each screen.
    intent: str = Field(default="login", pattern="^(login|signup)$")
    role: str = Field(default=Role.USER.value, pattern="^(user|doctor)$")
    doctor_profile: DoctorProfileIn | None = None

    @field_validator("mobile")
    @classmethod
    def _mobile(cls, v: str) -> str:
        return normalise_mobile(v)
