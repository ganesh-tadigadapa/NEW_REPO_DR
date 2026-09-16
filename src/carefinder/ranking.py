"""Distance, eye-care relevance, and the order the facilities come back in.

**This is not a medical-provider recommender, and the ordering must never be read as
one.** Nothing here scores clinical quality, outcomes, equipment, surgeons or safety,
because none of that is in the data and inventing it would be the most harmful thing
this feature could do. What it ranks is ACCESS: how likely a facility is to do eyes at
all, how far the patient has to travel, whether it is open right now, and how much of
its listing Google actually filled in.

Every factor is computed from a field Google returned, every weight is written down in
`WEIGHTS`, and `explain()` will state the factors for any single facility. The badges
the UI shows — "Nearby", "Eye-care focused", "Open now", "Highly rated" — are each
emitted only when the underlying field is genuinely present, so a facility with no
rating simply has no rating badge rather than a neutral-looking one.

The one number this module invents is the straight-line distance, which is:
  * computed from two coordinates Google returned,
  * a great-circle distance, NOT a travel distance, and
  * labelled "approximate" on every surface that shows it.
"""
from __future__ import annotations

import math
import re

EARTH_RADIUS_M = 6_371_000.0

# Words that mark a facility as eye-focused, in the forms they actually appear in on
# Indian listings. Matched case-insensitively against the display name.
#
# Transliterations are included because "Netralaya" and "Drishti" are how a very large
# number of eye hospitals in India are actually named, and a patient searching in Hindi
# or Telugu should not be shown a worse list than one searching in English.
EYE_NAME_TERMS = (
    "eye", "eyes", "ophthal", "opthal", "optom", "optic", "optical", "retina",
    "retinal", "cornea", "cataract", "vision", "sight", "lasik", "glaucoma",
    "netra", "netralaya", "nethra", "nethralaya", "drishti", "drusti", "dristi",
    "aankh", "akhi", "kann", "kan hospital",
)

# Google's own type vocabulary. `ophthalmologist` and `optometrist` are RESPONSE types
# (they cannot be used to filter a Nearby Search — see config.CARE_FINDER_QUERY), so
# they are read here rather than sent.
EYE_TYPES = frozenset({
    "ophthalmologist", "optometrist", "optician", "eye_care_center",
})
# Types that say "this is a health facility" without saying it does eyes. Worth a little,
# because a general hospital with an eye department is still a real onward referral.
CLINICAL_TYPES = frozenset({
    "hospital", "general_hospital", "medical_center", "medical_clinic", "doctor",
    "health", "clinic",
})

# The access factors, and what each is worth. Changing a number here changes the ORDER
# of a list; it cannot change a grade, a referral, or anything a patient is told about
# their eyes.
WEIGHTS = {
    "relevance": 0.35,      # does this place do eyes at all
    "proximity": 0.35,      # can the patient actually get there
    "open_now": 0.12,       # can they get there today
    "reputation": 0.10,     # what other patients said, damped by how many said it
    "completeness": 0.08,   # can they phone ahead / look it up
}

# Fields whose presence makes a listing usable. Completeness is a property of the
# LISTING, never of the facility.
COMPLETENESS_FIELDS = ("address", "phone", "website", "open_now", "rating")

# Reputation is damped towards a neutral prior so that one 5-star review does not
# outrank a hospital with four hundred. Expressed in review-count units.
RATING_PRIOR = 3.5
RATING_PRIOR_WEIGHT = 5.0

# A facility this close is "Nearby" in the sense a person on foot or on a bus means it.
NEARBY_METRES = 2_000
# The bar for a "Highly rated" badge. Both halves are required: a 5.0 from three people
# is not a signal, and the badge must not imply one.
HIGH_RATING = 4.3
HIGH_RATING_MIN_REVIEWS = 20

# Keys `normalise()` can produce that describe a SEARCH AREA rather than a facility.
# `viewport` is Google's bounding box for a locality: it is how a "Hyderabad" search gets
# sized to Hyderabad, and it has no business on a facility card. The facility field mask
# never asks for it, so this is belt and braces — but the belt is cheap and the braces
# are what stop a future mask change quietly widening the API's response.
NOT_A_FACILITY_FIELD = frozenset({"viewport"})

_WORD = re.compile(r"[a-z]+")


def haversine_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance. Straight line, not a route — see the module docstring."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def eye_relevance(place: dict) -> float:
    """0..1. How much of the evidence says this place does eyes.

    Name and type are independent signals: "Sankara Nethralaya" carries it in the name,
    a listing typed `ophthalmologist` carries it in the category, and a plain district
    hospital carries neither but is still a real place to be referred to.
    """
    name = (place.get("name") or "").lower()
    words = set(_WORD.findall(name))
    types = {str(t).lower() for t in (place.get("types") or [])}
    primary = str(place.get("primary_type") or "").lower()
    if primary:
        types.add(primary)

    by_name = any(term in name for term in EYE_NAME_TERMS) or bool(words & {"eye", "eyes"})
    by_type = bool(types & EYE_TYPES)
    clinical = bool(types & CLINICAL_TYPES)

    if by_name and by_type:
        return 1.0
    if by_type:
        return 0.9
    if by_name:
        return 0.8
    if clinical:
        return 0.35
    return 0.1


def _proximity(distance_m: float, radius_m: int) -> float:
    if radius_m <= 0:
        return 0.0
    return max(0.0, 1.0 - (distance_m / float(radius_m)))


def _reputation(place: dict) -> float:
    rating = place.get("rating")
    if not isinstance(rating, (int, float)):
        # Unknown, not bad. A neutral 0.5 keeps an unrated facility from being pushed
        # below a worse-but-rated one on the strength of data that does not exist.
        return 0.5
    count = place.get("review_count")
    n = float(count) if isinstance(count, int) and count > 0 else 0.0
    damped = ((float(rating) * n) + (RATING_PRIOR * RATING_PRIOR_WEIGHT)) / (n + RATING_PRIOR_WEIGHT)
    return max(0.0, min(1.0, (damped - 1.0) / 4.0))


def _open_factor(place: dict) -> float:
    value = place.get("open_now")
    if value is True:
        return 1.0
    if value is False:
        return 0.0
    return 0.5          # not published for this facility — neither rewarded nor punished


def completeness(place: dict) -> float:
    present = sum(1 for f in COMPLETENESS_FIELDS if place.get(f) is not None)
    return present / float(len(COMPLETENESS_FIELDS))


def badges(place: dict) -> list[str]:
    """Access labels, each one backed by a field that is actually present.

    Nothing here is a claim about care. "Highly rated" is a statement about Google
    reviews and is shown next to the rating and the review count so the reader can see
    exactly what it is based on.
    """
    out: list[str] = []
    distance = place.get("distance_meters")
    if isinstance(distance, (int, float)) and distance <= NEARBY_METRES:
        out.append("nearby")
    if eye_relevance(place) >= 0.8:
        out.append("eye_focused")
    if place.get("open_now") is True:
        out.append("open_now")
    rating, count = place.get("rating"), place.get("review_count")
    if (isinstance(rating, (int, float)) and rating >= HIGH_RATING
            and isinstance(count, int) and count >= HIGH_RATING_MIN_REVIEWS):
        out.append("highly_rated")
    return out


def score(place: dict, radius_m: int) -> float:
    distance = place.get("distance_meters")
    return (
        WEIGHTS["relevance"] * eye_relevance(place)
        + WEIGHTS["proximity"] * _proximity(float(distance or 0.0), radius_m)
        + WEIGHTS["open_now"] * _open_factor(place)
        + WEIGHTS["reputation"] * _reputation(place)
        + WEIGHTS["completeness"] * completeness(place)
    )


def explain(place: dict, radius_m: int) -> dict:
    """Every factor behind one facility's position, for the docs and the tests.

    Not returned by the API. It exists so that "why is this one first?" has an answer
    that is a table of numbers rather than an opinion.
    """
    return {
        "relevance": round(eye_relevance(place), 4),
        "proximity": round(_proximity(float(place.get("distance_meters") or 0.0), radius_m), 4),
        "open_now": round(_open_factor(place), 4),
        "reputation": round(_reputation(place), 4),
        "completeness": round(completeness(place), 4),
        "weights": dict(WEIGHTS),
        "score": round(score(place, radius_m), 4),
    }


def rank(places: list[dict], latitude: float, longitude: float, radius_m: int,
         limit: int) -> list[dict]:
    """Measure, filter to the radius the patient asked for, order, and cap.

    Filtering is not cosmetic. Google's circular `locationBias` is a bias, not a fence,
    so a "within 5 km" search can come back with a facility 18 km away. Showing it would
    make the radius button a lie, and the UI's honest "nothing within 5 km — try 10 km?"
    depends on this filter being real.
    """
    seen: set[str] = set()
    measured: list[dict] = []
    for place in places:
        pid = place.get("place_id")
        if not pid or pid in seen:
            continue
        seen.add(pid)
        # A permanently closed facility is not somewhere to send a patient.
        if str(place.get("business_status") or "").upper() == "CLOSED_PERMANENTLY":
            continue
        distance = haversine_metres(latitude, longitude,
                                    place["latitude"], place["longitude"])
        if distance > radius_m:
            continue
        record = {k: v for k, v in place.items() if k not in NOT_A_FACILITY_FIELD}
        record["distance_meters"] = int(round(distance))
        record["badges"] = badges(record)
        measured.append(record)

    measured.sort(key=lambda p: (-score(p, radius_m), p["distance_meters"], p["name"]))
    return measured[:limit]


__all__ = ["badges", "completeness", "explain", "eye_relevance", "haversine_metres",
           "rank", "score", "WEIGHTS"]
