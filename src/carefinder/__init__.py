"""Smart Care Finder — the step after the screening result.

An **access** layer, not a clinical one. Nothing in this package can see a retinal
image, a grade, a Grad-CAM map, a confidence, a report or a patient. It takes a
latitude and a longitude — or a place name the patient typed — asks Google for
eye-care facilities near it, and returns a normalised list.

The boundary is the whole point, so it is stated once here and enforced by
`tests/test_care_finder.py`:

    IN   latitude, longitude, radius        (or a locality string)
    OUT  place id, name, address, location, distance, rating, open-now,
         phone, website, Google Maps URL, types

Google receives the coordinates, the radius and a fixed eye-care search phrase. It
does not receive — and there is no code path that could give it — a name, a mobile
number, a scan id, a grade, a diagnosis or a report. The screening result never
enters this package; the *frontend* uses the grade it already has to decide how
prominently to present the feature, which is a presentation choice made entirely in
the browser.

Layout mirrors `src/delivery/`, for the same reason: a capability that is not part of
the medical pipeline is mounted beside it as a router rather than wired into it.

    config.py    environment, limits, and a safe `status()` for /health
    places.py    one HTTP call to Google Places API (New), and its failures
    ranking.py   distance, eye-care relevance, and the transparent badges
    routes.py    GET /v1/care-finder/nearby
"""
