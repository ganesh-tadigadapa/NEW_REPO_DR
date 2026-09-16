"""Smart Care Finder — the behaviour that matters when nobody is watching.

Not one test in this file reaches Google. The Places transport is replaced by a callable
that records what it was asked to do and returns what the test tells it to, so every
branch — the happy path, each configuration failure, the radius fence, the rate limit,
the cache, the manual-area path — runs in milliseconds and costs nothing.

The four properties worth stating, because they are what makes this feature safe:

  * **Nothing is invented.** A field Google did not return is ABSENT from the response.
    No default rating, no placeholder phone number, no guessed opening hours.
  * **Google is told nothing about the patient.** The recorded request body is asserted
    against, field by field, and against a screening result planted in the test.
  * **The radius is real.** Google's circular bias is a suggestion; the filter is not.
  * **The ranking is about access, not about clinical quality**, and the badges only
    appear when the field behind them is genuinely present.
"""
from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.carefinder import config as cfg
from src.carefinder import ranking
from src.carefinder import routes as routes_mod
from src.carefinder.places import PlacesService, normalise, set_places_service
from tests.conftest import auth_header, signup

PATIENT = "+919812340101"

# Vijayawada, roughly. Any two points would do; real ones make the distances readable.
CENTRE = (16.5062, 80.6480)


# --------------------------------------------------------------- Google doubles
def place(pid, name, lat, lng, **extra):
    """A Places API (New) place, in the shape Google actually returns it."""
    out = {
        "id": pid,
        "displayName": {"text": name, "languageCode": "en"},
        "location": {"latitude": lat, "longitude": lng},
    }
    out.update(extra)
    return out


class FakeGoogle:
    """Stands in for the one HTTP call. Records every request; returns what it is told."""

    def __init__(self, responses):
        # A list of (status, body) pairs, consumed in order; the last one repeats.
        self._responses = list(responses)
        self.requests: list[dict] = []

    def __call__(self, url, headers, payload):
        self.requests.append({"url": url, "headers": headers, "payload": payload})
        status, body = self._responses[min(len(self.requests) - 1, len(self._responses) - 1)]
        return status, body

    @property
    def calls(self) -> int:
        return len(self.requests)


def google_ok(places):
    return (200, {"places": places})


def google_error(status, gstatus, message=""):
    return (status, {"error": {"code": status, "status": gstatus, "message": message}})


# ------------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _configured(monkeypatch):
    """A configured Care Finder with an obviously fake key. Nothing here can reach
    Google: the service is always injected with a transport double."""
    monkeypatch.setattr(cfg, "CARE_FINDER_ENABLED", True)
    monkeypatch.setattr(cfg, "GOOGLE_MAPS_API_KEY", "test-key-not-real")
    monkeypatch.setattr(cfg, "DEFAULT_RADIUS_M", 5_000)
    monkeypatch.setattr(cfg, "MIN_RADIUS_M", 500)
    monkeypatch.setattr(cfg, "MAX_RADIUS_M", 25_000)
    monkeypatch.setattr(cfg, "MAX_RESULTS", 20)
    monkeypatch.setattr(cfg, "CACHE_TTL_SECONDS", 300)
    monkeypatch.setattr(cfg, "RATE_LIMIT_SEARCHES", 30)
    routes_mod.reset_state()
    yield
    routes_mod.reset_state()
    set_places_service(None)


@pytest.fixture
def client(auth_store):
    from src.auth.routes import router as auth_router

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(routes_mod.router)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def token(client):
    return signup(client, PATIENT)["token"]


def use_google(responses) -> FakeGoogle:
    fake = FakeGoogle(responses)
    set_places_service(PlacesService(transport=fake))
    return fake


def search(client, token, **params):
    return client.get("/v1/care-finder/nearby", params=params, headers=auth_header(token))


# ------------------------------------------------------------- normalisation
def test_a_field_google_did_not_return_is_absent_not_invented():
    """The single most important property of this module. A fabricated phone number on
    a health facility is worse than a missing one."""
    bare = normalise(place("p1", "District Eye Hospital", *CENTRE))
    assert bare == {"place_id": "p1", "name": "District Eye Hospital",
                    "latitude": CENTRE[0], "longitude": CENTRE[1]}
    for invented in ("rating", "review_count", "open_now", "phone", "website",
                     "address", "maps_url"):
        assert invented not in bare


def test_every_field_google_did_return_survives_normalisation():
    full = normalise(place(
        "p2", "Sankara Nethralaya", 16.51, 80.65,
        formattedAddress="MG Road, Vijayawada",
        rating=4.62, userRatingCount=1240,
        currentOpeningHours={"openNow": True},
        nationalPhoneNumber="0866 123 4567",
        websiteUri="https://example.org",
        googleMapsUri="https://maps.google.com/?cid=1",
        types=["ophthalmologist", "doctor"], primaryType="ophthalmologist",
        businessStatus="OPERATIONAL"))
    assert full["rating"] == 4.6            # rounded to one decimal, not re-scaled
    assert full["review_count"] == 1240
    assert full["open_now"] is True
    assert full["phone"] == "0866 123 4567"
    assert full["website"] == "https://example.org"
    assert full["maps_url"] == "https://maps.google.com/?cid=1"
    assert full["types"] == ["ophthalmologist", "doctor"]


def test_a_place_with_no_identity_or_no_position_is_dropped():
    assert normalise({"id": "x", "displayName": {"text": "No location"}}) is None
    assert normalise(place("", "Nameless", *CENTRE)) is None


def test_a_zero_review_count_is_not_reported_as_a_review_count():
    out = normalise(place("p", "Eye Clinic", *CENTRE, rating=0, userRatingCount=0))
    assert "review_count" not in out


# ------------------------------------------------------------------- the route
def test_a_search_needs_a_session(client):
    use_google([google_ok([])])
    r = client.get("/v1/care-finder/nearby",
                   params={"latitude": CENTRE[0], "longitude": CENTRE[1]})
    assert r.status_code == 401


@pytest.mark.parametrize("params", [
    {"latitude": 91, "longitude": 80},
    {"latitude": -91, "longitude": 80},
    {"latitude": 16, "longitude": 181},
    {"latitude": 16, "longitude": -181},
])
def test_impossible_coordinates_are_refused_before_google_is_called(client, token, params):
    fake = use_google([google_ok([])])
    assert search(client, token, **params).status_code == 422
    assert fake.calls == 0


def test_a_request_with_neither_a_point_nor_an_area_is_refused(client, token):
    fake = use_google([google_ok([])])
    r = search(client, token)
    assert r.status_code == 400 and r.json()["code"] == "no_location"
    assert fake.calls == 0


def test_the_happy_path_returns_normalised_ranked_results(client, token):
    use_google([google_ok([
        place("far", "General Hospital", 16.530, 80.680, types=["hospital"]),
        place("near", "Vasan Eye Care", 16.508, 80.649,
              formattedAddress="Benz Circle", rating=4.5, userRatingCount=310,
              currentOpeningHours={"openNow": True},
              types=["ophthalmologist"], googleMapsUri="https://maps.google.com/?cid=9"),
    ])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["count"] == 2
    # Eye-focused, close, open and well reviewed outranks a general hospital further out.
    assert body["results"][0]["place_id"] == "near"
    assert body["results"][0]["distance_meters"] < 1000
    assert body["attribution"] == "Powered by Google"


def test_no_results_is_a_successful_answer_not_an_error(client, token):
    use_google([google_ok([])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["results"] == [] and body["count"] == 0
    # "nothing within 5 km" — not "no eye care exists in this region".
    assert body["radius_m"] == 5_000


def test_the_radius_is_a_fence_not_a_suggestion(client, token):
    """Google's circular locationBias is a bias. A 5 km search that shows a facility
    18 km away would make the radius button a lie."""
    use_google([google_ok([
        place("inside", "Netra Eye Clinic", 16.520, 80.650),
        place("outside", "Faraway Eye Hospital", 16.80, 80.90),
    ])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], radius_m=5000)
    ids = [p["place_id"] for p in r.json()["results"]]
    assert ids == ["inside"]


def test_a_wider_radius_finds_what_the_narrow_one_could_not(client, token):
    far = place("outside", "Faraway Eye Hospital", 16.60, 80.70)
    use_google([google_ok([far])])
    narrow = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], radius_m=5000)
    assert narrow.json()["results"] == []
    wide = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], radius_m=25000)
    assert [p["place_id"] for p in wide.json()["results"]] == ["outside"]


def test_the_radius_is_clamped_server_side(client, token):
    fake = use_google([google_ok([])])
    assert search(client, token, latitude=CENTRE[0], longitude=CENTRE[1],
                  radius_m=50_000).json()["radius_m"] == 25_000
    assert search(client, token, latitude=CENTRE[0], longitude=CENTRE[1],
                  radius_m=1).json()["radius_m"] == 500
    for req in fake.requests:
        assert req["payload"]["locationBias"]["circle"]["radius"] <= 25_000


def test_a_permanently_closed_facility_is_not_somewhere_to_send_a_patient(client, token):
    use_google([google_ok([
        place("shut", "Closed Eye Hospital", 16.507, 80.649,
              businessStatus="CLOSED_PERMANENTLY"),
        place("open", "Open Eye Hospital", 16.507, 80.650),
    ])])
    ids = [p["place_id"] for p in
           search(client, token, latitude=CENTRE[0], longitude=CENTRE[1]).json()["results"]]
    assert ids == ["open"]


def test_the_same_place_returned_twice_appears_once(client, token):
    dup = place("same", "Eye Hospital", 16.507, 80.649)
    use_google([google_ok([dup, dict(dup)])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert r.json()["count"] == 1


# --------------------------------------------------------------------- privacy
FORBIDDEN = ("scan_", "icdr", "grade", "referable", "diagnos", "retino", "patient",
             "mobile", "+9198", "report", "whatsapp", "pdf")


def test_google_is_told_nothing_about_the_patient_or_the_screening(client, token):
    """The request body is asserted field by field, and then swept for anything that
    looks like a clinical or identifying value."""
    fake = use_google([google_ok([])])
    search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], language="te")
    payload = fake.requests[0]["payload"]
    assert set(payload) == {"textQuery", "locationBias", "rankPreference", "pageSize",
                            "languageCode", "regionCode"}
    assert payload["textQuery"] == cfg.CARE_FINDER_QUERY
    assert payload["languageCode"] == "te"
    blob = json.dumps(fake.requests[0], ensure_ascii=False).lower()
    for token_ in FORBIDDEN:
        assert token_ not in blob, f"the Places request carries {token_!r}"


def test_the_api_key_travels_in_a_header_and_never_in_a_response(client, token):
    fake = use_google([google_ok([place("p", "Eye Clinic", *CENTRE)])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert fake.requests[0]["headers"]["X-Goog-Api-Key"] == "test-key-not-real"
    assert "test-key-not-real" not in r.text
    assert "test-key-not-real" not in json.dumps(client.get(
        "/v1/care-finder/status", headers=auth_header(token)).json())


def test_the_field_mask_asks_for_nothing_the_ui_does_not_show(client, token):
    fake = use_google([google_ok([])])
    search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    mask = fake.requests[0]["headers"]["X-Goog-FieldMask"].split(",")
    allowed = {
        "places.id", "places.displayName", "places.formattedAddress", "places.location",
        "places.googleMapsUri", "places.types", "places.primaryType",
        "places.businessStatus", "places.nationalPhoneNumber", "places.websiteUri",
        "places.currentOpeningHours.openNow", "places.rating", "places.userRatingCount",
    }
    assert set(mask) <= allowed, f"unused Places fields requested: {set(mask) - allowed}"
    # Photos and reviews are the expensive ones, and nothing displays them.
    assert not any(f.startswith(("places.photos", "places.reviews")) for f in mask)


# ---------------------------------------------------------------- spend control
def test_an_identical_search_does_not_call_google_twice(client, token):
    fake = use_google([google_ok([place("p", "Eye Clinic", *CENTRE)])])
    first = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    second = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert fake.calls == 1
    assert first.json()["cached"] is False and second.json()["cached"] is True
    assert first.json()["results"] == second.json()["results"]


def test_a_different_radius_is_a_different_search(client, token):
    fake = use_google([google_ok([])])
    search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], radius_m=5000)
    search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], radius_m=10000)
    assert fake.calls == 2


def test_an_account_cannot_loop_on_a_billed_api(client, token, monkeypatch):
    monkeypatch.setattr(cfg, "RATE_LIMIT_SEARCHES", 3)
    monkeypatch.setattr(cfg, "CACHE_TTL_SECONDS", 0)      # every call reaches the limiter
    routes_mod.reset_state()
    fake = use_google([google_ok([])])
    codes = [search(client, token, latitude=CENTRE[0], longitude=CENTRE[1] + i / 100).status_code
             for i in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    assert fake.calls == 3


# --------------------------------------------------------------- error handling
@pytest.mark.parametrize("google,expect_status,expect_code,expect_config", [
    (google_error(403, "PERMISSION_DENIED",
                  "Places API (New) has not been used in project 123 before"),
     503, "api_disabled", True),
    (google_error(400, "INVALID_ARGUMENT", "API key not valid. Please pass a valid API key."),
     503, "invalid_key", True),
    (google_error(403, "PERMISSION_DENIED", "billing has not been enabled"),
     503, "billing_problem", True),
    (google_error(429, "RESOURCE_EXHAUSTED", "Quota exceeded"), 429, "quota_exceeded", False),
    (google_error(503, "UNAVAILABLE", "backend unavailable"), 502, "provider_error", False),
    (google_error(400, "INVALID_ARGUMENT", "bad field mask"), 400, "invalid_request", True),
])
def test_every_google_failure_becomes_a_stable_code(client, token, google,
                                                    expect_status, expect_code,
                                                    expect_config):
    use_google([google])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert r.status_code == expect_status
    body = r.json()
    assert body["ok"] is False and body["code"] == expect_code
    assert body.get("configuration", False) is expect_config


def test_no_google_error_text_ever_reaches_the_client(client, token):
    use_google([google_error(403, "PERMISSION_DENIED",
                             "Requests to this API places.googleapis.com method "
                             "google.maps.places.v1.Places.SearchText are blocked "
                             "for project 987654321")])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    for leak in ("googleapis", "project", "987654321", "SearchText"):
        assert leak not in r.text


def test_a_network_failure_is_reported_as_one(client, token):
    def explode(url, headers, payload):
        raise OSError("connection reset by peer")
    set_places_service(PlacesService(transport=explode))
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert r.status_code == 502 and r.json()["code"] == "provider_unreachable"
    assert "connection reset" not in r.text


def test_without_a_key_the_feature_says_so_instead_of_calling_google(client, token,
                                                                    monkeypatch):
    monkeypatch.setattr(cfg, "GOOGLE_MAPS_API_KEY", "")
    fake = use_google([google_ok([])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert r.status_code == 503 and r.json()["code"] == "not_configured"
    assert fake.calls == 0
    status = client.get("/v1/care-finder/status", headers=auth_header(token)).json()
    assert status["configured"] is False
    assert "GOOGLE_MAPS_API_KEY" in status["reason"]


def test_the_status_endpoint_never_reveals_the_key(client, token):
    body = client.get("/v1/care-finder/status", headers=auth_header(token)).json()
    assert body["configured"] is True
    assert not any(isinstance(v, str) and "test-key" in v for v in body.values())


# ------------------------------------------------------------------ manual area
def test_a_typed_locality_is_resolved_then_searched(client, token):
    fake = use_google([
        google_ok([place("area", "Guntur", 16.3067, 80.4365,
                         formattedAddress="Guntur, Andhra Pradesh, India")]),
        google_ok([place("clinic", "Guntur Eye Hospital", 16.307, 80.437)]),
    ])
    r = search(client, token, area="Guntur")
    assert r.status_code == 200
    body = r.json()
    assert body["center_source"] == "area"
    assert body["area_label"] == "Guntur, Andhra Pradesh, India"
    assert body["center"]["latitude"] == pytest.approx(16.3067)
    assert [p["place_id"] for p in body["results"]] == ["clinic"]
    # The locality resolution asks for the cheap field mask only.
    assert "rating" not in fake.requests[0]["headers"]["X-Goog-FieldMask"]


def test_an_unknown_locality_says_so_rather_than_searching_the_wrong_place(client, token):
    fake = use_google([google_ok([])])
    r = search(client, token, area="Xyzzy Nowhere")
    assert r.status_code == 404 and r.json()["code"] == "area_not_found"
    assert fake.calls == 1                    # resolution only; no nearby search followed


def test_a_device_position_wins_over_a_typed_area(client, token):
    fake = use_google([google_ok([])])
    r = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1], area="Guntur")
    assert r.json()["center_source"] == "device"
    assert fake.calls == 1                    # no locality resolution happened


# --------------------------------------------------------------------- ranking
def test_distance_is_a_real_measurement():
    """One degree of latitude is about 111 km. A distance that is not measured is a
    distance that is being made up."""
    assert ranking.haversine_metres(0, 0, 1, 0) == pytest.approx(111_195, rel=0.01)
    assert ranking.haversine_metres(16.5, 80.6, 16.5, 80.6) == 0


def test_eye_relevance_reads_the_name_and_the_type_not_a_guess():
    assert ranking.eye_relevance({"name": "Sankara Nethralaya", "types": []}) >= 0.8
    assert ranking.eye_relevance({"name": "City Clinic", "types": ["ophthalmologist"]}) >= 0.9
    assert ranking.eye_relevance({"name": "District Hospital", "types": ["hospital"]}) < 0.5
    assert ranking.eye_relevance({"name": "Corner Chai Stall", "types": []}) < 0.2


def test_a_badge_is_never_shown_without_the_field_behind_it():
    nothing_known = {"name": "Eye Hospital", "distance_meters": 9_000}
    assert ranking.badges(nothing_known) == ["eye_focused"]
    assert "open_now" not in ranking.badges({**nothing_known, "open_now": False})
    # Highly rated needs BOTH a high rating and enough reviews to mean anything.
    assert "highly_rated" not in ranking.badges({**nothing_known, "rating": 5.0,
                                                 "review_count": 3})
    assert "highly_rated" in ranking.badges({**nothing_known, "rating": 4.6,
                                             "review_count": 220})


def test_one_five_star_review_does_not_outrank_a_hospital_with_four_hundred():
    a = {"name": "A Eye Hospital", "distance_meters": 1000, "rating": 5.0, "review_count": 1}
    b = {"name": "B Eye Hospital", "distance_meters": 1000, "rating": 4.4,
         "review_count": 400}
    assert ranking.score(b, 5000) > ranking.score(a, 5000)


def test_an_unrated_facility_is_treated_as_unknown_not_as_bad():
    unrated = {"name": "Eye Hospital", "distance_meters": 1000}
    poor = {"name": "Eye Hospital", "distance_meters": 1000, "rating": 1.5,
            "review_count": 200}
    assert ranking.score(unrated, 5000) > ranking.score(poor, 5000)


def test_the_ranking_weights_are_access_factors_and_are_all_declared():
    assert set(ranking.WEIGHTS) == {"relevance", "proximity", "open_now", "reputation",
                                    "completeness"}
    assert sum(ranking.WEIGHTS.values()) == pytest.approx(1.0)
    # Distance and eye-relevance together must dominate: this is a "can I get eye care
    # near here" list, not a popularity chart.
    assert ranking.WEIGHTS["relevance"] + ranking.WEIGHTS["proximity"] > 0.6
    assert ranking.WEIGHTS["reputation"] < ranking.WEIGHTS["proximity"]


def test_the_ranking_explanation_accounts_for_the_whole_score():
    p = {"name": "Vasan Eye Care", "distance_meters": 1200, "rating": 4.4,
         "review_count": 150, "open_now": True, "address": "MG Road",
         "phone": "0866 1", "website": "https://e.example"}
    detail = ranking.explain(p, 5000)
    rebuilt = sum(detail[k] * detail["weights"][k] for k in ranking.WEIGHTS)
    assert rebuilt == pytest.approx(detail["score"], abs=1e-3)


# ------------------------------------------------- the manual "search by city" path
# A city is not a point. "Hyderabad" resolves to a centroid, and a 5 km search around the
# centroid of a city 40 km across answers a question nobody asked -- at best it finds the
# clinics nearest one arbitrary spot, at worst the centroid lands on a lake and the honest
# answer becomes "nothing found". These pin the fix.
HYDERABAD = {"latitude": 17.3850, "longitude": 78.4867}
HYDERABAD_VIEWPORT = {"low": {"latitude": 17.20, "longitude": 78.25},
                      "high": {"latitude": 17.60, "longitude": 78.65}}
# Phagwara: a real town, and genuinely small.
PHAGWARA_VIEWPORT = {"low": {"latitude": 31.21, "longitude": 75.75},
                     "high": {"latitude": 31.24, "longitude": 75.79}}


def area_place(name, coords, viewport=None, address=None):
    extra = {"formattedAddress": address or f"{name}, India"}
    if viewport:
        extra["viewport"] = viewport
    return place(f"area-{name.lower()}", name, coords["latitude"], coords["longitude"],
                 **extra)


def test_a_city_search_is_sized_to_the_city(client, token):
    fake = use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([place("c1", "Eye Hospital", 17.44, 78.39)]),      # ~9 km out
    ])
    r = search(client, token, area="Hyderabad")
    body = r.json()
    # Sized from Google's own bounding box, not from our default.
    assert body["radius_m"] == 25_000
    assert fake.requests[1]["payload"]["locationBias"]["circle"]["radius"] == 25_000.0
    # …and a facility 9 km from the centroid therefore survives the radius fence.
    assert [p["place_id"] for p in body["results"]] == ["c1"]


def test_a_small_town_search_is_not_inflated_into_a_district_search(client, token):
    use_google([
        google_ok([area_place("Phagwara", {"latitude": 31.224, "longitude": 75.770},
                              PHAGWARA_VIEWPORT)]),
        google_ok([]),
    ])
    assert search(client, token, area="Phagwara").json()["radius_m"] == 5_000


def test_a_locality_with_no_viewport_falls_back_to_the_default(client, token):
    use_google([
        google_ok([area_place("Somewhere", {"latitude": 20.0, "longitude": 78.0})]),
        google_ok([]),
    ])
    assert search(client, token, area="Somewhere").json()["radius_m"] == 5_000


def test_a_radius_the_patient_chose_beats_the_one_we_would_have_chosen(client, token):
    """The radius buttons are the patient's control. Sizing to the place is only what
    happens when they have not used it."""
    fake = use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([]),
    ])
    body = search(client, token, area="Hyderabad", radius_m=5000).json()
    assert body["radius_m"] == 5_000
    assert fake.requests[1]["payload"]["locationBias"]["circle"]["radius"] == 5_000.0


def test_the_query_names_the_resolved_place_not_the_typed_string(client, token):
    """Text Search is built for "eye hospital in Hyderabad". What must NOT reach Google
    is the raw string the patient typed, which is unvalidated input."""
    fake = use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([]),
    ])
    search(client, token, area="  hyderabad telangana  ")
    query = fake.requests[1]["payload"]["textQuery"]
    assert query == f"{cfg.CARE_FINDER_QUERY} in Hyderabad"
    assert "telangana" not in query.lower()


def test_a_device_search_query_is_not_anchored_to_any_place_name(client, token):
    fake = use_google([google_ok([])])
    search(client, token, latitude=CENTRE[0], longitude=CENTRE[1])
    assert fake.requests[0]["payload"]["textQuery"] == cfg.CARE_FINDER_QUERY


def test_the_response_says_where_the_distances_are_measured_from(client, token):
    """"1.2 km away" means something different when the origin is a city the patient
    typed than when it is the phone in their hand."""
    use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([place("c1", "Eye Hospital", 17.39, 78.49)]),
    ])
    body = search(client, token, area="Hyderabad").json()
    assert body["center_source"] == "area" and body["area_name"] == "Hyderabad"

    fake2 = use_google([google_ok([])])
    device = search(client, token, latitude=CENTRE[0], longitude=CENTRE[1]).json()
    assert device["center_source"] == "device" and device["area_name"] is None
    assert fake2.calls == 1


def test_the_locality_resolution_asks_for_the_extent_and_nothing_expensive(client, token):
    fake = use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([]),
    ])
    search(client, token, area="Hyderabad")
    mask = fake.requests[0]["headers"]["X-Goog-FieldMask"].split(",")
    assert "places.viewport" in mask
    for expensive in ("places.rating", "places.currentOpeningHours.openNow",
                      "places.nationalPhoneNumber", "places.websiteUri",
                      "places.userRatingCount"):
        assert expensive not in mask


def test_two_different_cities_are_two_different_cache_entries(client, token):
    """The centre is rounded to ~110 m for the cache key. Two cities that round to the
    same cell would be a wrong answer, and the place name is part of the key so that a
    resolved name change cannot silently reuse another place's results."""
    fake = use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([]),
        google_ok([area_place("Secunderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([]),
    ])
    search(client, token, area="Hyderabad")
    search(client, token, area="Secunderabad")
    assert fake.calls == 4            # two resolutions AND two searches, not one search


def test_the_extent_maths_is_the_same_maths_as_the_distance_maths():
    """config keeps a local copy so it imports nothing. If the two ever diverge, a city
    would be sized by one formula and its facilities filtered by another."""
    a, b = (17.20, 78.25), (17.60, 78.65)
    assert cfg._haversine(*a, *b) == pytest.approx(ranking.haversine_metres(*a, *b))


def test_the_extent_radius_is_clamped_at_both_ends(monkeypatch):
    monkeypatch.setattr(cfg, "DEFAULT_RADIUS_M", 5_000)
    monkeypatch.setattr(cfg, "MAX_RADIUS_M", 25_000)
    tiny = {"low": {"latitude": 10.0, "longitude": 10.0},
            "high": {"latitude": 10.001, "longitude": 10.001}}
    huge = {"low": {"latitude": 8.0, "longitude": 68.0},
            "high": {"latitude": 37.0, "longitude": 97.0}}          # all of India
    assert cfg.radius_for_extent(tiny) == 5_000
    assert cfg.radius_for_extent(huge) == 25_000
    assert cfg.radius_for_extent(None) == 5_000
    assert cfg.radius_for_extent({"low": {}, "high": {}}) == 5_000


def test_a_viewport_is_only_ever_read_never_shown_as_a_facility_field(client, token):
    """It is search machinery. It has no business on a facility card."""
    use_google([
        google_ok([area_place("Hyderabad", HYDERABAD, HYDERABAD_VIEWPORT)]),
        google_ok([place("c1", "Eye Hospital", 17.39, 78.49,
                         viewport=HYDERABAD_VIEWPORT)]),
    ])
    body = search(client, token, area="Hyderabad").json()
    assert "viewport" not in body["results"][0]


# ------------------------------------------------------------------ the seam
def test_this_package_cannot_see_the_medical_pipeline():
    """An import here would be the first step towards a grade reaching Google."""
    import pathlib
    from src.common.config import REPO_ROOT

    banned = ("src.api.pipeline", "src.grading", "src.explain", "src.quality",
              "src.segment", "src.api.evidence", "src.delivery")
    for path in (REPO_ROOT / "src" / "carefinder").glob("*.py"):
        source = pathlib.Path(path).read_text(encoding="utf-8")
        for module in banned:
            assert f"import {module}" not in source, f"{path.name} imports {module}"
