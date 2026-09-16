/**
 * CareBridge preferences and voice selection.
 *
 * Deliberately pure where it can be: parsing, validation and voice matching are plain
 * functions so they can be reasoned about (and tested) without a browser.
 *
 * STORAGE POLICY. Exactly three values are persisted — the chosen language, whether
 * voice guidance is on, and whether the reader wants the simple or the clinical view.
 * All three are interface preferences. No grade, no image, no scan id, no patient
 * reference and nothing else from a result ever goes into localStorage. The session
 * token in lib/auth.ts remains the only other thing this app stores, and CareBridge
 * does not read or touch it: changing your language does not sign you out.
 */
import { DEFAULT_LANGUAGE, isLanguageCode } from "@/lib/i18n";
import type { ExplanationLevel, LanguageCode, LanguageMeta } from "@/lib/i18n";

export const PREFS_KEY = "carebridge_prefs";

export type Prefs = {
  lang: LanguageCode;
  voice: boolean;
  level: ExplanationLevel;
  /**
   * True once the person has actively picked a language, as opposed to being given the
   * English default. This is what decides whether the onboarding card is shown.
   */
  chosen: boolean;
};

export const DEFAULT_PREFS: Prefs = {
  lang: DEFAULT_LANGUAGE, voice: true, level: "simple", chosen: false,
};

function isLevel(v: unknown): v is ExplanationLevel {
  return v === "simple" || v === "clinical";
}

/**
 * Tolerant parse. Anything unexpected — corrupt JSON, an old shape, a language that was
 * removed, a hand-edited value — falls back to the default for that field rather than
 * throwing. A broken preference must never be able to break the result page.
 */
export function parsePrefs(raw: string | null | undefined): Prefs {
  if (!raw) return { ...DEFAULT_PREFS };
  let data: unknown;
  try { data = JSON.parse(raw); } catch { return { ...DEFAULT_PREFS }; }
  if (!data || typeof data !== "object" || Array.isArray(data)) return { ...DEFAULT_PREFS };
  const o = data as Record<string, unknown>;
  return {
    lang: isLanguageCode(o.lang) ? o.lang : DEFAULT_PREFS.lang,
    voice: typeof o.voice === "boolean" ? o.voice : DEFAULT_PREFS.voice,
    level: isLevel(o.level) ? o.level : DEFAULT_PREFS.level,
    chosen: o.chosen === true,
  };
}

export function serializePrefs(p: Prefs): string {
  return JSON.stringify({ lang: p.lang, voice: p.voice, level: p.level, chosen: p.chosen });
}

/** Read from localStorage. Safe on the server and in private browsing. */
export function loadPrefs(): Prefs {
  if (typeof window === "undefined") return { ...DEFAULT_PREFS };
  try { return parsePrefs(window.localStorage.getItem(PREFS_KEY)); }
  catch { return { ...DEFAULT_PREFS }; }
}

export function savePrefs(p: Prefs): void {
  if (typeof window === "undefined") return;
  try { window.localStorage.setItem(PREFS_KEY, serializePrefs(p)); }
  catch { /* private browsing — the choice then lasts for this tab only */ }
}

// --------------------------------------------------------------- voice selection
/** The part of SpeechSynthesisVoice we actually use. Keeps this testable. */
export type VoiceLike = { lang: string; name: string; default?: boolean };

function norm(tag: string): string {
  return tag.replace(/_/g, "-").toLowerCase();
}

/**
 * Best available voice for a language, or null.
 *
 * Null is a real answer, not a failure: a device with no Telugu voice must show the
 * Telugu text and say so, never read Telugu aloud with an English voice. Matching is
 * exact tag first (te-IN), then the base subtag (te-*), in the order the language
 * registry prefers.
 */
export function pickVoice(voices: VoiceLike[], meta: LanguageMeta): VoiceLike | null {
  if (!voices || voices.length === 0) return null;
  for (const wanted of meta.speechLocales) {
    const exact = voices.find((v) => norm(v.lang) === norm(wanted));
    if (exact) return exact;
  }
  for (const wanted of meta.speechLocales) {
    const base = norm(wanted).split("-")[0];
    const loose = voices.find((v) => norm(v.lang).split("-")[0] === base);
    if (loose) return loose;
  }
  return null;
}

/**
 * Join the parts of a spoken passage into something a synthesiser reads sensibly.
 * Blank parts are dropped, and each part is terminated so the voice pauses between them.
 */
export function speechText(parts: (string | null | undefined)[]): string {
  return parts
    .map((p) => (p ?? "").trim())
    .filter((p) => p !== "")
    .map((p) => (/[.!?।]$/.test(p) ? p : `${p}.`))
    .join(" ");
}
