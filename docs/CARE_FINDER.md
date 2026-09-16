# 📍 Smart Care Finder

**From screening to the next step of care.**

A screening result that tells someone their eyes need looking at, and then leaves them to
work out where, has done half a job. Smart Care Finder is the other half: one CareBridge
feature that takes the patient's location, finds real eye-care facilities near it on
Google Places, draws them on a map beside a list, shows what Google actually knows about
each one, and hands over directions that open in Google Maps on any phone.

It is an **access** feature. It does not analyse, grade, explain or recommend treatment.

```
SCREEN → QUALITY → GRADE → EXPLAIN → CAREBRIDGE → NUTRITION → REPORT → WHATSAPP
                                                                          ↓
                                                         📍 SMART CARE FINDER
                                                                          ↓
                                                    🗺️ MAP + NEARBY EYE CARE
                                                                          ↓
                                                                  🏥 FACILITY
                                                                          ↓
                                                                🧭 DIRECTIONS
```

---

## What it is not

| Not this | Because |
|---|---|
| A provider recommender | Nothing in the data describes clinical quality. The ranking is about **access** — see [Ranking](#ranking). |
| An endorsement | Every surface says so, in all four languages (`careFinder.notEndorsement`). |
| Emergency triage | The existing clinician-review logic is read, never overridden or escalated. |
| A second map product | The map is one file. The facility data is Google's; the tiles are not. |
| A place a grade can leak | Google receives a coordinate, a radius, a fixed phrase and a language code. Nothing else, by construction. |

---

## Set-up

You need **one** Google Cloud API key.

1. **Create or pick a project**, and **enable billing on it.** Places has no free-key
   tier. Google's monthly free credit still requires a billing account to exist.
2. **Enable "Places API (New)".** In the API Library this is a different entry from the
   older **"Places API"**. Enabling the legacy one does *not* enable this one, and the
   failure looks identical to a bad key from the browser.
3. **Create an API key** and restrict it:
   * *API restrictions* → **Places API (New)** only.
   * *Application restrictions* → **None**. This is a server-to-server call. A key with
     an HTTP-referrer restriction is refused with
     `API keys with referer restrictions cannot be used with this API`.
4. Put it in `.env` at the repo root:

   ```bash
   GOOGLE_MAPS_API_KEY=AIza...
   ```

5. Verify it without opening a browser:

   ```bash
   make care-finder-check                        # configuration only, no API call
   make care-finder-check SUITE=1                # the whole feature, end to end
   make care-finder-check NEAR=16.5062,80.6480   # ONE real Places call
   make care-finder-check AREA=Vijayawada        # resolve a locality, then search
   ```

   `SUITE=1` runs one device search and three city searches — Hyderabad, Phagwara and
   Delhi, deliberately very different sizes — and prints the real facilities, addresses
   and distances each one returns. It is the single command that proves the feature
   works against the live API.

   The script names the three failures apart, because they need three different fixes:
   an invalid key, a project without Places API (New), and a project without billing all
   arrive from Google as the same `PERMISSION_DENIED`.

**There is no browser key, and no `NEXT_PUBLIC_GOOGLE_*` variable anywhere in this
repository.** See [The map](#the-map) for why.

### What the patient sees before it is configured

The browser asks `GET /v1/care-finder/status` once when the result page renders, **before
offering anything**. If the API cannot search, no button is drawn at all — an offer that
cannot be taken is worse than no offer — and the section says so in the patient's own
language, with the reason underneath:

> 🛠 Nearby eye-care search has not been set up on this service yet.
> Your screening result and your report are complete and unaffected.
> `SETUP NEEDED` missing GOOGLE_MAPS_API_KEY — …

Two deliberate distinctions there:

* **"has not been set up" is not "not available right now."** Only `not_configured` —
  no credential exists at all — gets the first sentence. `api_disabled`, `invalid_key`,
  `billing_problem` and `provider_denied` get the second, because in those cases
  something *is* set up and Google refused it. Telling a patient Google is down when the
  truth is that nobody has added a key is a lie that also costs an operator an afternoon.
* **The reason names the missing VARIABLE, never its value.** It is the same string
  `/health` has always published, and it disappears the moment the API is configured.

The result, the explanation, the report and WhatsApp delivery are unaffected throughout.

---

## The endpoint

```
GET /v1/care-finder/nearby      authenticated patient -> eye care near a point
GET /v1/care-finder/status      is the feature configured at all
```

| Parameter | Notes |
|---|---|
| `latitude` | −90 … 90. Rejected with `422` outside that range, before Google is called. |
| `longitude` | −180 … 180, same. |
| `area` | 2–120 characters. Used **instead of** a coordinate pair. |
| `radius_m` | Clamped server-side. **Omitting it is not the same as sending the default** — see below. |
| `language` | The CareBridge language, passed to Google so place names come back in the reader's script. |

A session is required. Not to know who the patient is — the account is used for nothing
but the rate-limit bucket, and never reaches Google — but because an unauthenticated
proxy in front of a billed API is somebody else's free Places quota.

```json
{
  "ok": true,
  "center": { "latitude": 16.5062, "longitude": 80.648 },
  "center_source": "device",
  "area_label": null,
  "radius_m": 5000,
  "count": 2,
  "cached": false,
  "attribution": "Powered by Google",
  "disclaimer": "…not a recommendation or an endorsement…",
  "results": [
    {
      "place_id": "ChIJ…",
      "name": "Vasan Eye Care",
      "latitude": 16.508, "longitude": 80.649,
      "distance_meters": 1240,
      "badges": ["nearby", "eye_focused", "open_now"],
      "address": "Benz Circle, Vijayawada",
      "rating": 4.5, "review_count": 312, "open_now": true,
      "phone": "0866 123 4567", "website": "https://…",
      "maps_url": "https://maps.google.com/?cid=…",
      "types": ["ophthalmologist", "doctor"]
    }
  ]
}
```

**Every field after `badges` is optional, and absent when Google did not supply it.**
There is no `or "Unknown"`, no `or 0` and no placeholder anywhere in `normalise()`. A
fabricated phone number on a health facility is worse than a missing one, and the UI
renders a missing field as missing.

A `200` with `"results": []` is a real answer, not an error: nothing eye-related is
listed within the radius asked for. The UI says exactly that and offers 10 km and 25 km.

Failures use `{"ok": false, "code": "…"}` with a stable code the frontend maps to a
translated sentence — `not_configured`, `api_disabled`, `invalid_key`,
`billing_problem`, `quota_exceeded`, `rate_limited`, `provider_unreachable`,
`provider_error`, `area_not_found`. **No Google error text ever reaches the client**; it
is logged server-side, where it is the one thing that makes a broken key diagnosable.

`/health` carries the same non-secret summary as the WhatsApp block:

```json
{ "care_finder": { "enabled": true, "configured": false,
                   "reason": "missing GOOGLE_MAPS_API_KEY",
                   "default_radius_m": 5000, "max_radius_m": 25000 } }
```

### A city is not a point

`radius_m` omitted means "you choose"; `radius_m` given means the patient pressed a
radius button and their choice wins.

That distinction exists because "Hyderabad" resolves to a centroid, and searching 5 km
around the centroid of a city 40 km across answers a question nobody asked — at best it
finds the clinics nearest one arbitrary spot, at worst the centroid lands on a lake and
the honest answer becomes "nothing found". So the locality resolution also asks for
`places.viewport`, Google's own bounding box for the place, and
`config.radius_for_extent()` sizes the first search to half its diagonal, clamped between
the configured default and maximum:

| Place | Viewport diagonal | First search |
|---|---|---|
| Hyderabad | ~60 km | 25 km (the configured ceiling) |
| Phagwara | ~5 km | 5 km (the configured floor) |
| no viewport returned | — | 5 km (the default) |

The resolved place's **name** — never the string the patient typed, which is unvalidated
input — is also folded into the query Google receives (`"…eye care in Hyderabad"`), which
is what Text Search is built for and anchors relevance in a way a bias circle alone does
not.

### "1.2 km away" from what?

After a device search, from the device. After a city search, from the city the patient
typed. Those are different claims, so the card names which:

> 📏 Distance from your location: 1.2 km away
> 📏 Distance from Hyderabad: 1.2 km away

`center_source` and `area_name` in the response are what the UI reads to decide. Either
way it is a **straight-line** distance computed by this API from two coordinates Google
returned — never a travel distance and never a travel time, and the card says so.

---

## Which Places method, and why

**Text Search (New)** — `POST https://places.googleapis.com/v1/places:searchText`.

Nearby Search (New) filters by place **type**, and the Places API (New) type table
([Table A][types]) has no `ophthalmologist`, no `optometrist` and no eye-specific type at
all. The nearest available options are `doctor` and `hospital`, which would return
general practice and district hospitals and leave the patient to guess which of them does
eyes. A categorical text query matches the eye-care vocabulary that is actually in these
facilities' names and categories.

`locationBias` carries the circle, because `locationRestriction` on `searchText` accepts
a **rectangle only** — and a rectangle around a radius quietly widens the search at the
corners. The circle is then honoured exactly by filtering on the distance we compute
ourselves: Google's bias is a suggestion, and a 5 km search that showed a facility 18 km
away would make the radius button a lie.

One call per search. `rankPreference: DISTANCE`, `pageSize: 20`.

### The field mask

Places API (New) has no default field list, and the **billing SKU for the call is decided
by the most expensive field requested**. Nothing is asked for that the UI does not
display — `tests/test_care_finder.py` asserts that against an allow-list, and asserts
that photos and reviews (the expensive ones) are never requested.

| SKU | Fields | Shown as |
|---|---|---|
| Pro | `id`, `displayName`, `formattedAddress`, `location`, `googleMapsUri`, `types`, `primaryType`, `businessStatus` | name, address, pin, directions, relevance |
| Enterprise | `nationalPhoneNumber`, `websiteUri`, `currentOpeningHours.openNow`, `rating`, `userRatingCount` | ☎️ 🌐 🕐 ⭐ |

`CARE_FINDER_RICH_FIELDS=0` drops the Enterprise half for a materially cheaper search.
The cards then stop showing what they were not given.

Only `currentOpeningHours.openNow` is read. `regularOpeningHours` describes a normal week
and would be wrong on a public holiday, and "probably open" is not a thing to tell
someone deciding whether to travel.

[types]: https://developers.google.com/maps/documentation/places/web-service/place-types

---

## Ranking

**Not a medical-provider recommender, and the order must never be read as one.** Nothing
scores clinical quality, outcomes, equipment or safety, because none of that is in the
data and inventing it would be the most harmful thing this feature could do.

What is ranked is **access** (`src/carefinder/ranking.py`, every weight declared in
`WEIGHTS`):

| Factor | Weight | From |
|---|---|---|
| Eye-care relevance | 0.35 | eye vocabulary in the name (including *Netralaya*, *Nethra*, *Drishti*) or in Google's types |
| Proximity | 0.35 | the distance we computed, against the radius asked for |
| Open now | 0.12 | `currentOpeningHours.openNow`; unknown scores 0.5, neither rewarded nor punished |
| Reputation | 0.10 | rating, damped toward a neutral prior by review count |
| Listing completeness | 0.08 | how much of the listing Google filled in |

Reputation is damped so one five-star review does not outrank a hospital with four
hundred, and an **unrated** facility is treated as unknown rather than as bad.
`ranking.explain()` returns every factor for one facility, and a test asserts the factors
reconstruct the score exactly.

### The badges

Each appears only when the field behind it is genuinely present:

| Badge | Condition |
|---|---|
| **Nearby** | distance ≤ 2 km |
| **Eye-care focused** | name or Google type says so |
| **Open now** | `openNow` is literally `true` |
| **Highly rated** | rating ≥ 4.3 **and** ≥ 20 reviews — a 5.0 from three people is not a signal |

The words "best", "recommended", "highest quality" and "top" appear nowhere, in any
language, and a frontend test asserts it.

---

## The map

**Leaflet + OpenStreetMap tiles, in one file: `web/components/carebridge/CareFinderMap.tsx`.**

The facility data is Google's, fetched server-side. Drawing it needs *a* map, not a
second Google product, and three things follow from choosing a keyless one:

* **There is no browser key to leak.** A Google Maps JS key ships to every visitor;
  restricting it by referrer and API is real work to get right and easy to get wrong.
  Not having one is stronger than restricting one.
* **One key, one bill, one thing to enable.** Setup is a single line in `.env`.
* **It looks like CareBridge.** The tiles sit inside a CareBridge card, the pins use the
  project palette, and the page does not read as an embedded Google Maps demo.

Swapping in the Google Maps JavaScript API later is a change to that **one file**:
everything outside it talks to the map through `center`, `facilities`, `selectedId` and
`onSelect`. Add `NEXT_PUBLIC_GOOGLE_MAPS_BROWSER_KEY`, restrict it to the Maps JavaScript
API and to your origins, and nothing else moves.

Google's terms require attribution wherever Places data is displayed outside a Google
map. `careFinder.attribution` renders it; it is not decoration.

### Map and list are one interface

`selectedId` is the single piece of state that joins them. A tap on a pin and a tap on a
card go through the same setter, so they cannot drift apart:

* tap a **card** → it expands with the full details, the marker turns teal and grows, the
  map pans to it
* tap a **marker** → the matching card is selected, expanded and scrolled into view

**The map is never the only way to reach a facility.** Every fact drawn on it — name,
position, distance, open/closed — is also text in the list, which works without tiles,
without a pointer and with a screen reader. Markers are keyboard-focusable and carry an
accessible name of the form "3. Sankara Nethralaya, 2.4 km away. Select to see details."
On a phone the Map/List switch shows one pane at a time and **List is the default**,
because it is the view that always works.

---

## Privacy

The rules, and where each is enforced:

| Rule | Enforced by |
|---|---|
| The location prompt is never raised until the patient presses the button | `CareFinder.tsx` — `getPosition()` is called only from the click handler; a test asserts `getCurrentPosition` is untouched on render |
| Google never receives a name, a mobile number, a scan id, a grade, a diagnosis or a report | `tests/test_care_finder.py` asserts the request body field by field, then sweeps it for clinical and identifying substrings |
| The browser never sends the screening result anywhere | `lib/carefinder.ts` has nowhere to put one; a frontend test sweeps the request URL |
| The API key never reaches the browser | It is read only by `src/carefinder/`, sent in a request header, and asserted absent from every response |
| No precise location is stored | Nothing is written to disk. The in-process cache key is a coordinate rounded to **3 decimals (~110 m)** plus a radius; the log line rounds to **1 decimal (~11 km)** |
| Exact coordinates are never shown as text | The pin says "Your location"; a test asserts the numbers appear nowhere in the DOM |
| The patient is told, before they decide | `careFinder.privacyNote` is on screen at every phase, in all four languages, exactly once |

`src/carefinder/` imports none of `src.api.pipeline`, `src.grading`, `src.explain`,
`src.quality`, `src.segment`, `src.api.evidence` or `src.delivery` — and a test reads the
source files to keep it that way.

---

## Spend control

| Guard | Default | Why |
|---|---|---|
| Radius clamp | 500 m – 25 km | Google's own ceiling is 50 km; a patient does not need it |
| Result cap | 20 | Google's page-size ceiling anyway |
| One call per search | — | The locality path costs a second call, and only on that path |
| In-process TTL cache | 300 s | Makes the 10 km / 25 km buttons, a double tap and a refresh free |
| Per-account rate limit | 30 / hour | A loop or an abuse should not reach a billed API |
| Field mask | exact | Nothing requested that is not displayed |

---

## Result-aware, without touching the result

The feature reads two things off the `AnalyzeResult` the page already has, and both
choose a **sentence** and a **CSS class**:

| State | Wording | Prominence |
|---|---|---|
| Ungradeable / no model | "No grade was produced from this photograph…" | normal |
| `rule_check.recommendation === "clinician_review"` | "Your screening result needs clinician review." | **prominent** |
| Grade 0 | routine | normal |
| Grade 1 | follow-up recommended | normal |
| Grade 2 | clinical follow-up recommended | **prominent** |
| Grade 3–4 | specialist evaluation recommended | **prominent** |

The clinician-review signal is the existing system's own (`src/explain/icdr_rules.py`),
read as-is — not recomputed, not second-guessed and not overridden. No wording here
restates the grade, quotes a follow-up interval or says anything the sections above it
have not already said; tests assert that no clinical value appears in this section at all.

---

## Files

| File | Role |
|---|---|
| `src/carefinder/config.py` | environment, limits, field mask, safe `status()` |
| `src/carefinder/places.py` | one Places call; normalisation; failure → stable code |
| `src/carefinder/ranking.py` | haversine, relevance, badges, the declared weights |
| `src/carefinder/routes.py` | `/v1/care-finder/nearby`, cache, rate limit |
| `web/lib/carefinder.ts` | typed client, geolocation, directions URL, formatting |
| `web/components/carebridge/CareFinder.tsx` | the feature |
| `web/components/carebridge/CareFinderMap.tsx` | the map, and only the map |
| `web/lib/i18n/translations/*.ts` | `careFinder.*` in en / hi / te / pa |
| `scripts/check_care_finder.py` | operator verification against the live API |
| `tests/test_care_finder.py` | 44 backend tests, none of which reach Google |
| `web/tests/carefinder.test.tsx` | 41 frontend tests, none of which reach the network |
