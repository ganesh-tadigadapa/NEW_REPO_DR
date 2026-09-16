// Client for Smart Care Finder.
//
// Note what this file does NOT contain: a Google API key, a Google URL, a Places
// request, a scan id, a grade or anything else from the screening. The browser talks to
// this project's own API and to nothing else; the key lives on the server, which is why
// there is no `NEXT_PUBLIC_GOOGLE_*` value anywhere in the frontend.
//
// Two things travel out of the browser, and only after the person presses a button:
// a coordinate pair (or a place name they typed) and their CareBridge language. That is
// the entire payload.
import { authFetch } from "@/lib/auth";
import type { StringKey } from "@/lib/i18n";

/** One facility, exactly as the API normalised it. Every field beyond the first four is
 *  optional because Google genuinely does not have all of them for every place — and a
 *  missing field is rendered as missing, never as a placeholder. */
export type Facility = {
  place_id: string;
  name: string;
  latitude: number;
  longitude: number;
  /** Straight-line metres from the search centre. Computed by the API, not by Google. */
  distance_meters: number;
  /** Access labels, each backed by a field that is actually present. */
  badges: FacilityBadge[];
  address?: string;
  rating?: number;
  review_count?: number;
  open_now?: boolean;
  phone?: string;
  website?: string;
  maps_url?: string;
  types?: string[];
  primary_type?: string;
  business_status?: string;
};

export type FacilityBadge = "nearby" | "eye_focused" | "open_now" | "highly_rated";

export type NearbyResponse = {
  ok: true;
  center: { latitude: number; longitude: number };
  center_source: "device" | "area";
  area_label: string | null;
  /** The resolved place's short name. Present only for an area search; it is what the
   *  distance label names, so "1.2 km" cannot be read as "from you" when it is not. */
  area_name?: string | null;
  radius_m: number;
  count: number;
  results: Facility[];
  cached: boolean;
  attribution: string;
  disclaimer: string;
};

export type NearbyFailure = {
  ok: false;
  code?: string;
  /** True when retrying cannot help until an operator changes something. */
  configuration?: boolean;
};

export type NearbyResult = NearbyResponse | NearbyFailure;

/** The radius steps the UI offers, in metres. The API clamps whatever it is sent. */
export const RADIUS_STEPS = [5_000, 10_000, 25_000] as const;
export const DEFAULT_RADIUS_M = RADIUS_STEPS[0];

/**
 * Backend code -> translation key.
 *
 * A lookup rather than a rendered sentence from the server, for the same reason the
 * WhatsApp client uses one: the server answers in one language and the patient reads in
 * theirs. An unrecognised code falls through to the generic sentence — never to a raw
 * provider string, of which the API sends none anyway.
 */
const ERROR_KEYS: Record<string, StringKey> = {
  // "Nothing has been set up" and "Google refused us" are different facts, and telling a
  // patient the second when the truth is the first is a lie that also wastes an
  // operator's afternoon. `not_configured` is the only code that means no credential
  // exists at all.
  not_configured: "careFinder.errors.notSetUp",
  provider_denied: "careFinder.errors.notConfigured",
  api_disabled: "careFinder.errors.notConfigured",
  invalid_key: "careFinder.errors.notConfigured",
  billing_problem: "careFinder.errors.notConfigured",
  quota_exceeded: "careFinder.errors.quota",
  rate_limited: "careFinder.errors.rateLimited",
  provider_unreachable: "careFinder.errors.network",
  provider_error: "careFinder.errors.generic",
  invalid_request: "careFinder.errors.generic",
  area_not_found: "careFinder.errors.areaNotFound",
  no_location: "careFinder.errors.unavailable",
  // Browser-side geolocation failures, mapped through the same function so the UI has
  // one way of turning a problem into a sentence.
  location_denied: "careFinder.errors.denied",
  location_timeout: "careFinder.errors.timeout",
  location_unavailable: "careFinder.errors.unavailable",
  location_unsupported: "careFinder.errors.unsupported",
};

export function errorKey(code?: string): StringKey {
  return (code && ERROR_KEYS[code]) || "careFinder.errors.generic";
}

/** The follow-up sentence for a failure, or null when the main one says enough. */
export function errorHintKey(code?: string): StringKey | null {
  if (code === "not_configured") return "careFinder.errors.notSetUpHint";
  if (isConfigurationProblem(code)) return "careFinder.errors.notConfiguredHint";
  if (isLocationProblem(code)) return "careFinder.errors.deniedHint";
  return null;
}

/** Codes that mean "this will never work until an operator changes something". The UI
 *  offers Retry only for the other kind. */
export function isConfigurationProblem(code?: string): boolean {
  return code === "not_configured" || code === "provider_denied"
    || code === "api_disabled" || code === "invalid_key"
    || code === "billing_problem";
}

/** Codes that mean the device could not supply a position, so the manual search is the
 *  way forward rather than a retry. */
export function isLocationProblem(code?: string): boolean {
  return Boolean(code && code.startsWith("location_"));
}

// ------------------------------------------------------------------ the probe
export type CareFinderStatus = {
  enabled: boolean;
  configured: boolean;
  /** Names the missing VARIABLE when unconfigured, never its value. Same string
   *  `/health` already publishes; it is a diagnostic, not a credential. */
  reason: string | null;
  default_radius_m: number;
  max_radius_m: number;
};

/**
 * Ask the API whether a search could work at all, before offering one.
 *
 * Without this the section renders a button that cannot succeed: the patient presses it,
 * waits through a spinner, and is told something vague — when the server knew the answer
 * before the page finished loading. `null` means the probe itself failed, and the caller
 * treats that as "assume it works", because a broken probe must not hide a working
 * feature.
 */
export async function getCareFinderStatus(): Promise<CareFinderStatus | null> {
  try {
    const r = await authFetch("/v1/care-finder/status");
    if (!r.ok) return null;
    const body = await r.json();
    if (!body || typeof body.configured !== "boolean") return null;
    return body as CareFinderStatus;
  } catch {
    return null;
  }
}

// ------------------------------------------------------------------ geolocation
export type Position = { latitude: number; longitude: number };

export type LocationFailure = {
  code: "location_denied" | "location_timeout" | "location_unavailable"
    | "location_unsupported";
};

/**
 * Ask the browser where the device is. Called ONLY from a click handler.
 *
 * Nothing on any page requests a position on load: a health service that pops a location
 * prompt at a patient before it has explained why is a health service people close.
 *
 * Every documented failure is handled, because on the devices this is built for they all
 * happen — permission refused on a shared phone, no fix indoors, and a timeout on a
 * handset whose GPS is cold.
 */
export function getPosition(timeoutMs = 12_000): Promise<Position | LocationFailure> {
  if (typeof navigator === "undefined" || !navigator.geolocation) {
    return Promise.resolve({ code: "location_unsupported" });
  }
  return new Promise((resolve) => {
    let settled = false;
    const done = (v: Position | LocationFailure) => {
      if (!settled) { settled = true; resolve(v); }
    };
    // Some browsers never call either callback when the permission prompt is dismissed
    // rather than answered, which would leave the button spinning forever.
    const guard = setTimeout(() => done({ code: "location_timeout" }), timeoutMs + 1_000);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        clearTimeout(guard);
        done({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
      },
      (err) => {
        clearTimeout(guard);
        const code =
          err?.code === 1 ? "location_denied"
            : err?.code === 3 ? "location_timeout"
              : "location_unavailable";
        done({ code });
      },
      // A town-level fix is all a 5 km search needs, and not asking for high accuracy
      // keeps the wait short and the battery cost small on a cheap handset.
      { enableHighAccuracy: false, timeout: timeoutMs, maximumAge: 120_000 },
    );
  });
}

export function isPosition(v: Position | LocationFailure): v is Position {
  return typeof (v as Position).latitude === "number";
}

// --------------------------------------------------------------------- the call
/**
 * Ask this project's API for eye care near a point, or near a place name.
 *
 * Never throws for a search failure: a refusal is an `ok: false` answer the card
 * renders, because the screening result on the page must survive a maps problem. The
 * only throw path is a transport failure, which is caught here and reported as one.
 */
export async function findNearby(params: {
  position?: Position;
  area?: string;
  /** Omit it to let the server size the search to the place that was named: "Hyderabad"
   *  then searches a city rather than 5 km around a centroid. Passing one means the
   *  patient pressed a radius button, and their choice wins. */
  radiusM?: number;
  language: string;
  signal?: AbortSignal;
}): Promise<NearbyResult> {
  const q = new URLSearchParams();
  if (params.position) {
    q.set("latitude", String(params.position.latitude));
    q.set("longitude", String(params.position.longitude));
  } else if (params.area) {
    q.set("area", params.area.trim());
  }
  // Deliberately absent when undefined — see the `radiusM` note above. An omitted
  // parameter and a defaulted one mean different things to this API.
  if (params.radiusM !== undefined) q.set("radius_m", String(params.radiusM));
  q.set("language", params.language);

  try {
    const r = await authFetch(`/v1/care-finder/nearby?${q.toString()}`,
      { signal: params.signal });
    const body = await r.json().catch(() => null);
    if (r.ok && body?.ok) return body as NearbyResponse;
    return {
      ok: false,
      code: body?.code || body?.detail?.error?.code,
      configuration: Boolean(body?.configuration),
    };
  } catch {
    return { ok: false, code: "provider_unreachable" };
  }
}

// ------------------------------------------------------------------- formatting
/** Metres -> the two forms a person actually says. Under a kilometre stays in metres. */
export function distanceParts(metres: number): { key: StringKey; value: string } {
  if (metres < 950) {
    return { key: "careFinder.distanceM", value: String(Math.round(metres / 10) * 10) };
  }
  const km = metres / 1000;
  return { key: "careFinder.distanceKm", value: km < 10 ? km.toFixed(1) : String(Math.round(km)) };
}

export function radiusKm(metres: number): string {
  return String(Math.round(metres / 1000));
}

/**
 * The directions link.
 *
 * Google's documented Maps URL scheme, which is the one that resolves correctly in a
 * desktop browser, in Google Maps on Android and in Maps on iOS. The place id is
 * included when Google gave us one: it names the exact facility rather than trusting a
 * name-and-coordinate lookup to land on the right building.
 *
 * Nothing here is hand-assembled from guesswork, and `maps_url` — Google's own canonical
 * link for the place — is preferred when the caller wants to open the listing itself.
 */
export function directionsUrl(f: Facility): string {
  const q = new URLSearchParams({ api: "1", destination: `${f.latitude},${f.longitude}` });
  if (f.place_id) q.set("destination_place_id", f.place_id);
  return `https://www.google.com/maps/dir/?${q.toString()}`;
}

/** A `tel:` link the dialler will accept. Spaces and dashes are presentation only. */
export function telHref(phone: string): string {
  return `tel:${phone.replace(/[^\d+]/g, "")}`;
}

/** Badge -> its translation key. Kept here so a badge the API adds later renders
 *  nothing rather than the raw code. */
const BADGE_KEYS: Record<FacilityBadge, StringKey> = {
  nearby: "careFinder.badges.nearby",
  eye_focused: "careFinder.badges.eyeFocused",
  open_now: "careFinder.badges.openNow",
  highly_rated: "careFinder.badges.highlyRated",
};

export function badgeKey(badge: string): StringKey | null {
  return BADGE_KEYS[badge as FacilityBadge] ?? null;
}
