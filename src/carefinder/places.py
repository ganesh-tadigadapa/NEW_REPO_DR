"""PlacesService — one call to Google Places API (New), and the translation of its
failures into something a patient can be shown.

Scope, deliberately narrow: this module takes a point, a radius and a language, makes
ONE HTTP request to `places:searchText`, and returns normalised facilities. It does not
know what a scan is, cannot see a grade, and has no access to the account store.

Why raw HTTP with `httpx` rather than the Google client libraries: the project already
talks to Twilio the same way, for the same reason — two endpoints do not justify a
dependency tree in the serving image. `httpx` is already a requirement.

Two rules enforced here, because breaking either is how a feature like this goes bad:

  1. **Nothing is invented.** A field Google did not return is absent from the result,
     not defaulted, not estimated and not filled in from another facility. The only
     number this module computes is the straight-line distance, which is labelled as
     approximate everywhere it is shown.
  2. **No provider text reaches the patient.** Google's error strings are logged, never
     returned. The route answers with a stable code, which the frontend maps to a
     sentence in the reader's own language.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from src.carefinder import config as cfg

log = logging.getLogger("dr-carefinder.places")

SEARCH_TEXT_PATH = "/places:searchText"

# Google's `error.status` -> (our code, English fallback). Everything unlisted becomes a
# generic provider error: an unknown Google failure must not leak through as text.
_STATUS_CODES: dict[str, tuple[str, str]] = {
    "INVALID_ARGUMENT": ("invalid_request", "That search could not be performed."),
    "PERMISSION_DENIED": ("provider_denied",
                          "Nearby eye-care search is not available right now."),
    "UNAUTHENTICATED": ("provider_denied",
                        "Nearby eye-care search is not available right now."),
    "RESOURCE_EXHAUSTED": ("quota_exceeded",
                           "The nearby-care search is busy. Try again shortly."),
    "UNAVAILABLE": ("provider_unreachable",
                    "Could not reach the nearby-care service. Try again."),
    "DEADLINE_EXCEEDED": ("provider_unreachable",
                          "Could not reach the nearby-care service. Try again."),
}

# Substrings in Google's message that identify a CONFIGURATION problem rather than a
# transient one. The UI offers "try again" for the transient kind only, because retrying
# a disabled API or an unbilled project just spends the patient's time.
_CONFIG_HINTS = (
    ("has not been used in project", "api_disabled"),
    ("is not enabled", "api_disabled"),
    ("serviceusage", "api_disabled"),
    ("api key not valid", "invalid_key"),
    ("api_key_invalid", "invalid_key"),
    ("api keys with referer restrictions", "invalid_key"),
    ("billing", "billing_problem"),
)

_GENERIC = ("provider_error", "Nearby eye-care search did not work. Try again.")


@dataclass
class SearchOutcome:
    """What the route is allowed to know.

    Never a raw exception, a stack trace, an API key or a Google URL.
    """
    ok: bool
    places: list[dict] = field(default_factory=list)
    code: str = ""
    # English fallback, safe to display. Never contains provider detail.
    message: str = ""
    # True when retrying cannot help until an operator changes something.
    configuration: bool = False


def _text(node: Any) -> str | None:
    """Google wraps some strings as {"text": "...", "languageCode": "en"}."""
    if isinstance(node, dict):
        value = node.get("text")
        return value.strip() if isinstance(value, str) and value.strip() else None
    if isinstance(node, str) and node.strip():
        return node.strip()
    return None


def normalise(place: dict) -> dict | None:
    """One Google place -> the flat record the API contract promises.

    A key is present only when Google actually returned a value for it. There is no
    `or "Unknown"`, no `or 0` and no placeholder anywhere in this function, and there
    must not be: a fabricated phone number on a health facility is worse than a missing
    one. `None` is returned for a record with no usable identity or position.
    """
    place_id = place.get("id")
    name = _text(place.get("displayName"))
    loc = place.get("location") or {}
    lat, lng = loc.get("latitude"), loc.get("longitude")
    if not place_id or not name or lat is None or lng is None:
        return None

    out: dict[str, Any] = {
        "place_id": str(place_id),
        "name": name,
        "latitude": float(lat),
        "longitude": float(lng),
    }

    address = _text(place.get("formattedAddress"))
    if address:
        out["address"] = address

    rating = place.get("rating")
    if isinstance(rating, (int, float)):
        out["rating"] = round(float(rating), 1)
    count = place.get("userRatingCount")
    if isinstance(count, int) and count > 0:
        out["review_count"] = count

    # Only `currentOpeningHours.openNow` is used. `regularOpeningHours` describes a
    # normal week and would be wrong on a public holiday, and "probably open" is not a
    # thing to tell someone deciding whether to travel.
    open_now = (place.get("currentOpeningHours") or {}).get("openNow")
    if isinstance(open_now, bool):
        out["open_now"] = open_now

    phone = place.get("nationalPhoneNumber") or place.get("internationalPhoneNumber")
    if isinstance(phone, str) and phone.strip():
        out["phone"] = phone.strip()

    website = place.get("websiteUri")
    if isinstance(website, str) and website.strip():
        out["website"] = website.strip()

    # Google's own canonical link for this place. Preferred over anything hand-built:
    # it resolves correctly on desktop, Android and iOS and it cannot go stale.
    maps_url = place.get("googleMapsUri")
    if isinstance(maps_url, str) and maps_url.strip():
        out["maps_url"] = maps_url.strip()

    types = place.get("types")
    if isinstance(types, list):
        clean = [t for t in types if isinstance(t, str)]
        if clean:
            out["types"] = clean
    primary = place.get("primaryType")
    if isinstance(primary, str) and primary.strip():
        out["primary_type"] = primary.strip()

    status = place.get("businessStatus")
    if isinstance(status, str) and status.strip():
        out["business_status"] = status.strip()

    # Google's own bounding box for the place. Only ever present on the locality
    # resolution, which is the only call that asks for it.
    viewport = place.get("viewport")
    if isinstance(viewport, dict):
        low, high = viewport.get("low"), viewport.get("high")
        if (isinstance(low, dict) and isinstance(high, dict)
                and all(isinstance(v, (int, float)) for v in
                        (low.get("latitude"), low.get("longitude"),
                         high.get("latitude"), high.get("longitude")))):
            out["viewport"] = {
                "low": {"latitude": float(low["latitude"]),
                        "longitude": float(low["longitude"])},
                "high": {"latitude": float(high["latitude"]),
                         "longitude": float(high["longitude"])},
            }

    return out


class PlacesService:
    """The HTTP boundary. Subclassed or replaced wholesale in tests."""

    def __init__(self, transport=None):
        # `transport(url, headers, json) -> (status_code, body_dict)`. Injected by the
        # tests so not one line of this file needs a network to be exercised.
        self._transport = transport

    # ---------------------------------------------------------------- public
    def search_eye_care(self, latitude: float, longitude: float, radius_m: int,
                        language: str = "en", area_hint: str | None = None) -> SearchOutcome:
        """Eye-care facilities near a point, ranked by distance by Google.

        `locationBias` rather than `locationRestriction`: Places (New) accepts a circle
        for a bias and only a rectangle for a restriction, and a rectangle around a
        radius quietly widens the search at the corners. The circle is honoured exactly
        by filtering on the distance we compute ourselves — see ranking.rank().

        `area_hint` is the resolved place NAME, and only ever that — never the string the
        patient typed, which is unvalidated input. Naming the place in the query is what
        Text Search is built for ("eye hospital in Hyderabad"), and it anchors relevance
        in a way a bias circle alone does not.
        """
        text_query = cfg.CARE_FINDER_QUERY
        if area_hint:
            text_query = f"{text_query} in {area_hint}"
        payload = {
            "textQuery": text_query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": float(latitude), "longitude": float(longitude)},
                    "radius": float(radius_m),
                },
            },
            "rankPreference": "DISTANCE",
            "pageSize": cfg.MAX_RESULTS,
            "languageCode": language or "en",
            "regionCode": cfg.CARE_FINDER_REGION_CODE,
        }
        return self._search(payload, cfg.field_mask())

    def resolve_area(self, query: str, language: str = "en") -> SearchOutcome:
        """Turn a typed locality into a point AND an extent.

        Deliberately the same Places API rather than the Geocoding API: one API to
        enable, one key restriction to get right, one bill to read.

        The extent matters. "Hyderabad" resolves to a centroid, and a 5 km search around
        the centroid of a city 40 km across answers a question nobody asked — at best it
        finds the clinics nearest one arbitrary point, at worst the centroid lands on a
        lake and the honest answer is "nothing found". `viewport` is Google's own
        bounding box for the place, so a city gets a city-sized first search and a
        village gets a village-sized one. See routes.nearby().

        Still the cheap field mask: a name, a coordinate and a box. No rating, no hours,
        no phone — none of which a search centre has any use for.
        """
        payload = {
            "textQuery": query.strip(),
            "pageSize": 1,
            "languageCode": language or "en",
            "regionCode": cfg.CARE_FINDER_REGION_CODE,
        }
        return self._search(payload, cfg.AREA_FIELDS)

    # --------------------------------------------------------------- internal
    def _search(self, payload: dict, field_mask: str) -> SearchOutcome:
        ok, reason = cfg.configured()
        if not ok:
            log.warning("care finder unavailable: %s", reason)
            return SearchOutcome(ok=False, code="not_configured",
                                 message="Nearby eye-care search is not configured.",
                                 configuration=True)
        url = f"{cfg.PLACES_API_BASE}{SEARCH_TEXT_PATH}"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": cfg.GOOGLE_MAPS_API_KEY,
            "X-Goog-FieldMask": field_mask,
        }
        try:
            status, body = self._post(url, headers, payload)
        except Exception as e:                                   # noqa: BLE001
            # Type only. The exception text can carry the URL, and the URL is not
            # interesting enough to risk printing a query string next to a key header.
            log.warning("places request failed: %s", type(e).__name__)
            return SearchOutcome(ok=False, code="provider_unreachable",
                                 message="Could not reach the nearby-care service.")

        if status == 200:
            raw = body.get("places") if isinstance(body, dict) else None
            places = [] if not isinstance(raw, list) else [
                p for p in (normalise(x) for x in raw if isinstance(x, dict)) if p]
            return SearchOutcome(ok=True, places=places)

        return self._failure(status, body)

    def _post(self, url: str, headers: dict, payload: dict) -> tuple[int, dict]:
        if self._transport is not None:
            return self._transport(url, headers, payload)
        import httpx
        with httpx.Client(timeout=cfg.CARE_FINDER_TIMEOUT_SECONDS) as client:
            r = client.post(url, headers=headers, json=payload)
        try:
            return r.status_code, r.json()
        except Exception:                                        # noqa: BLE001
            return r.status_code, {}

    def _failure(self, status: int, body: Any) -> SearchOutcome:
        err = (body or {}).get("error") if isinstance(body, dict) else None
        gstatus = str((err or {}).get("status") or "")
        gmessage = str((err or {}).get("message") or "")

        code, message = _STATUS_CODES.get(gstatus, _GENERIC)
        configuration = False

        # A configuration problem is more specific than the gRPC status that carries it:
        # a disabled API, an invalid key and an unbilled project all arrive as
        # PERMISSION_DENIED, and they need three different fixes.
        lowered = gmessage.lower()
        for hint, specific in _CONFIG_HINTS:
            if hint in lowered:
                code, configuration = specific, True
                message = "Nearby eye-care search is not available right now."
                break
        else:
            if code in ("provider_denied", "invalid_request", "not_configured"):
                configuration = True

        if status >= 500:
            code, message = "provider_error", _GENERIC[1]
            configuration = False

        # The Google text IS logged: it is the one thing that makes a broken key or a
        # disabled API diagnosable, it contains no patient data, and it never leaves the
        # server. The response carries only `code`.
        log.warning("places search failed: http=%s status=%s code=%s detail=%s",
                    status, gstatus or "-", code, gmessage[:200] or "-")
        return SearchOutcome(ok=False, code=code, message=message,
                             configuration=configuration)


# ------------------------------------------------------------------- singleton
_SERVICE: PlacesService | None = None


def get_places_service() -> PlacesService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PlacesService()
    return _SERVICE


def set_places_service(service: PlacesService | None) -> None:
    """Test seam. Injecting a double is the only way this package is ever exercised in
    CI — no test in this repository may reach Google."""
    global _SERVICE
    _SERVICE = service


__all__ = ["PlacesService", "SearchOutcome", "normalise",
           "get_places_service", "set_places_service"]
