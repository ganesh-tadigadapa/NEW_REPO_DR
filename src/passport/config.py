"""Configuration for the Eye Health Passport.

Read from the environment, never from a request. Nothing here is a secret — the passport
layer signs nothing of its own, and reuses the delivery layer's media signing for the
comparison PDF.
"""
from __future__ import annotations

import os
from pathlib import Path

# Imported for its side effect as much as its values: src.auth.config loads `.env`.
from src.auth import config as auth_cfg  # noqa: F401
from src.common.config import REPO_ROOT


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


# The longitudinal record. Separate directory from the medical scan store and from the
# account store, for the same reason those two are separate from each other.
PASSPORT_STORE_DIR = Path(
    os.getenv("PASSPORT_STORE_DIR", str(REPO_ROOT / "data" / "interim" / "passport")))

# Switch the whole feature off without touching a route. When false, `/v1/analyze` stops
# recording history and the passport endpoints answer honestly that there is none.
PASSPORT_ENABLED = _flag("PASSPORT_ENABLED", "1")

# How many screenings one patient's timeline may hold. A bound, not a policy: the
# timeline UI and the comparison only ever need the most recent entries.
MAX_HISTORY = int(os.getenv("PASSPORT_MAX_HISTORY", "200"))

# Duplicate protection for the comparison send, mirroring the report send. Same meaning,
# separate variable, because a patient may legitimately want the comparison seconds after
# the report itself.
COMPARISON_RESEND_COOLDOWN_SECONDS = int(
    os.getenv("PASSPORT_RESEND_COOLDOWN_SECONDS", "60"))


# ------------------------------------------------------- patient -> doctor sharing
# How long a share code a patient generates stays redeemable. Short on purpose: the code
# is spoken or shown across a desk in a clinic, and a capability that outlives that
# conversation is a capability somebody else can use.
SHARE_CODE_TTL_SECONDS = int(os.getenv("PASSPORT_SHARE_CODE_TTL_SECONDS", "1800"))

# How many codes one patient may have outstanding at once. Bounds both the file and the
# guessing surface.
SHARE_CODE_MAX_ACTIVE = int(os.getenv("PASSPORT_SHARE_CODE_MAX_ACTIVE", "5"))


def status() -> dict:
    """Safe, non-secret summary for /health. Says whether history is being kept."""
    return {
        "enabled": PASSPORT_ENABLED,
        "store_dir_configured": bool(PASSPORT_STORE_DIR),
        "max_history": MAX_HISTORY,
        "share_code_ttl_seconds": SHARE_CODE_TTL_SECONDS,
    }
