"use client";
/**
 * Smart Care Finder — the interactive map.
 *
 * READ THIS BEFORE EDITING. **The map is never the only way to reach a facility.** Every
 * fact drawn here — name, position, distance, open/closed — is also rendered as text in
 * the list beside it, which works without JavaScript tiles, without a pointer and with a
 * screen reader. A person who cannot use a map loses nothing but the picture.
 *
 * Why Leaflet and OpenStreetMap rather than the Google Maps JavaScript API:
 *
 *   * The FACILITY DATA is Google's, fetched server-side with the server-side key (see
 *     src/carefinder/). Drawing it needs a map, not a second Google product.
 *   * A browser map key is a key that ships to every visitor. Google's own guidance is
 *     to restrict it by referrer and by API, which is real work to get right and easy to
 *     get wrong; not having one to leak is stronger than restricting one.
 *   * Tiles from a non-Google source keep this page looking like CareBridge rather than
 *     like an embedded Google Maps demo, which is what the design asks for.
 *
 * Swapping in the Google Maps JS API later is a change to this ONE file: everything
 * outside it talks to the map through `center`, `facilities`, `selectedId` and
 * `onSelect`.
 *
 * Leaflet is loaded with a dynamic import inside an effect because it touches `window`
 * at module scope, which would break the server render.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import type * as L from "leaflet";
import "leaflet/dist/leaflet.css";
import type { Facility } from "@/lib/carefinder";

type Props = {
  center: { latitude: number; longitude: number };
  facilities: Facility[];
  selectedId: string | null;
  onSelect: (placeId: string) => void;
  /** Already-translated strings. This component holds no copy of its own. */
  labels: {
    mapLabel: string;
    yourLocation: string;
    unavailable: string;
    markerLabel: (f: Facility, index: number) => string;
  };
};

/** Our own marker, as HTML. Leaflet's default icon is a bundled PNG that breaks under
 *  bundlers, and a div we style is the only way the pins match the CareBridge palette. */
function facilityIcon(leaflet: typeof L, index: number, selected: boolean) {
  return leaflet.divIcon({
    className: "cf-pinwrap",
    html: `<span class="cf-pin${selected ? " on" : ""}"><span class="cf-pinnum">${index + 1}</span></span>`,
    iconSize: [30, 38],
    iconAnchor: [15, 36],
  });
}

/** One framing for every fit, so the hidden-then-shown path lands identically. */
const FIT = { padding: [36, 36] as [number, number], maxZoom: 15 };

function youIcon(leaflet: typeof L) {
  return leaflet.divIcon({
    className: "cf-youwrap",
    html: '<span class="cf-you"><span class="cf-youdot"></span></span>',
    iconSize: [22, 22],
    iconAnchor: [11, 11],
  });
}

export default function CareFinderMap({
  center, facilities, selectedId, onSelect, labels,
}: Props) {
  const holder = useRef<HTMLDivElement | null>(null);
  const map = useRef<L.Map | null>(null);
  const leafletRef = useRef<typeof L | null>(null);
  const markers = useRef<Map<string, L.Marker>>(new Map());
  // The bounds that show everything, kept so they can be re-applied. See `remeasure`.
  const framing = useRef<L.LatLngBounds | null>(null);
  const lastSize = useRef<{ w: number; h: number }>({ w: 0, h: 0 });
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  // The click handler has to see the CURRENT onSelect without the map being torn down
  // and rebuilt every time the parent re-renders.
  const select = useRef(onSelect);
  select.current = onSelect;

  // ---------------------------------------------------------------- create once
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const leaflet = (await import("leaflet")).default ?? (await import("leaflet"));
        if (cancelled || !holder.current || map.current) return;
        leafletRef.current = leaflet as typeof L;
        const instance = leaflet.map(holder.current, {
          center: [center.latitude, center.longitude],
          zoom: 13,
          // The page scrolls past this map on a phone. Scroll-wheel zoom would hijack
          // that; a two-finger gesture and the +/- buttons still work.
          scrollWheelZoom: false,
          attributionControl: true,
        });
        leaflet.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          maxZoom: 19,
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        }).addTo(instance);
        map.current = instance;
        if (!cancelled) setReady(true);
      } catch {
        // No tiles, no Leaflet, no network: the list beside this still has everything.
        if (!cancelled) setFailed(true);
      }
    })();
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
      markers.current.clear();
    };
    // Deliberately created once. `center` changes are applied by the effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --------------------------------------------------------- the person's own pin
  useEffect(() => {
    const leaflet = leafletRef.current;
    if (!ready || !leaflet || !map.current) return;
    const you = leaflet.marker([center.latitude, center.longitude], {
      icon: youIcon(leaflet),
      // Conceptual, exactly as the brief asks: "Your location". The coordinates are
      // never written out as text anywhere on this page.
      title: labels.yourLocation,
      alt: labels.yourLocation,
      keyboard: false,
      interactive: false,
      zIndexOffset: -100,
    }).addTo(map.current);
    map.current.setView([center.latitude, center.longitude], map.current.getZoom());
    return () => { you.remove(); };
  }, [ready, center.latitude, center.longitude, labels.yourLocation]);

  // ----------------------------------------------------------- facility markers
  useEffect(() => {
    const leaflet = leafletRef.current;
    const instance = map.current;
    if (!ready || !leaflet || !instance) return;

    markers.current.forEach((m) => m.remove());
    markers.current.clear();

    facilities.forEach((f, i) => {
      const marker = leaflet.marker([f.latitude, f.longitude], {
        icon: facilityIcon(leaflet, i, f.place_id === selectedId),
        title: f.name,
        alt: labels.markerLabel(f, i),
        // Leaflet gives a keyboard-focusable marker that fires `click` on Enter, which
        // is what makes the pins reachable without a mouse.
        keyboard: true,
      }).addTo(instance);
      marker.on("click", () => select.current(f.place_id));
      const el = marker.getElement();
      if (el) {
        el.setAttribute("role", "button");
        el.setAttribute("aria-label", labels.markerLabel(f, i));
        el.setAttribute("aria-pressed", String(f.place_id === selectedId));
        // Leaflet's own `keyboard: true` makes the marker focusable, and it does fire a
        // click for Enter — but only through an internal handler, it does not handle
        // Space, and an element we have given `role="button"` has to answer to both.
        // Owning the key handling here is one line and does not depend on which Leaflet
        // version is installed.
        el.addEventListener("keydown", (ev) => {
          const key = (ev as KeyboardEvent).key;
          if (key !== "Enter" && key !== " " && key !== "Spacebar") return;
          ev.preventDefault();
          ev.stopPropagation();
          select.current(f.place_id);
        });
      }
      markers.current.set(f.place_id, marker);
    });

    if (facilities.length > 0) {
      framing.current = leaflet.latLngBounds([
        [center.latitude, center.longitude],
        ...facilities.map((f) => [f.latitude, f.longitude] as [number, number]),
      ]);
      instance.fitBounds(framing.current, FIT);
    }
    // `selectedId` is handled by the effect below so that selecting a facility does not
    // rebuild every marker and refit the map under the reader.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, facilities, center.latitude, center.longitude]);

  // ------------------------------------------------ list -> map synchronisation
  useEffect(() => {
    const leaflet = leafletRef.current;
    const instance = map.current;
    if (!ready || !leaflet || !instance) return;
    markers.current.forEach((marker, id) => {
      const index = facilities.findIndex((f) => f.place_id === id);
      if (index < 0) return;
      const on = id === selectedId;
      marker.setIcon(facilityIcon(leaflet, index, on));
      marker.setZIndexOffset(on ? 1000 : 0);
      marker.getElement()?.setAttribute("aria-pressed", String(on));
    });
    const chosen = facilities.find((f) => f.place_id === selectedId);
    if (chosen) {
      // Centre on the chosen facility without zooming past what the person was looking
      // at. `panTo` keeps the surrounding context, which a hard `setView` throws away.
      instance.panTo([chosen.latitude, chosen.longitude], { animate: true });
    }
  }, [ready, selectedId, facilities]);

  // Keep Leaflet honest about its own size: on a phone this map lives in a tab that
  // starts hidden, and a map laid out while `display:none` renders as a grey box for
  // ever afterwards. The ResizeObserver catches the moment the tab is shown; the window
  // listener catches an orientation change. Both are guarded because jsdom has neither.
  const remeasure = useCallback(() => {
    const instance = map.current;
    const el = holder.current;
    if (!instance || !el) return;
    const w = el.clientWidth, h = el.clientHeight;
    const wasHidden = lastSize.current.w === 0 || lastSize.current.h === 0;
    lastSize.current = { w, h };
    if (w === 0 || h === 0) return;
    instance.invalidateSize();
    // `invalidateSize` keeps the centre and the zoom. That is right for an orientation
    // change and WRONG for the moment a hidden tab is first shown: on a phone the map is
    // built inside `display:none`, so the fitBounds that framed every facility ran
    // against a 0x0 container and resolved to maximum zoom on a single street. Re-frame
    // once, when the pane goes from hidden to visible, and never after — re-fitting on
    // every resize would throw away a pan the person had just made.
    if (wasHidden && framing.current) instance.fitBounds(framing.current, FIT);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const t = setTimeout(remeasure, 60);
    if (typeof window !== "undefined") window.addEventListener("resize", remeasure);
    let observer: ResizeObserver | undefined;
    if (typeof ResizeObserver !== "undefined" && holder.current) {
      observer = new ResizeObserver(remeasure);
      observer.observe(holder.current);
    }
    return () => {
      clearTimeout(t);
      observer?.disconnect();
      if (typeof window !== "undefined") window.removeEventListener("resize", remeasure);
    };
  }, [ready, remeasure]);

  if (failed) {
    return <p className="cb-note cf-mapfail" role="note">{labels.unavailable}</p>;
  }

  return (
    <div
      ref={holder}
      className="cf-map"
      // A pannable, zoomable widget. `application` tells a screen reader to pass arrow
      // keys through to it rather than treating them as document navigation.
      role="application"
      aria-label={labels.mapLabel}
    />
  );
}
