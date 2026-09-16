#!/usr/bin/env python3
"""Verify the Smart Care Finder / Google Places setup before involving the browser.

Two modes:

    scripts/check_care_finder.py                    checks config, calls NOTHING
    scripts/check_care_finder.py --near 16.5,80.6   makes ONE real Places call
    scripts/check_care_finder.py --area Vijayawada  resolves a place, then searches

This talks to Google directly, so it separates "is the key any good" from "is the app
wired up correctly". Run it first; if it passes, any remaining problem is in the app.

The three ways a Google key fails all look the same from the browser and need three
different fixes, so this names them apart:

    * the key is invalid or typo'd
    * the key is valid but the project has **Places API (New)** switched off
      (or has the LEGACY "Places API" on instead, which is a different product)
    * the key and the API are fine but the project has no billing account

No credential is printed. `--near` is echoed rounded.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import argparse  # noqa: E402

from src.carefinder import config as cfg  # noqa: E402
from src.carefinder import ranking  # noqa: E402
from src.carefinder.places import PlacesService  # noqa: E402

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"
OK, BAD, WARN = f"{GREEN}  ok {RESET}", f"{RED} fail{RESET}", f"{YELLOW} warn{RESET}"

# What to tell an operator for each stable code the service can produce. Every line is
# an action, because "it failed" is not a thing anyone can do something about.
REMEDY = {
    "not_configured": "Set GOOGLE_MAPS_API_KEY in .env (see .env.example).",
    "invalid_key": (
        "Google rejected the key itself.\n"
        "       * check for a stray space or a truncated paste\n"
        "       * the key must NOT have an HTTP-referrer restriction: this is a\n"
        "         server-to-server call, and a browser-restricted key is refused"),
    "api_disabled": (
        "The key is valid; the project does not have Places API (New) enabled.\n"
        "       Console -> APIs & Services -> Library -> \"Places API (New)\".\n"
        "       Note this is NOT the older \"Places API\" entry — enabling that one\n"
        "       does not enable this one."),
    "billing_problem": (
        "The project has no active billing account. Places has no free-key tier;\n"
        "       Google's free monthly credit still requires a billing account to exist."),
    "quota_exceeded": "The project is over its Places quota or rate limit for now.",
    "provider_unreachable": "No network route to places.googleapis.com from this machine.",
    "provider_denied": "Google denied the request. Check the key's API restrictions.",
}


def _config_check() -> bool:
    ok, reason = cfg.configured()
    print(f"[{OK if ok else BAD}] configuration")
    if not ok:
        print(f"       {reason}")
        print(f"{DIM}       {REMEDY.get('not_configured')}{RESET}")
        return False
    # Presence only. The key's value is never printed, not even a prefix.
    print(f"{DIM}       GOOGLE_MAPS_API_KEY present · region {cfg.CARE_FINDER_REGION_CODE} · "
          f"radius {cfg.DEFAULT_RADIUS_M}-{cfg.MAX_RADIUS_M} m · "
          f"detail fields {'on' if cfg.CARE_FINDER_RICH_FIELDS else 'off'}{RESET}")
    print(f"{DIM}       query: {cfg.CARE_FINDER_QUERY!r}{RESET}")
    return True


def _report(outcome, what: str) -> bool:
    if outcome.ok:
        print(f"[{OK}] {what}")
        return True
    print(f"[{BAD}] {what}")
    print(f"       code: {outcome.code}")
    remedy = REMEDY.get(outcome.code)
    if remedy:
        print(f"{DIM}       {remedy}{RESET}")
    return False


# One device search and three cities of very different sizes. Enough to show that a
# metro is not searched as if it were a village, and that the radius the server picks is
# sized to the place rather than to a constant.
SUITE = [
    ("device", "16.5062,80.6480", None),
    ("city", None, "Hyderabad"),
    ("city", None, "Phagwara"),
    ("city", None, "Delhi"),
]


def _suite() -> int:
    """Everything, in one command, against the live API. This is the check to run the
    moment a key is added — it exercises both entry points the UI has."""
    service = PlacesService()
    failures = 0
    for kind, near, area in SUITE:
        print(f"\n--- {kind}: {area or near} " + "-" * 34)
        if area:
            resolved = service.resolve_area(area)
            if not _report(resolved, f"resolve {area!r}") or not resolved.places:
                failures += 1
                continue
            top = resolved.places[0]
            lat, lng = top["latitude"], top["longitude"]
            # Sized to the place Google resolved, exactly as the endpoint does it.
            radius = cfg.radius_for_extent(top.get("viewport"))
            print(f"{DIM}       -> {top.get('address') or top['name']} · "
                  f"first search sized to {radius / 1000:.0f} km{RESET}")
            hint = top.get("name")
        else:
            lat, lng = (float(x) for x in near.split(","))
            radius, hint = cfg.DEFAULT_RADIUS_M, None

        outcome = service.search_eye_care(lat, lng, radius, area_hint=hint)
        if not _report(outcome, f"eye-care search within {radius} m"):
            failures += 1
            continue
        ranked = ranking.rank(outcome.places, lat, lng, radius, cfg.MAX_RESULTS)
        print(f"{DIM}       Google returned {len(outcome.places)}; "
              f"{len(ranked)} inside the radius{RESET}")
        for i, p in enumerate(ranked[:5], 1):
            bits = [f"{p['distance_meters'] / 1000:.1f} km"]
            if "rating" in p:
                bits.append(f"{p['rating']}\u2605 ({p.get('review_count', 0)})")
            if "open_now" in p:
                bits.append("open" if p["open_now"] else "closed")
            print(f"  {i:>2}. {p['name'][:42]:<42} {' · '.join(bits)}")
            print(f"      {DIM}{p.get('address', '(no address returned)')[:74]}{RESET}")
        if not ranked:
            print(f"[{WARN}] nothing inside the radius — the UI would offer a wider "
                  f"search here, which is correct behaviour, not a failure.")

    print()
    if failures:
        print(f"[{BAD}] {failures} of {len(SUITE)} searches failed.\n")
        return 1
    print(f"[{OK}] Smart Care Finder works end to end against the live Places API.\n")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--near", help="lat,lng to search around, e.g. 16.5062,80.6480")
    ap.add_argument("--area", help="a locality to resolve and then search around")
    ap.add_argument("--radius", type=int, default=None, help="metres (clamped)")
    ap.add_argument("--suite", action="store_true",
                    help="one device search and three city searches, end to end")
    args = ap.parse_args()

    print("\nSmart Care Finder — Google Places API (New)\n" + "-" * 46)
    if not _config_check():
        return 1

    if args.suite:
        return _suite()

    if not args.near and not args.area:
        print(f"\n{DIM}No live call made. Add --near 16.5062,80.6480, --area Vijayawada,\n"
              f"or --suite to run the whole thing end to end against the configured key.{RESET}\n")
        return 0

    service = PlacesService()
    radius = cfg.clamp_radius(args.radius)

    if args.area:
        resolved = service.resolve_area(args.area)
        if not _report(resolved, f"resolve {args.area!r}"):
            return 1
        if not resolved.places:
            print(f"[{WARN}] Google found no place called {args.area!r}.")
            return 1
        top = resolved.places[0]
        lat, lng = top["latitude"], top["longitude"]
        print(f"{DIM}       -> {top.get('address') or top['name']}{RESET}")
    else:
        try:
            lat, lng = (float(x) for x in args.near.split(","))
        except ValueError:
            print(f"[{BAD}] --near must be 'lat,lng'")
            return 2
        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
            print(f"[{BAD}] --near is not a point on Earth")
            return 2

    outcome = service.search_eye_care(lat, lng, radius)
    # Rounded to one decimal — about 11 km. Enough to confirm the right city, not
    # enough to be a record of anybody's position.
    if not _report(outcome, f"eye-care search near {lat:.1f},{lng:.1f} within {radius} m"):
        return 1

    ranked = ranking.rank(outcome.places, lat, lng, radius, cfg.MAX_RESULTS)
    print(f"{DIM}       Google returned {len(outcome.places)}; "
          f"{len(ranked)} within {radius} m after the radius filter{RESET}")
    if not ranked:
        print(f"[{WARN}] nothing eye-related within {radius} m — the app would offer a "
              f"wider search here, which is the correct behaviour, not a failure.")
        return 0

    print()
    for i, p in enumerate(ranked[:8], 1):
        bits = [f"{p['distance_meters'] / 1000:.1f} km"]
        if "rating" in p:
            bits.append(f"{p['rating']}★ ({p.get('review_count', 0)})")
        if "open_now" in p:
            bits.append("open" if p["open_now"] else "closed")
        if "phone" in p:
            bits.append("phone")
        if "website" in p:
            bits.append("web")
        print(f"  {i:>2}. {p['name'][:44]:<44} {' · '.join(bits)}")
        print(f"      {DIM}{', '.join(p.get('badges') or []) or 'no badges'}{RESET}")

    print(f"\n[{OK}] Smart Care Finder is working end to end against the live API.\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
