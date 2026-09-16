/**
 * Smart Care Finder — the states a screenshot cannot prove.
 *
 * The happy path is the easy part. What has to be trusted is what this section does when
 * the patient refuses the location prompt, when the GPS never gets a fix, when Google is
 * not configured, when there is nothing within 5 km, and when the person reading it does
 * not read English. None of those appear in a rehearsed demo, and two of them — asking
 * for a location before the patient has agreed to anything, and sending the screening
 * result to Google — would be the worst bugs this feature could have.
 *
 * No test here reaches the network or Google. `fetch` is stubbed and the map is replaced
 * by a stub that exposes its props, so "the pin and the card are the same selection" is
 * asserted rather than eyeballed.
 */
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CareBridgeProvider from "@/components/carebridge/CareBridgeProvider";
import CareFinder from "@/components/carebridge/CareFinder";
import { DICTIONARIES } from "@/lib/i18n";
import { en } from "@/lib/i18n/translations/en";
import {
  directionsUrl, distanceParts, errorKey, isConfigurationProblem, isLocationProblem,
  type Facility,
} from "@/lib/carefinder";
import { PREFS_KEY } from "@/lib/carebridge";
import { makeResult, makeUngradeable } from "./fixtures";

// The map, replaced by something that shows its props. Leaflet needs a real layout
// engine; what these tests care about is the CONTRACT between the list and the map.
const mapProps: any[] = [];
vi.mock("@/components/carebridge/CareFinderMap", () => ({
  default: (props: any) => {
    mapProps.push(props);
    return (
      <div data-testid="map" data-selected={props.selectedId ?? ""}>
        {props.facilities.map((f: Facility, i: number) => (
          <button
            key={f.place_id}
            type="button"
            data-testid={`pin-${f.place_id}`}
            aria-label={props.labels.markerLabel(f, i)}
            onClick={() => props.onSelect(f.place_id)}
          />
        ))}
      </div>
    );
  },
}));

vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => ({ authenticated: true, account: { mobile_masked: "+91 ***** 40001" } }),
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

function Wrap({ children }: { children: React.ReactNode }) {
  return <CareBridgeProvider>{children}</CareBridgeProvider>;
}

// ------------------------------------------------------------------- doubles
function facility(over: Partial<Facility> = {}): Facility {
  return {
    place_id: "p1",
    name: "Vasan Eye Care",
    latitude: 16.508,
    longitude: 80.649,
    distance_meters: 1240,
    badges: ["nearby", "eye_focused"],
    ...over,
  };
}

const OK_BODY = (results: Facility[], over: Record<string, unknown> = {}) => ({
  ok: true,
  center: { latitude: 16.5062, longitude: 80.648 },
  center_source: "device",
  area_label: null,
  radius_m: 5000,
  count: results.length,
  results,
  cached: false,
  attribution: "Powered by Google",
  disclaimer: "…",
  ...over,
});

/**
 * Stub the calls this section makes, and hand back the recorded SEARCH urls.
 *
 * Two endpoints are involved: the capability probe the section makes on mount, and the
 * search itself. Only the searches are recorded, so every assertion about "what leaves
 * the browser" is about the thing the patient actually asked for.
 */
function stubSearch(body: any, status = 200, probe: any = CONFIGURED) {
  const urls: string[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = String(url);
    if (u.includes("/care-finder/status")) {
      return { ok: probe !== null, status: probe ? 200 : 500,
               json: async () => probe } as Response;
    }
    urls.push(u);
    return { ok: status >= 200 && status < 300, status, json: async () => body } as Response;
  }));
  return urls;
}

/** What the API says when a search would actually work. */
const CONFIGURED = {
  ok: true, enabled: true, configured: true, reason: null,
  default_radius_m: 5000, max_radius_m: 25000,
};
const NOT_CONFIGURED = {
  ok: true, enabled: true, configured: false,
  reason: "missing GOOGLE_MAPS_API_KEY — Smart Care Finder needs a server-side Google key",
  default_radius_m: 5000, max_radius_m: 25000,
};

/** The browser's geolocation, in each of the ways it actually behaves. */
function stubGeolocation(outcome: "granted" | "denied" | "timeout" | "unavailable") {
  const getCurrentPosition = vi.fn((ok: any, fail: any) => {
    if (outcome === "granted") {
      ok({ coords: { latitude: 16.5062, longitude: 80.648 } });
    } else {
      fail({ code: outcome === "denied" ? 1 : outcome === "timeout" ? 3 : 2 });
    }
  });
  Object.defineProperty(navigator, "geolocation", {
    value: { getCurrentPosition }, configurable: true, writable: true,
  });
  return getCurrentPosition;
}

function removeGeolocation() {
  Object.defineProperty(navigator, "geolocation", {
    value: undefined, configurable: true, writable: true,
  });
}

beforeEach(() => { mapProps.length = 0; });

const findButton = () => screen.getByRole("button", { name: new RegExp(en.careFinder.find, "i") });

// ------------------------------------------------------- consent before location
describe("the location prompt", () => {
  it("is never raised until the patient asks for a search", async () => {
    const geo = stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([facility()]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    // The section is rendered and the button is there…
    expect(await screen.findByRole("button",
      { name: new RegExp(en.careFinder.find, "i") })).toBeInTheDocument();
    // …the device has not been asked where it is, and no search has run. The capability
    // probe does not count: it carries no location and asks Google nothing.
    expect(geo).not.toHaveBeenCalled();
    expect(urls).toHaveLength(0);
  });

  it("says what the location is for before it is requested", () => {
    stubGeolocation("granted");
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    expect(screen.getByText(new RegExp(en.careFinder.privacyNote, "i"))).toBeInTheDocument();
  });

  it("is raised once, on the click, and then the search runs", async () => {
    const geo = stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([facility()]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);
    expect(geo).toHaveBeenCalledTimes(1);
    expect(urls).toHaveLength(1);
  });
});

// ------------------------------------------------------------------- privacy
describe("what leaves the browser", () => {
  it("is a coordinate, a radius and a language — and nothing else", async () => {
    stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([facility()]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);

    const url = new URL(urls[0], "http://x");
    expect([...url.searchParams.keys()].sort())
      .toEqual(["language", "latitude", "longitude", "radius_m"]);
    // The screening result is on the same page. It must not be in this request.
    const blob = urls[0].toLowerCase();
    for (const leak of ["scan", "grade", "icdr", "referable", "confidence", "patient",
                        "report", "pdf"]) {
      expect(blob).not.toContain(leak);
    }
  });

  it("never carries a Google key, because the browser does not have one", async () => {
    stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([facility()]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);
    expect(urls[0]).not.toMatch(/key|googleapis/i);
    // The call goes to this project's own API, not to Google.
    expect(urls[0]).toContain("/v1/care-finder/nearby");
  });
});

// --------------------------------------------------------- location failures
describe("when the device cannot give a position", () => {
  it.each([
    ["denied", en.careFinder.errors.denied],
    ["timeout", en.careFinder.errors.timeout],
    ["unavailable", en.careFinder.errors.unavailable],
  ] as const)("%s is explained, and the manual search is opened", async (mode, message) => {
    stubGeolocation(mode);
    const urls = stubSearch(OK_BODY([]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(new RegExp(message, "i"));
    // No search was attempted without a position.
    expect(urls).toHaveLength(0);
    // The way forward is open, not buried behind another click.
    expect(screen.getByLabelText(en.careFinder.manualHint)).toBeVisible();
  });

  it("a browser with no geolocation at all is handled, not crashed into", async () => {
    removeGeolocation();
    stubSearch(OK_BODY([]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(new RegExp(en.careFinder.errors.unsupported, "i"));
  });

  it("the typed area is searched instead", async () => {
    stubGeolocation("denied");
    const urls = stubSearch(OK_BODY([facility()], {
      center_source: "area", area_label: "Guntur, Andhra Pradesh, India",
      area_name: "Guntur",
    }));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    const input = await screen.findByLabelText(en.careFinder.manualHint);
    fireEvent.change(input, { target: { value: "Guntur" } });
    fireEvent.click(screen.getByRole("button", { name: en.careFinder.manualSubmit }));

    await screen.findByText(en.careFinder.resultsTitle);
    const url = new URL(urls[0], "http://x");
    expect(url.searchParams.get("area")).toBe("Guntur");
    expect(url.searchParams.get("latitude")).toBeNull();
    expect(screen.getByText(/Showing eye care near Guntur, Andhra Pradesh, India/))
      .toBeInTheDocument();
  });
});

// ------------------------------------------------------- map / list as one thing
describe("the map and the list are one interface", () => {
  const two = [facility(), facility({ place_id: "p2", name: "Netra Eye Hospital",
                                      distance_meters: 3100, badges: ["eye_focused"] })];

  async function open() {
    stubGeolocation("granted");
    stubSearch(OK_BODY(two));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);
  }

  /** The list pane. Scoped, because a real marker carries the facility name too. */
  const list = () => within(screen.getByRole("region", { name: en.careFinder.resultsTitle }));

  it("selects the first facility so the map is never empty of a subject", async () => {
    await open();
    expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "p1");
  });

  it("a tap on a card selects the matching marker", async () => {
    await open();
    fireEvent.click(list().getByRole("button", { name: /Netra Eye Hospital/ }));
    await waitFor(() =>
      expect(screen.getByTestId("map")).toHaveAttribute("data-selected", "p2"));
  });

  it("a tap on a marker selects the matching card", async () => {
    await open();
    fireEvent.click(screen.getByTestId("pin-p2"));
    const card = list().getByRole("button", { name: /Netra Eye Hospital/ });
    await waitFor(() => expect(card).toHaveAttribute("aria-expanded", "true"));
    // …and the previously selected one is no longer expanded. One selection, not two.
    expect(list().getByRole("button", { name: /Vasan Eye Care/ }))
      .toHaveAttribute("aria-expanded", "false");
  });

  it("gives every marker an accessible name with the facility and its distance", async () => {
    await open();
    expect(screen.getByTestId("pin-p1"))
      .toHaveAccessibleName(/1\. Vasan Eye Care.*1\.2 km away/);
  });

  it("marks the patient's own position without writing out a coordinate", async () => {
    await open();
    expect(screen.getByText(en.careFinder.yourLocation)).toBeInTheDocument();
    expect(document.body.textContent).not.toContain("16.5062");
    expect(document.body.textContent).not.toContain("80.648");
  });
});

// ------------------------------------------------------------ facility details
describe("a facility card", () => {
  it("shows every field Google returned", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility({
      address: "Benz Circle, Vijayawada",
      rating: 4.5, review_count: 312, open_now: true,
      phone: "0866 123 4567", website: "https://vasan.example",
      badges: ["nearby", "eye_focused", "open_now", "highly_rated"],
    })]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);

    expect(screen.getAllByText(/Benz Circle, Vijayawada/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/1\.2 km away/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/4\.5 out of 5/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/312 Google reviews/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(en.careFinder.openNow).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /0866 123 4567/ })[0])
      .toHaveAttribute("href", "tel:08661234567");
  });

  it("shows NO field Google did not return", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility()]));            // name, position, distance only
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);

    // No invented rating, no invented phone number, no invented "Open now".
    expect(screen.queryByText(/out of 5/)).not.toBeInTheDocument();
    expect(screen.queryByText(new RegExp(`${en.careFinder.phone}:`))).not.toBeInTheDocument();
    expect(screen.queryByText(en.careFinder.openNow)).not.toBeInTheDocument();
    expect(screen.queryByText(en.careFinder.closed)).not.toBeInTheDocument();
    // Unknown hours are SAID, not guessed at.
    expect(screen.getAllByText(en.careFinder.hoursUnknown).length).toBeGreaterThan(0);
  });

  it("links to Google's own directions URL for that exact place", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility()]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);

    const link = screen.getAllByRole("link", { name: new RegExp(en.careFinder.directions) })[0];
    const href = link.getAttribute("href") || "";
    expect(href).toContain("https://www.google.com/maps/dir/?");
    expect(href).toContain("destination=16.508%2C80.649");
    expect(href).toContain("destination_place_id=p1");
  });

  it("never claims a facility is best, recommended or highest quality", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility({ rating: 4.9, review_count: 900,
                                   badges: ["nearby", "eye_focused", "highly_rated"] })]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);
    const text = document.body.textContent || "";
    for (const claim of ["best hospital", "best doctor", "recommended hospital",
                         "highest quality", "top rated hospital"]) {
      expect(text.toLowerCase()).not.toContain(claim);
    }
    // What it says instead: an access label, next to the data behind it.
    expect(screen.getAllByText(en.careFinder.badges.highlyRated).length).toBeGreaterThan(0);
  });
});

// ------------------------------------------------------------ rural expansion
describe("when there is nothing nearby", () => {
  it("says so without claiming the region has none, and offers a wider search", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    // The heading, not the live region — the same sentence is announced there too.
    await screen.findByRole("heading", { name: en.careFinder.emptyTitle });
    expect(screen.getByText(/That does not mean there is none in your region/))
      .toBeInTheDocument();
    for (const km of [10, 25]) {
      expect(screen.getByRole("button", { name: `Search within ${km} km` })).toBeInTheDocument();
    }
  });

  it("re-searches at the wider radius without asking for the location again", async () => {
    const geo = stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByRole("heading", { name: en.careFinder.emptyTitle });

    fireEvent.click(screen.getByRole("button", { name: "Search within 25 km" }));
    await waitFor(() => expect(urls).toHaveLength(2));
    expect(new URL(urls[1], "http://x").searchParams.get("radius_m")).toBe("25000");
    expect(geo).toHaveBeenCalledTimes(1);
  });
});

// --------------------------------------------------------------- API failures
describe("when the search service fails", () => {
  it("shows a translated sentence, never the provider's own words", async () => {
    stubGeolocation("granted");
    stubSearch({ ok: false, code: "provider_error",
                 message: "places.googleapis.com project 987654321 blocked" }, 502);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(new RegExp(en.careFinder.errors.generic, "i"));
    expect(document.body.textContent).not.toContain("googleapis");
    expect(document.body.textContent).not.toContain("987654321");
  });

  it("says 'not set up' for a missing credential, not 'Google is unavailable'", async () => {
    // The probe said yes and the search then said no — the key was pulled between the
    // two, or the probe failed open. Either way the sentence must name the real cause.
    stubGeolocation("granted");
    stubSearch({ ok: false, code: "not_configured", configuration: true }, 503);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(await screen.findByRole("button",
      { name: new RegExp(en.careFinder.find, "i") }));
    await screen.findByText(new RegExp(en.careFinder.errors.notSetUp, "i"));
    expect(screen.queryByText(new RegExp(en.careFinder.errors.notConfigured, "i")))
      .not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: new RegExp(en.careFinder.find, "i") }))
      .toBeDisabled();
  });

  it("still says 'not available' when Google itself refused us", async () => {
    stubGeolocation("granted");
    stubSearch({ ok: false, code: "api_disabled", configuration: true }, 503);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(await screen.findByRole("button",
      { name: new RegExp(en.careFinder.find, "i") }));
    await screen.findByText(new RegExp(en.careFinder.errors.notConfigured, "i"));
    // …and the exact cause is on screen for whoever has to fix it.
    expect(screen.getByText(/api_disabled/)).toBeInTheDocument();
  });

  it("offers a retry for the kind of failure a retry can fix", async () => {
    stubGeolocation("granted");
    stubSearch({ ok: false, code: "provider_unreachable" }, 502);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(new RegExp(en.careFinder.errors.network, "i"));
    expect(screen.getByRole("button", { name: new RegExp(en.careFinder.retry, "i") }))
      .toBeEnabled();
  });

  it("leaves the result and the report untouched", async () => {
    stubGeolocation("granted");
    stubSearch({ ok: false, code: "provider_error" }, 502);
    const { container } = render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(new RegExp(en.careFinder.errors.generic, "i"));
    // The section is still a section; nothing above it was thrown away.
    expect(container.querySelector("section.cf")).toBeInTheDocument();
  });
});

// --------------------------------------------------- the result-aware wording
describe("the wording follows the grade the page already has", () => {
  it.each([
    [0, en.careFinder.priority.routine, false],
    [1, en.careFinder.priority.followUp, false],
    [2, en.careFinder.priority.clinical, true],
    [3, en.careFinder.priority.specialist, true],
    [4, en.careFinder.priority.specialist, true],
  ])("grade %i", (grade, sentence, prominent) => {
    stubGeolocation("granted");
    const r = makeResult({
      grading: { ...makeResult().grading!, icdr_grade: grade as number,
                 referable: (grade as number) >= 2 },
    });
    const { container } = render(<Wrap><CareFinder r={r} /></Wrap>);
    expect(screen.getByText(sentence)).toBeInTheDocument();
    expect(container.querySelector("section.cf")?.className.includes("prominent"))
      .toBe(prominent);
  });

  it("defers to the existing clinician-review signal", () => {
    stubGeolocation("granted");
    const base = makeResult();
    const r = makeResult({
      rule_check: { ...base.rule_check!, flag: "referral_disagreement",
                    referable_agrees: false, agrees_with_cnn: false,
                    recommendation: "clinician_review" },
    });
    render(<Wrap><CareFinder r={r} /></Wrap>);
    expect(screen.getByText(en.careFinder.priority.review)).toBeInTheDocument();
  });

  it("names no grade when the photograph could not be graded", () => {
    stubGeolocation("granted");
    render(<Wrap><CareFinder r={makeUngradeable()} /></Wrap>);
    expect(screen.getByText(en.careFinder.priority.unreadable)).toBeInTheDocument();
    // An ungradeable photograph must not produce a follow-up interval anywhere.
    const text = document.body.textContent || "";
    expect(text).not.toMatch(/\b\d+ months?\b/);
    expect(text).not.toMatch(/\bGrade \d\b/);
  });

  it("states no clinical fact at all", () => {
    stubGeolocation("granted");
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    const text = document.body.textContent || "";
    for (const clinical of ["Moderate NPDR", "Grade 2", "77%", "scan_test_0001"]) {
      expect(text).not.toContain(clinical);
    }
  });
});

// ------------------------------------------------- the capability probe
describe("when the service cannot search at all", () => {
  it("does not offer a button that cannot work", async () => {
    const geo = stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([facility()]), 200, NOT_CONFIGURED);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);

    await screen.findByText(new RegExp(en.careFinder.errors.notSetUp, "i"));
    expect(screen.queryByRole("button", { name: new RegExp(en.careFinder.find, "i") }))
      .not.toBeInTheDocument();
    // Nor a manual search box that would fail the same way.
    expect(screen.queryByLabelText(en.careFinder.manualHint)).not.toBeInTheDocument();
    // And nothing was asked of the device or of Google.
    expect(geo).not.toHaveBeenCalled();
    expect(urls).toHaveLength(0);
  });

  it("names the missing variable, so somebody can fix it", async () => {
    stubSearch(OK_BODY([]), 200, NOT_CONFIGURED);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    await screen.findByText(/GOOGLE_MAPS_API_KEY/);
    expect(screen.getByText(en.careFinder.setupLabel)).toBeInTheDocument();
  });

  it("never prints a credential, only the name of one", async () => {
    stubSearch(OK_BODY([]), 200, NOT_CONFIGURED);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    await screen.findByText(/GOOGLE_MAPS_API_KEY/);
    const text = document.body.textContent || "";
    expect(text).not.toMatch(/AIza/);
    expect(text).not.toMatch(/=\s*\S/);
  });

  it("says the screening result is unaffected", async () => {
    stubSearch(OK_BODY([]), 200, NOT_CONFIGURED);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    expect(await screen.findByText(new RegExp(en.careFinder.errors.notSetUpHint, "i")))
      .toBeInTheDocument();
  });

  it("assumes it works when the probe itself fails", async () => {
    // A broken probe must not hide a working feature.
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility()]), 200, null);
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    expect(await screen.findByRole("button",
      { name: new RegExp(en.careFinder.find, "i") })).toBeEnabled();
  });
});

// ------------------------------------------------- the city search
describe("searching by city", () => {
  it("lets the server size the first search to the place", async () => {
    // A city is not a point. Sending radius_m=5000 for "Hyderabad" would search 5 km
    // around a centroid; omitting it asks the server to size it to the city.
    const urls = stubSearch(OK_BODY([facility()], {
      center_source: "area", area_label: "Hyderabad, Telangana, India",
      area_name: "Hyderabad", radius_m: 25000,
    }));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(await screen.findByText(en.careFinder.manualTitle));
    fireEvent.change(screen.getByLabelText(en.careFinder.manualHint),
      { target: { value: "Hyderabad" } });
    fireEvent.click(screen.getByRole("button", { name: en.careFinder.manualSubmit }));
    await screen.findByText(en.careFinder.resultsTitle);

    const url = new URL(urls[0], "http://x");
    expect(url.searchParams.get("area")).toBe("Hyderabad");
    expect(url.searchParams.has("radius_m")).toBe(false);
    // The radius the server chose is what the header reports back.
    expect(screen.getByText(/Within 25 km/)).toBeInTheDocument();
  });

  it("pins the radius once the patient presses a radius button", async () => {
    const urls = stubSearch(OK_BODY([facility()], {
      center_source: "area", area_name: "Hyderabad", radius_m: 25000,
    }));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(await screen.findByText(en.careFinder.manualTitle));
    fireEvent.change(screen.getByLabelText(en.careFinder.manualHint),
      { target: { value: "Hyderabad" } });
    fireEvent.click(screen.getByRole("button", { name: en.careFinder.manualSubmit }));
    await screen.findByText(en.careFinder.resultsTitle);

    fireEvent.click(screen.getByRole("button", { name: "Search within 10 km" }));
    await waitFor(() => expect(urls).toHaveLength(2));
    const second = new URL(urls[1], "http://x");
    expect(second.searchParams.get("radius_m")).toBe("10000");
    expect(second.searchParams.get("area")).toBe("Hyderabad");
  });
});

// ------------------------------------------------- what a distance means
describe("a distance says where it is measured from", () => {
  it("from the device, after a device search", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility()]));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(await screen.findByRole("button",
      { name: new RegExp(en.careFinder.find, "i") }));
    await screen.findByText(en.careFinder.resultsTitle);
    expect(screen.getAllByText(new RegExp(en.careFinder.distanceFromYou)).length)
      .toBeGreaterThan(0);
  });

  it("from the place typed, after a city search — never implying it is from you",
    async () => {
      stubSearch(OK_BODY([facility()], {
        center_source: "area", area_name: "Hyderabad", radius_m: 25000,
      }));
      render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
      fireEvent.click(await screen.findByText(en.careFinder.manualTitle));
      fireEvent.change(screen.getByLabelText(en.careFinder.manualHint),
        { target: { value: "Hyderabad" } });
      fireEvent.click(screen.getByRole("button", { name: en.careFinder.manualSubmit }));
      await screen.findByText(en.careFinder.resultsTitle);

      expect(screen.getAllByText(/Distance from Hyderabad/).length).toBeGreaterThan(0);
      expect(screen.queryByText(new RegExp(en.careFinder.distanceFromYou)))
        .not.toBeInTheDocument();
    });
});

// --------------------------------------------------------------- CareBridge
describe("CareBridge integration", () => {
  it("every language has the whole feature, in its own script", () => {
    for (const code of ["hi", "te", "pa"] as const) {
      const dict = DICTIONARIES[code].careFinder;
      expect(dict.find).not.toBe(en.careFinder.find);
      expect(dict.privacyNote).not.toBe(en.careFinder.privacyNote);
      expect(dict.directions).not.toBe(en.careFinder.directions);
      expect(dict.badges.openNow).not.toBe(en.careFinder.badges.openNow);
      // The placeholders that make a sentence render have to survive translation.
      expect(dict.emptyBody).toContain("{km}");
      expect(dict.markerLabel).toContain("{name}");
      expect(dict.markerLabel).toContain("{distance}");
      expect(dict.areaShown).toContain("{area}");
      expect(dict.foundCount).toContain("{count}");
    }
  });

  it("renders in the chosen language, not in English", () => {
    stubGeolocation("granted");
    window.localStorage.setItem(PREFS_KEY,
      JSON.stringify({ lang: "te", voice: false, level: "simple", chosen: true }));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    expect(screen.getByRole("button", { name: new RegExp(DICTIONARIES.te.careFinder.find) }))
      .toBeInTheDocument();
    expect(screen.queryByText(en.careFinder.find)).not.toBeInTheDocument();
  });

  it("offers the voice guidance through the existing Listen control", async () => {
    stubGeolocation("granted");
    stubSearch(OK_BODY([facility()]));
    window.localStorage.setItem(PREFS_KEY,
      JSON.stringify({ lang: "en", voice: true, level: "simple", chosen: true }));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(findButton());
    await screen.findByText(en.careFinder.resultsTitle);
    // Either the Listen button or the honest "no voice on this device" note — both come
    // from SpeakButton, which is the point: no second speech engine was built.
    const listen = screen.queryByRole("button", { name: en.a11y.speak });
    const note = screen.queryByText(new RegExp(en.errors.voiceUnsupported));
    expect(listen || note).toBeTruthy();
  });

  it("carries the CareBridge language to the search", async () => {
    stubGeolocation("granted");
    const urls = stubSearch(OK_BODY([facility()]));
    window.localStorage.setItem(PREFS_KEY,
      JSON.stringify({ lang: "pa", voice: false, level: "simple", chosen: true }));
    render(<Wrap><CareFinder r={makeResult()} /></Wrap>);
    fireEvent.click(screen.getByRole("button",
      { name: new RegExp(DICTIONARIES.pa.careFinder.find) }));
    await waitFor(() => expect(urls).toHaveLength(1));
    expect(new URL(urls[0], "http://x").searchParams.get("language")).toBe("pa");
  });
});

// --------------------------------------------------------------- pure helpers
describe("the client helpers", () => {
  it("says metres below a kilometre and kilometres above it", () => {
    expect(distanceParts(340)).toEqual({ key: "careFinder.distanceM", value: "340" });
    expect(distanceParts(1240)).toEqual({ key: "careFinder.distanceKm", value: "1.2" });
    expect(distanceParts(18400)).toEqual({ key: "careFinder.distanceKm", value: "18" });
  });

  it("maps every backend code to a real translation key", () => {
    for (const code of ["not_configured", "quota_exceeded", "rate_limited",
                        "provider_unreachable", "area_not_found", "location_denied"]) {
      expect(errorKey(code)).not.toBe("careFinder.errors.generic");
    }
    expect(errorKey("something_new_from_the_server")).toBe("careFinder.errors.generic");
  });

  it("knows which failures a retry cannot fix", () => {
    expect(isConfigurationProblem("api_disabled")).toBe(true);
    expect(isConfigurationProblem("billing_problem")).toBe(true);
    expect(isConfigurationProblem("provider_unreachable")).toBe(false);
    expect(isLocationProblem("location_denied")).toBe(true);
    expect(isLocationProblem("quota_exceeded")).toBe(false);
  });

  it("builds a directions URL that works on desktop, Android and iOS", () => {
    const url = new URL(directionsUrl(facility()));
    expect(url.origin + url.pathname).toBe("https://www.google.com/maps/dir/");
    expect(url.searchParams.get("api")).toBe("1");
    expect(url.searchParams.get("destination")).toBe("16.508,80.649");
    expect(url.searchParams.get("destination_place_id")).toBe("p1");
  });
});
