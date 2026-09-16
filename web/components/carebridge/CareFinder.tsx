"use client";
/**
 * 📍 Smart Care Finder — "from screening to the next step of care".
 *
 * READ THIS BEFORE EDITING. This component performs no analysis and displays no clinical
 * value. It reads exactly two things off the screening result, and both are PRESENTATION
 * decisions made in the browser:
 *
 *   * `quality.gradeable` / `grading.icdr_grade` — which sentence introduces the
 *     feature, and how prominent the section is.
 *   * `rule_check.recommendation === "clinician_review"` — the existing system's own
 *     signal, read, never recomputed and never overridden.
 *
 * Neither reaches the network. The API call carries a coordinate (or a typed place
 * name), a radius and the CareBridge language. It does not carry the grade, the scan id,
 * the patient, the image or the report, and `lib/carefinder.ts` has nowhere to put them.
 *
 * ONE feature, and the parts are not separable:
 *
 *      location → nearby eye-care search → map + list, synchronised
 *              → facility details → distance → open/closed → directions
 *
 * The map and the list are two views of one selection. `selectedId` is the single piece
 * of state that joins them: a tap on a pin and a tap on a card go through the same
 * setter, so they cannot drift apart. The list is always usable on its own — see
 * CareFinderMap for why that is a hard rule rather than a nicety.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AnalyzeResult } from "@/lib/api";
import {
  DEFAULT_RADIUS_M, RADIUS_STEPS, badgeKey, directionsUrl, distanceParts, errorHintKey,
  errorKey, findNearby, getCareFinderStatus, getPosition, isConfigurationProblem,
  isLocationProblem, isPosition, radiusKm, telHref,
  type CareFinderStatus, type Facility, type NearbyResponse, type Position,
} from "@/lib/carefinder";
import type { StringKey } from "@/lib/i18n";
import { useCareBridge } from "./CareBridgeProvider";
import CareFinderMap from "./CareFinderMap";
import SpeakButton from "./SpeakButton";

type Phase = "idle" | "locating" | "searching" | "results" | "error";
type View = "map" | "list";

/**
 * How the feature introduces itself, and how loudly.
 *
 * This is the result-aware part of the brief, and it is deliberately thin: it picks a
 * SENTENCE and a CSS class. It does not restate the grade, does not recommend a
 * timescale (the "What should I do now?" section above already does, in the programme's
 * own words) and cannot change anything the patient has been told.
 */
function priorityFor(r: AnalyzeResult): { key: StringKey; prominent: boolean } {
  if (!r.quality.gradeable || !r.grading) {
    return { key: "careFinder.priority.unreadable", prominent: false };
  }
  // The existing clinician-review logic, read as-is. Not recomputed, not second-guessed.
  if (r.rule_check?.recommendation === "clinician_review") {
    return { key: "careFinder.priority.review", prominent: true };
  }
  switch (r.grading.icdr_grade) {
    case 0: return { key: "careFinder.priority.routine", prominent: false };
    case 1: return { key: "careFinder.priority.followUp", prominent: false };
    case 2: return { key: "careFinder.priority.clinical", prominent: true };
    default: return { key: "careFinder.priority.specialist", prominent: true };
  }
}

/** "https://www.vasaneye.in/vijayawada" -> "vasaneye.in". Falls back to the raw string
 *  rather than dropping the link if Google ever returns something unparseable. */
function hostOf(url: string): string {
  try { return new URL(url).hostname.replace(/^www\./, ""); } catch { return url; }
}

/** Bring an element into view, honouring the reduced-motion preference. Guarded because
 *  `scrollIntoView` does not exist in the test environment, and a missing nicety must not
 *  take the section down with it. */
function scrollIntoView(el: HTMLElement | null) {
  if (!el || typeof el.scrollIntoView !== "function") return;
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "nearest" });
}

/**
 * Scroll a card to the top of the LIST, without moving the page.
 *
 * `scrollIntoView` is the wrong tool here twice over: on a wide screen the list is a
 * scroll container of its own beside the map, and `block: "nearest"` leaves a card that
 * has just expanded with its "Get directions" button below the fold of that container —
 * which is the one control the person selected the card to reach. Scrolling the
 * container by hand also cannot jerk the whole page, which `scrollIntoView` would.
 */
function revealInList(card: HTMLElement | null) {
  const list = card?.parentElement;
  if (!card || !list || typeof list.scrollTo !== "function") return;
  if (list.scrollHeight <= list.clientHeight) return;        // not a scroll container
  const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
  const top = Math.max(0, Math.min(card.offsetTop - list.offsetTop,
                                   list.scrollHeight - list.clientHeight));
  list.scrollTo({ top, behavior: reduced ? "auto" : "smooth" });
}

/** Distance, in the words a person uses. Metres under a kilometre, kilometres above. */
function useDistanceText() {
  const { t } = useCareBridge();
  return useCallback((metres: number) => {
    const { key, value } = distanceParts(metres);
    return t(key, key === "careFinder.distanceM" ? { metres: value } : { km: value });
  }, [t]);
}

/** The labels that are real data, and only when the data is real. */
function Badges({ f }: { f: Facility }) {
  const { t } = useCareBridge();
  if (!f.badges?.length) return null;
  return (
    <ul className="cf-badges">
      {f.badges.map((b) => {
        const key = badgeKey(b);
        if (!key) return null;
        return <li key={b} className={`cf-badge cf-badge-${b}`}>{t(key)}</li>;
      })}
    </ul>
  );
}

/**
 * Everything Google actually returned about one facility, and nothing it did not.
 *
 * Every block below is behind a presence check. A facility with no phone number shows no
 * phone row — not "Phone: not available", and certainly not a number from somewhere
 * else. `open_now` is tri-state on purpose: true, false, and "not published", which is
 * common and is said out loud rather than guessed at.
 */
function FacilityDetails({
  f, compact = false, from = null,
}: { f: Facility; compact?: boolean; from?: string | null }) {
  const { t } = useCareBridge();
  const distanceText = useDistanceText();
  return (
    <div className={`cf-details${compact ? " compact" : ""}`}>
      {f.address && (
        <p className="cf-detailrow">
          <span className="cf-detailicon" aria-hidden="true">📍</span>
          <span>{f.address}</span>
        </p>
      )}
      <p className="cf-detailrow">
        <span className="cf-detailicon" aria-hidden="true">📏</span>
        <span>
          {/* WHERE FROM is part of the fact. After a city search the origin is a place
              the patient typed, not the phone in their hand, and "1.2 km away" without
              that context is a different claim from the one the data supports. */}
          <span className="cf-detaillabel">
            {from ? t("careFinder.distanceFromArea", { area: from })
                  : t("careFinder.distanceFromYou")}:{" "}
          </span>
          {distanceText(f.distance_meters)}
        </span>
      </p>
      {typeof f.rating === "number" && (
        <p className="cf-detailrow">
          <span className="cf-detailicon" aria-hidden="true">⭐</span>
          <span>
            {t("careFinder.rating", { rating: f.rating.toFixed(1) })}
            {typeof f.review_count === "number" && (
              <span className="cb-hint"> · {t("careFinder.reviews", { count: f.review_count })}</span>
            )}
          </span>
        </p>
      )}
      <p className="cf-detailrow">
        <span className="cf-detailicon" aria-hidden="true">🕐</span>
        {/* Never colour alone: the word is always written out. */}
        <span className={f.open_now === true ? "cf-open" : f.open_now === false ? "cf-shut" : ""}>
          {f.open_now === true ? t("careFinder.openNow")
            : f.open_now === false ? t("careFinder.closed")
              : t("careFinder.hoursUnknown")}
        </span>
      </p>
      {f.phone && (
        <p className="cf-detailrow">
          <span className="cf-detailicon" aria-hidden="true">☎️</span>
          <span>
            <span className="cf-detaillabel">{t("careFinder.phone")}: </span>
            <a href={telHref(f.phone)}>{f.phone}</a>
          </span>
        </p>
      )}
      {f.website && (
        <p className="cf-detailrow">
          <span className="cf-detailicon" aria-hidden="true">🌐</span>
          <span>
            <span className="cf-detaillabel">{t("careFinder.website")}: </span>
            {/* The host, not the word "Website" twice — a person deciding whether to
                follow a link on a health page should be able to see where it goes. */}
            <a href={f.website} target="_blank" rel="noopener noreferrer nofollow">
              {hostOf(f.website)}
            </a>
          </span>
        </p>
      )}
      <a
        className="cf-directions"
        href={directionsUrl(f)}
        target="_blank"
        rel="noopener noreferrer"
      >
        <span aria-hidden="true">🧭</span> {t("careFinder.directions")}
      </a>
      <p className="cb-note cf-approx">{t("careFinder.approx")} {t("careFinder.directionsHint")}</p>
    </div>
  );
}

/** One facility in the list. Selected -> expanded, and the map is centred on it. */
function FacilityCard({
  f, index, selected, onSelect, cardId, from,
}: {
  f: Facility; index: number; selected: boolean;
  onSelect: () => void; cardId: string; from: string | null;
}) {
  const { t } = useCareBridge();
  const distanceText = useDistanceText();
  return (
    <li className={`cf-card${selected ? " on" : ""}`} id={cardId}>
      {/* The whole summary is one button: a big, obvious target on a phone, and one tab
          stop per facility rather than five. The details it reveals are below it, not
          inside it, so the links in them stay independently reachable. */}
      <button
        type="button"
        className="cf-cardhead"
        onClick={onSelect}
        aria-expanded={selected}
        aria-controls={`${cardId}-detail`}
      >
        <span className="cf-cardnum" aria-hidden="true">{index + 1}</span>
        <span className="cf-cardmain">
          <span className="cf-cardname">{f.name}</span>
          <span className="cf-cardmeta">
            {distanceText(f.distance_meters)}
            {typeof f.rating === "number" && (
              <> · <span aria-hidden="true">⭐</span> {f.rating.toFixed(1)}</>
            )}
            {f.open_now === true && <> · <span className="cf-open">{t("careFinder.openNow")}</span></>}
            {f.open_now === false && <> · <span className="cf-shut">{t("careFinder.closed")}</span></>}
          </span>
          <Badges f={f} />
        </span>
        <span className="cf-cardmark" aria-hidden="true">{selected ? "▾" : "▸"}</span>
      </button>
      <div id={`${cardId}-detail`} hidden={!selected}>
        {selected && <FacilityDetails f={f} from={from} />}
      </div>
    </li>
  );
}

export default function CareFinder({ r }: { r: AnalyzeResult }) {
  const { t, lang } = useCareBridge();
  const distanceText = useDistanceText();

  const [phase, setPhase] = useState<Phase>("idle");
  const [code, setCode] = useState<string | undefined>();
  const [data, setData] = useState<NearbyResponse | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [view, setView] = useState<View>("list");
  const [radius, setRadius] = useState<number>(DEFAULT_RADIUS_M);
  const [manualOpen, setManualOpen] = useState(false);
  const [area, setArea] = useState("");
  // What the API says about its own ability to search, asked once. `undefined` is "not
  // asked yet"; `null` is "the probe failed", which is treated as "assume it works".
  const [status, setStatus] = useState<CareFinderStatus | null | undefined>(undefined);
  // The last centre we searched from, so a radius change does not ask for the position
  // (and the permission prompt) a second time.
  const origin = useRef<{ position?: Position; area?: string } | null>(null);
  // The in-flight lock. A ref because it has to be correct DURING the click handler,
  // before React has re-rendered — that is the double-tap race.
  const inFlight = useRef(false);
  const resultsRef = useRef<HTMLDivElement | null>(null);

  const { key: priorityKey, prominent } = useMemo(() => priorityFor(r), [r]);
  const busy = phase === "locating" || phase === "searching";

  // Ask BEFORE offering. Without this the section renders a button that cannot succeed:
  // the patient presses it, sits through a spinner, and is told something vague — when
  // the server knew the answer before the page finished loading. This costs one cheap
  // request and no Google call.
  useEffect(() => {
    let live = true;
    getCareFinderStatus().then((s) => { if (live) setStatus(s); });
    return () => { live = false; };
  }, []);

  // A search is impossible, and the server said so. Not the same as "Google is down".
  const unavailable = status ? !status.configured || !status.enabled : false;

  const run = useCallback(async (
    from: { position?: Position; area?: string }, metres: number | undefined,
  ) => {
    if (inFlight.current) return;
    inFlight.current = true;
    origin.current = from;
    setPhase("searching");
    setCode(undefined);
    try {
      const res = await findNearby({
        position: from.position, area: from.area, radiusM: metres, language: lang,
      });
      if (res.ok) {
        setData(res);
        setRadius(res.radius_m);
        // A new search invalidates the old selection: the facility may not be in it.
        setSelectedId(res.results[0]?.place_id ?? null);
        setPhase("results");
      } else {
        setCode(res.code);
        setPhase("error");
      }
    } finally {
      inFlight.current = false;
    }
  }, [lang]);

  /** The only place a location is ever requested, and only from a click. */
  const findWithDevice = useCallback(async () => {
    if (inFlight.current) return;
    setPhase("locating");
    setCode(undefined);
    const position = await getPosition();
    if (!isPosition(position)) {
      setCode(position.code);
      setPhase("error");
      // A device that cannot give a position is the case the manual search exists for,
      // so it is opened rather than offered.
      setManualOpen(true);
      return;
    }
    await run({ position }, radius);
  }, [radius, run]);

  const searchArea = useCallback(async (e?: React.FormEvent) => {
    e?.preventDefault();
    const q = area.trim();
    if (q.length < 2) return;
    // No radius on purpose. A city is not a point: the server sizes the first search to
    // the place Google resolved, so "Hyderabad" searches a city rather than 5 km around
    // a centroid. The radius buttons below the results then pin it explicitly.
    await run({ area: q }, undefined);
  }, [area, run]);

  const changeRadius = useCallback(async (metres: number) => {
    setRadius(metres);
    if (origin.current) await run(origin.current, metres);
  }, [run]);

  /** Card -> map and map -> card. One setter, so they cannot disagree. */
  const select = useCallback((placeId: string) => {
    setSelectedId(placeId);
  }, []);

  useEffect(() => {
    if (phase !== "results") return;
    scrollIntoView(resultsRef.current);
  }, [phase]);

  // A marker tap on a phone happens in the Map tab, where the card is off-screen. Moving
  // focus would fight the map; scrolling the card into view is enough on desktop, where
  // both panes are visible at once.
  useEffect(() => {
    if (!selectedId || view !== "list") return;
    const card = document.getElementById(`cf-card-${selectedId}`);
    revealInList(card);
    scrollIntoView(card);
  }, [selectedId, view]);

  const results = data?.results ?? [];
  // Null when the origin is the device. Non-null names the place the patient typed, and
  // every distance on screen is then labelled as measured from there.
  const distanceOrigin = data?.center_source === "area"
    ? (data.area_name || data.area_label || null) : null;
  const selected = results.find((f) => f.place_id === selectedId) ?? null;
  const configProblem = phase === "error" && isConfigurationProblem(code);
  const locationProblem = phase === "error" && isLocationProblem(code);
  const hintKey = phase === "error" ? errorHintKey(code) : null;

  const markerLabel = useCallback((f: Facility, i: number) => t("careFinder.markerLabel", {
    name: `${i + 1}. ${f.name}`, distance: distanceText(f.distance_meters),
  }), [t, distanceText]);

  const mapLabels = useMemo(() => ({
    mapLabel: t("careFinder.mapLabel"),
    yourLocation: t("careFinder.yourLocation"),
    unavailable: t("careFinder.mapUnavailable"),
    markerLabel,
  }), [t, markerLabel]);

  return (
    <section
      className={`cb-section cf${prominent ? " prominent" : ""}`}
      aria-labelledby="cf-h"
    >
      <div className="eyebrow"><span aria-hidden="true">🧭</span> {t("careFinder.eyebrow")}</div>
      <h3 id="cf-h" className="cb-h">{t("careFinder.continueTitle")}</h3>
      <p className="cb-lede">{t("careFinder.continueBody")}</p>

      <div className="cf-head">
        <span className="cf-headicon" aria-hidden="true">📍</span>
        <div className="cf-headtext">
          <h4>{t("careFinder.title")}</h4>
          {/* Result-aware wording. It never restates the grade — that is above. */}
          <p>{t(priorityKey)}</p>
        </div>
      </div>

      {/* The server cannot search, and said so before we offered. No dead button, and
          the reason is named rather than dressed up as a passing outage. `reason` names
          the missing VARIABLE and never its value — it is the same string /health has
          always published. The whole block disappears the moment the API is configured. */}
      {phase !== "results" && unavailable && (
        <div className="cf-unavailable" role="note">
          <p className="cf-unavailablemsg">
            <span aria-hidden="true">🛠</span> {t("careFinder.errors.notSetUp")}
          </p>
          <p className="cb-note">{t("careFinder.errors.notSetUpHint")}</p>
          {status?.reason && (
            <p className="cf-setup mono">
              <span className="cf-setuptag">{t("careFinder.setupLabel")}</span>
              {status.reason}
            </p>
          )}
        </div>
      )}

      {phase !== "results" && !unavailable && (
        <div className="cf-start">
          <button
            type="button"
            className="cf-cta"
            onClick={findWithDevice}
            disabled={busy || configProblem}
            aria-busy={busy}
            aria-describedby="cf-status"
          >
            {phase === "locating" ? (
              <><span className="spin" aria-hidden="true" /> {t("careFinder.gettingLocation")}</>
            ) : phase === "searching" ? (
              <><span className="spin" aria-hidden="true" /> {t("careFinder.searching")}</>
            ) : phase === "error" && !configProblem ? (
              <><span aria-hidden="true">↻</span> {t("careFinder.retry")}</>
            ) : (
              <><span aria-hidden="true">📍</span> {t("careFinder.find")}</>
            )}
          </button>

        </div>
      )}

      {/* ONE live region for the whole feature, rendered in every phase.
          It has to outlive the button: when the results arrive the button is replaced,
          and a live region that is removed at that moment announces nothing at all —
          a screen-reader user would simply lose the thread. So it stays, and says how
          many facilities were found. */}
      <p id="cf-status" className="cf-status" role="status" aria-live="polite">
        {phase === "locating" && t("careFinder.gettingLocation")}
        {phase === "searching" && t("careFinder.searching")}
        {phase === "error" && (
          <span className="cf-error">
            <span aria-hidden="true">⚠</span> {t(errorKey(code))}
            {hintKey && <> {t(hintKey)}</>}
            {/* The exact cause, for whoever has to fix it. A patient cannot act on
                "api_disabled", but nobody can act on silence. */}
            {configProblem && code && <span className="cf-code mono"> ({code})</span>}
          </span>
        )}
        {phase === "idle" && (
          <span className="cf-privacy">
            <span aria-hidden="true">🔒</span> {t("careFinder.privacyNote")}
          </span>
        )}
        {phase === "results" && (
          <span className="cf-sronly">
            {results.length === 0
              ? t("careFinder.emptyTitle")
              : `${t("careFinder.foundCount", { count: results.length })} · ${t("careFinder.selectHint")}`}
          </span>
        )}
      </p>

      {/* The manual path. Always reachable, opened automatically when the device could
          not give a position — which in a village health centre is a normal Tuesday. */}
      {phase !== "results" && !unavailable && (
        <details className="cf-manual" open={manualOpen}
                 onToggle={(e) => setManualOpen((e.target as HTMLDetailsElement).open)}>
          <summary>{t("careFinder.manualTitle")}</summary>
          <form className="cf-manualform" onSubmit={searchArea}>
            <label className="cf-manuallabel" htmlFor="cf-area">
              {t("careFinder.manualHint")}
            </label>
            <div className="cf-manualrow">
              <input
                id="cf-area"
                type="text"
                value={area}
                onChange={(e) => setArea(e.target.value)}
                placeholder={t("careFinder.manualPlaceholder")}
                autoComplete="address-level2"
                maxLength={120}
              />
              <button type="submit" className="ghost" disabled={busy || area.trim().length < 2}>
                {t("careFinder.manualSubmit")}
              </button>
            </div>
          </form>
        </details>
      )}

      {phase === "results" && data && (
        <div className="cf-results" ref={resultsRef}>
          <div className="cf-resulthead">
            <div>
              <h4 className="cf-resulttitle">{t("careFinder.resultsTitle")}</h4>
              <p className="cb-hint">
                {t("careFinder.foundCount", { count: data.count })} ·{" "}
                {t("careFinder.within", { km: radiusKm(data.radius_m) })}
                {data.area_label && <> · {t("careFinder.areaShown", { area: data.area_label })}</>}
              </p>
            </div>
            {/* Map / List. A phone cannot show both well, so it shows one at a time —
                and the list is the default, because it is the view that always works. */}
            {/* Toggle buttons rather than an ARIA tablist: on a wide screen both panes
                are shown at once and this switch is hidden, so a tablist would be
                describing a relationship that is not true there. */}
            <div className="cf-viewtabs" role="group" aria-label={t("careFinder.resultsTitle")}>
              {(["list", "map"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  aria-pressed={view === v}
                  aria-controls={`cf-pane-${v}`}
                  className={`cf-viewtab${view === v ? " on" : ""}`}
                  onClick={() => setView(v)}
                >
                  <span aria-hidden="true">{v === "map" ? "🗺️" : "📋"}</span>{" "}
                  {t(v === "map" ? "careFinder.view.map" : "careFinder.view.list")}
                </button>
              ))}
            </div>
          </div>

          {results.length === 0 ? (
            <div className="cf-empty">
              <h4>{t("careFinder.emptyTitle")}</h4>
              <p>{t("careFinder.emptyBody", { km: radiusKm(data.radius_m) })}</p>
            </div>
          ) : (
            <div className="cf-split" data-view={view}>
              <div
                className="cf-pane cf-listpane"
                id="cf-pane-list"
                role="region"
                aria-label={t("careFinder.resultsTitle")}
              >
                <p className="cb-hint cf-selecthint">{t("careFinder.selectHint")}</p>
                <ul className="cf-list">
                  {results.map((f, i) => (
                    <FacilityCard
                      key={f.place_id}
                      f={f}
                      index={i}
                      cardId={`cf-card-${f.place_id}`}
                      selected={f.place_id === selectedId}
                      onSelect={() => select(f.place_id)}
                      from={distanceOrigin}
                    />
                  ))}
                </ul>
              </div>

              <div
                className="cf-pane cf-mappane"
                id="cf-pane-map"
                role="region"
                aria-label={t("careFinder.mapLabel")}
              >
                <CareFinderMap
                  center={data.center}
                  facilities={results}
                  selectedId={selectedId}
                  onSelect={select}
                  labels={mapLabels}
                />
                <p className="cf-youlegend">
                  <span className="cf-youchip" aria-hidden="true" />
                  {t("careFinder.yourLocation")}
                  <span className="cb-hint"> · {t("careFinder.yourLocationHint")}</span>
                </p>
                {/* The map's own detail card. Shown only where the list is not on screen
                    at the same time — on a wide screen the selected card is already
                    expanded a few centimetres to the left. */}
                {selected && (
                  <div className="cf-mapdetail">
                    <h5>{selected.name}</h5>
                    <FacilityDetails f={selected} compact from={distanceOrigin} />
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Rural expansion. Offered whatever the outcome, because "five results, all
              30 minutes away" is as good a reason to widen the search as none at all. */}
          <div className="cf-radiusrow" role="group" aria-label={t("careFinder.resultsTitle")}>
            {RADIUS_STEPS.map((metres) => (
              <button
                key={metres}
                type="button"
                className={`cf-radius${radius === metres ? " on" : ""}`}
                aria-pressed={radius === metres}
                disabled={busy}
                onClick={() => changeRadius(metres)}
              >
                {t("careFinder.expand", { km: radiusKm(metres) })}
              </button>
            ))}
            <button type="button" className="cf-restart" onClick={() => {
              setPhase("idle"); setData(null); setSelectedId(null);
              setCode(undefined); origin.current = null;
            }}>
              {t("careFinder.startOver")}
            </button>
          </div>

          <SpeakButton
            id="care-finder"
            parts={[t("careFinder.resultsTitle"), t("careFinder.voiceIntro")]}
          />
        </div>
      )}

      {/* The privacy sentence is on screen at every phase, and exactly once: under the
          button before a location is asked for, and here once results are showing. */}
      <p className="cb-note cf-foot">
        {phase === "results" && (
          <><span aria-hidden="true">🔒</span> {t("careFinder.privacyNote")}{" "}</>
        )}
        {t("careFinder.notEndorsement")}
      </p>
      {/* Google's terms require attribution wherever Places data is displayed. */}
      <p className="cb-note cf-attrib">{t("careFinder.attribution")}</p>

      <details className="cb-why">
        <summary>{t("careFinder.whyLabel")}</summary>
        <p>{t("careFinder.whyBody")}</p>
        <p>{t("careFinder.privacyDetail")}</p>
        <p>{t("careFinder.badgeNote")}</p>
      </details>
    </section>
  );
}
