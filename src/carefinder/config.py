"""Configuration for Smart Care Finder.

Read from the environment, never from a request, and never returned by an API.

One secret lives here: `GOOGLE_MAPS_API_KEY`. It is a **server-side** key and it stays
server-side — it is not a `NEXT_PUBLIC_*` value, it never appears in a response, it is
never logged, and `status()` reports only whether it is present. The browser cannot make
a Places call in this design, so there is nothing for a browser key to be used for.

The limits below exist because an unbounded proxy in front of a billed API is a bill
waiting to happen. Radius is clamped, result count is clamped, identical searches inside
a short window are served from an in-process cache, and each account gets a fixed number
of searches per window.
"""
from __future__ import annotations

import logging
import os

# Imported for its side effect as much as its values: src.auth.config loads `.env` from
# the repo root, so a developer needs no exported variables for local work.
from src.auth import config as auth_cfg  # noqa: F401  (import for .env loading)

log = logging.getLogger("dr-carefinder")


def _flag(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


# ------------------------------------------------------------------ mode
# Off => the endpoint answers "not configured" and the UI hides the feature rather than
# offering a button that cannot work. There is deliberately no demo mode that returns
# invented facilities: a fabricated hospital is the one failure this feature must not
# have, so the code to produce it does not exist.
CARE_FINDER_ENABLED = _flag("CARE_FINDER_ENABLED", "1")

# ------------------------------------------------------------------ Google
# Places API (New). A server-side key with an API restriction limited to the Places API,
# and no HTTP-referrer restriction (this is not a browser call).
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

PLACES_API_BASE = os.getenv(
    "PLACES_API_BASE", "https://places.googleapis.com/v1").rstrip("/")

CARE_FINDER_TIMEOUT_SECONDS = float(os.getenv("CARE_FINDER_TIMEOUT_SECONDS", "10"))

# Biases Google's ranking and address formatting to the deployment's country.
CARE_FINDER_REGION_CODE = os.getenv("CARE_FINDER_REGION_CODE", "IN").strip().upper()

# ------------------------------------------------------------------ the search
# Why Text Search (New) and not Nearby Search (New): Nearby Search filters by place
# TYPE, and the Places API (New) type table has no "ophthalmologist" and no eye-specific
# type at all — the nearest options are `doctor` and `hospital`, which would return
# general practice and district hospitals and leave the patient to guess which of them
# does eyes. A categorical text query matches the eye-care vocabulary that is actually in
# the names and categories of these facilities in India. Confirmed against
# developers.google.com/maps/documentation/places/web-service/place-types (Table A).
CARE_FINDER_QUERY = os.getenv(
    "CARE_FINDER_QUERY", "eye hospital ophthalmologist eye clinic eye care").strip()

# Radius. The default is a town-scale search; the maximum is the "rural expansion" ceiling
# offered in the UI. Google's own hard limit for a circular bias is 50 km.
DEFAULT_RADIUS_M = _int("CARE_FINDER_DEFAULT_RADIUS_M", 5_000)
MIN_RADIUS_M = _int("CARE_FINDER_MIN_RADIUS_M", 500)
MAX_RADIUS_M = min(_int("CARE_FINDER_MAX_RADIUS_M", 25_000), 50_000)

# Google's own page-size ceiling for both Places (New) search methods is 20.
MAX_RESULTS = min(_int("CARE_FINDER_MAX_RESULTS", 20), 20)

# ------------------------------------------------------------------ spend control
# Identical search, same account, inside this window -> served from memory, no Google
# call. This is what makes the "10 km / 25 km" retry buttons and a double tap cheap.
CACHE_TTL_SECONDS = _int("CARE_FINDER_CACHE_TTL_SECONDS", 300)

# Per account, per rolling window. A patient needs a handful of searches; anything past
# that is a loop or an abuse, and neither should reach a billed API.
RATE_LIMIT_SEARCHES = _int("CARE_FINDER_RATE_LIMIT", 30)
RATE_LIMIT_WINDOW_SECONDS = _int("CARE_FINDER_RATE_WINDOW_SECONDS", 3600)

# ------------------------------------------------------------------ field mask
# Places API (New) has no default field list: every field is named, and the billing SKU
# for the call is decided by the most expensive field in this mask. Nothing is requested
# that the UI does not display — see docs/CARE_FINDER.md for the field-by-field mapping.
#
#   Pro tier         id, displayName, formattedAddress, location, googleMapsUri,
#                    types, primaryType, businessStatus
#   Enterprise tier  nationalPhoneNumber, websiteUri, currentOpeningHours, rating,
#                    userRatingCount
#
# The Enterprise fields are exactly the four the brief requires on a facility card
# (open/closed, rating, phone, website). Dropping them is a supported configuration —
# see PLACE_FIELDS_BASIC — and the UI simply stops showing what it was not given.
PLACE_FIELDS_BASIC = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.googleMapsUri,places.types,places.primaryType,places.businessStatus"
)
PLACE_FIELDS_DETAIL = (
    "places.nationalPhoneNumber,places.websiteUri,"
    "places.currentOpeningHours.openNow,places.rating,places.userRatingCount"
)
# Off => only the Pro-tier fields are requested, which is materially cheaper and loses
# the rating, the phone number, the website and the open/closed badge.
CARE_FINDER_RICH_FIELDS = _flag("CARE_FINDER_RICH_FIELDS", "1")


# The locality resolution's own mask. Cheap by design: a name, a coordinate and Google's
# bounding box for the place. `viewport` is Pro tier, same as the rest of this line, and
# it is what lets "Hyderabad" search a city rather than 5 km around a centroid.
AREA_FIELDS = ("places.id,places.displayName,places.formattedAddress,"
               "places.location,places.viewport")


def field_mask() -> str:
    if CARE_FINDER_RICH_FIELDS:
        return f"{PLACE_FIELDS_BASIC},{PLACE_FIELDS_DETAIL}"
    return PLACE_FIELDS_BASIC


def clamp_radius(metres: float | int | None) -> int:
    """Whatever the client asked for, reduced to something this service will pay for."""
    if metres is None:
        return DEFAULT_RADIUS_M
    try:
        value = int(float(metres))
    except (TypeError, ValueError):
        return DEFAULT_RADIUS_M
    return max(MIN_RADIUS_M, min(value, MAX_RADIUS_M))


def radius_for_extent(viewport: dict | None) -> int:
    """A first-search radius sized to the place the patient actually named.

    Half the diagonal of Google's own bounding box is the radius of a circle that covers
    it, so a metro gets a metro-sized search and a village gets a village-sized one,
    without this code holding any opinion about which places are big. Clamped like every
    other radius: the configured default is the floor (a tiny village should still get a
    useful first search) and the configured maximum is the ceiling (nobody's first search
    is allowed to become a state-wide one).

    Returns the default when Google gave no viewport, which is the honest fallback — the
    UI's radius buttons are still there.
    """
    if not isinstance(viewport, dict):
        return DEFAULT_RADIUS_M
    low, high = viewport.get("low") or {}, viewport.get("high") or {}
    try:
        diagonal = _haversine(float(low["latitude"]), float(low["longitude"]),
                              float(high["latitude"]), float(high["longitude"]))
    except (KeyError, TypeError, ValueError):
        return DEFAULT_RADIUS_M
    return max(DEFAULT_RADIUS_M, min(int(diagonal / 2), MAX_RADIUS_M))


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Local copy so config imports nothing. ranking.haversine_metres is the same maths
    and `tests/test_care_finder.py` pins the two against each other."""
    import math
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(min(1.0, math.sqrt(a)))


def configured() -> tuple[bool, str]:
    """Every precondition for a real search, checked in one place.

    Called at startup for the log line AND before each search, so a misconfiguration is a
    clear sentence in the UI rather than a 403 from Google in front of a patient.
    """
    if not CARE_FINDER_ENABLED:
        return False, "Smart Care Finder is switched off (CARE_FINDER_ENABLED=0)"
    if not GOOGLE_MAPS_API_KEY:
        return False, ("missing GOOGLE_MAPS_API_KEY — Smart Care Finder needs a "
                       "server-side Google key with the Places API (New) enabled")
    return True, "ok"


def status() -> dict:
    """Safe, non-secret summary for /health and the frontend capability probe.

    No key, no key prefix, no key length. Only whether a search would work, and the
    limits the UI needs in order to draw the right radius buttons.
    """
    ok, reason = configured()
    return {
        "enabled": CARE_FINDER_ENABLED,
        "configured": ok,
        # `reason` names the missing VARIABLE, never its value.
        "reason": None if ok else reason,
        "default_radius_m": DEFAULT_RADIUS_M,
        "max_radius_m": MAX_RADIUS_M,
        "max_results": MAX_RESULTS,
        "detail_fields": CARE_FINDER_RICH_FIELDS,
    }
