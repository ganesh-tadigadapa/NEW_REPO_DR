"""The one HTTP surface Smart Care Finder needs.

    GET /v1/care-finder/nearby      authenticated patient -> eye care near a point
    GET /v1/care-finder/status      is the feature configured at all

`/nearby` takes EITHER a device position (`latitude` + `longitude`) OR a locality the
patient typed (`area`). The second one exists because a rural health centre with no GPS
fix is a normal Tuesday, not an edge case, and a feature that only works with a
satellite lock is a feature that does not work where it is needed most.

Three guards, and the reason for each:

  * **A session is required.** Not to know who the patient is — the account is used for
    nothing but the rate-limit bucket and is never sent to Google — but because an
    unauthenticated proxy in front of a billed API is somebody else's free Places quota.
  * **Radius and result count are clamped**, in config, before Google sees them.
  * **Identical searches inside a short window are cached in process.** The "try 10 km /
    try 25 km" buttons, a double tap and a page refresh are then free.

What Google is sent: a latitude, a longitude, a radius, a fixed eye-care phrase and a
language code. What Google is NOT sent, and has no code path to receive: a name, a
mobile number, a scan id, a grade, a report, or anything at all from the screening. This
router does not import the pipeline, the evidence store or the delivery layer.
"""
from __future__ import annotations

import logging
import threading
import time

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from src.auth.models import Account
from src.auth.security import current_account
from src.carefinder import config as cfg
from src.carefinder import ranking
from src.carefinder.places import get_places_service

log = logging.getLogger("dr-carefinder.routes")

router = APIRouter(prefix="/v1/care-finder", tags=["care-finder"])

# Google's terms require attribution wherever Places data is displayed outside a Google
# map. The frontend renders this string; it is not decoration.
ATTRIBUTION = "Powered by Google"

DISCLAIMER = ("Facility information comes from Google Places. This is a list of nearby "
              "eye-care services, not a recommendation or an endorsement of any of them.")

# Safe code -> HTTP status. The patient sees a translated sentence chosen from the code;
# the status is for clients and logs.
_STATUS = {
    "not_configured": 503,
    "provider_denied": 503,
    "api_disabled": 503,
    "invalid_key": 503,
    "billing_problem": 503,
    "quota_exceeded": 429,
    "rate_limited": 429,
    "provider_unreachable": 502,
    "provider_error": 502,
    "invalid_request": 400,
    "area_not_found": 404,
    "no_location": 400,
}


# --------------------------------------------------------------- spend control
class _Cache:
    """Tiny TTL cache. In process, bounded, and holding no patient identity.

    A key is a coordinate rounded to three decimals (~110 m), a radius and a language.
    That is coarse enough that the cache cannot be read as a record of where anybody
    was, and fine enough that the same search from the same spot hits it.
    """

    def __init__(self, max_entries: int = 256):
        self._data: dict[tuple, tuple[float, list[dict]]] = {}
        self._lock = threading.Lock()
        self._max = max_entries

    def get(self, key: tuple) -> list[dict] | None:
        if cfg.CACHE_TTL_SECONDS <= 0:
            return None
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            stored_at, value = hit
            if time.time() - stored_at > cfg.CACHE_TTL_SECONDS:
                self._data.pop(key, None)
                return None
            return value

    def put(self, key: tuple, value: list[dict]) -> None:
        if cfg.CACHE_TTL_SECONDS <= 0:
            return
        with self._lock:
            if len(self._data) >= self._max:
                oldest = min(self._data, key=lambda k: self._data[k][0])
                self._data.pop(oldest, None)
            self._data[key] = (time.time(), value)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


class _RateLimiter:
    """Fixed searches per account per rolling window. Resets when the process does,
    which is acceptable: this protects a billing account from a loop, not a border."""

    def __init__(self):
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, account_id: str) -> bool:
        if cfg.RATE_LIMIT_SEARCHES <= 0:
            return True
        now = time.time()
        window = cfg.RATE_LIMIT_WINDOW_SECONDS
        with self._lock:
            hits = [t for t in self._hits.get(account_id, []) if now - t < window]
            if len(hits) >= cfg.RATE_LIMIT_SEARCHES:
                self._hits[account_id] = hits
                return False
            hits.append(now)
            self._hits[account_id] = hits
            return True

    def clear(self) -> None:
        with self._lock:
            self._hits.clear()


CACHE = _Cache()
LIMITER = _RateLimiter()


def reset_state() -> None:
    """Used by the tests so one case cannot warm or exhaust the next one's budget."""
    CACHE.clear()
    LIMITER.clear()


def _fail(code: str, message: str, **extra) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS.get(code, 502),
        content={"ok": False, "code": code, "message": message, **extra},
    )


# ---------------------------------------------------------------------- routes
@router.get("/status")
def care_finder_status(account: Account = Depends(current_account)):
    """Whether a search would work, and the limits the UI draws its buttons from.

    No key, no key prefix, no key length — see config.status().
    """
    return {"ok": True, **cfg.status(), "attribution": ATTRIBUTION}


@router.get("/nearby")
def nearby(
    account: Account = Depends(current_account),
    latitude: float | None = Query(default=None, ge=-90, le=90,
                                   description="Device latitude, WGS84 degrees."),
    longitude: float | None = Query(default=None, ge=-180, le=180,
                                    description="Device longitude, WGS84 degrees."),
    area: str | None = Query(default=None, min_length=2, max_length=120,
                             description="A locality to search around instead of a "
                                         "device position."),
    radius_m: int | None = Query(default=None, ge=1, le=50_000,
                                 description="Clamped server-side to the configured "
                                             "minimum and maximum."),
    language: str = Query(default="en", max_length=8,
                          description="CareBridge language, passed to Google so place "
                                      "names come back in the reader's script."),
):
    """Eye-care facilities near a point, normalised and ranked by access factors.

    A 200 with an empty `results` list is a real answer, not an error: it means nothing
    eye-related was listed within the radius asked for, and the UI offers a wider one.
    """
    ok, reason = cfg.configured()
    if not ok:
        return _fail("not_configured", "Nearby eye-care search is not configured.",
                     configuration=True)

    has_point = latitude is not None and longitude is not None
    if not has_point and not (area or "").strip():
        return _fail("no_location",
                     "Provide latitude and longitude, or an area to search around.")

    if not LIMITER.allow(account.account_id):
        return _fail("rate_limited", "Too many searches. Try again in a little while.")

    service = get_places_service()
    lang = (language or "en").strip() or "en"
    # `radius_m` omitted is not the same as `radius_m` given. Omitted means "you choose",
    # which for a named place means "size it to that place"; given means the patient
    # pressed a radius button and their choice wins.
    radius = cfg.clamp_radius(radius_m) if radius_m is not None else cfg.DEFAULT_RADIUS_M

    # --- resolve the centre -------------------------------------------------
    area_label: str | None = None
    area_name: str | None = None
    if has_point:
        centre_lat, centre_lng = float(latitude), float(longitude)
        source = "device"
    else:
        resolved = service.resolve_area(area.strip(), lang)          # type: ignore[union-attr]
        if not resolved.ok:
            return _fail(resolved.code or "provider_error", resolved.message,
                         configuration=resolved.configuration)
        if not resolved.places:
            return _fail("area_not_found",
                         "That place could not be found. Try a nearby town or district.")
        top = resolved.places[0]
        centre_lat, centre_lng = top["latitude"], top["longitude"]
        area_label = top.get("address") or top.get("name")
        # The RESOLVED name, never the string the patient typed. It goes into the query
        # sent to Google and into the distance label, and unvalidated input belongs in
        # neither.
        area_name = top.get("name")
        source = "area"
        if radius_m is None:
            radius = cfg.radius_for_extent(top.get("viewport"))

    # --- the search ---------------------------------------------------------
    key = (round(centre_lat, 3), round(centre_lng, 3), radius, lang, area_name or "")
    results = CACHE.get(key)
    cached = results is not None
    if not cached:
        outcome = service.search_eye_care(centre_lat, centre_lng, radius, lang,
                                          area_hint=area_name)
        if not outcome.ok:
            return _fail(outcome.code or "provider_error", outcome.message,
                         configuration=outcome.configuration)
        results = ranking.rank(outcome.places, centre_lat, centre_lng, radius,
                               cfg.MAX_RESULTS)
        CACHE.put(key, results)

    # Coordinates are logged rounded to one decimal — about 11 km, enough to tell a
    # Vijayawada search from a Chennai one while recording nobody's position.
    log.info("care finder: source=%s radius=%sm results=%s cached=%s near=%.1f,%.1f",
             source, radius, len(results), cached, centre_lat, centre_lng)

    return {
        "ok": True,
        "center": {"latitude": centre_lat, "longitude": centre_lng},
        "center_source": source,
        "area_label": area_label,
        # The short name, for the distance label. "1.2 km away" means something
        # different when the origin is a city the patient typed than when it is the
        # phone in their hand, and the UI has to be able to say which.
        "area_name": area_name,
        "radius_m": radius,
        "count": len(results),
        "results": results,
        "cached": cached,
        "attribution": ATTRIBUTION,
        "disclaimer": DISCLAIMER,
    }


__all__ = ["router", "reset_state", "ATTRIBUTION", "DISCLAIMER"]
