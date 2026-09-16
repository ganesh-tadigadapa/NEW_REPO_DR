"use client";
/**
 * CareBridge — the accessibility context for the whole patient-facing app.
 *
 * One provider holds three things: the chosen language, whether voice guidance is on,
 * and whether the reader wants the simple or the clinical presentation. Every feature
 * reads them from here, so a module added next year inherits all three by calling
 * `useCareBridge()` instead of inventing its own settings.
 *
 * Speech lives here too, and on purpose: the browser has ONE speech queue, so exactly
 * one component may be speaking at a time. Holding `speakingId` centrally is what makes
 * "stop the previous playback before starting a new one" true rather than hoped for.
 *
 * This provider changes what is DRAWN. It never touches a grade, a probability, a
 * threshold or a referral decision — those arrive from the API already decided.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useRef, useState,
} from "react";
import {
  DEFAULT_LANGUAGE, languageMeta, translatorFor,
  type ExplanationLevel, type LanguageCode, type LanguageMeta, type Translator,
} from "@/lib/i18n";
import {
  DEFAULT_PREFS, loadPrefs, pickVoice, savePrefs, speechText,
  type Prefs, type VoiceLike,
} from "@/lib/carebridge";

type SpeechState = {
  /** Whether this browser exposes speech synthesis at all. */
  supported: boolean;
  /** Whether a voice exists for the CURRENT language on THIS device. */
  voiceAvailable: boolean;
  /** Id of the button currently speaking, or null. */
  speakingId: string | null;
};

type Ctx = Translator & {
  meta: LanguageMeta;
  voice: boolean;
  level: ExplanationLevel;
  /** False during the first paint, before localStorage has been read. */
  hydrated: boolean;
  /** True once we know the person has never picked a language. */
  needsOnboarding: boolean;
  setLanguage: (code: LanguageCode) => void;
  setVoice: (on: boolean) => void;
  setLevel: (level: ExplanationLevel) => void;
  /** Mark onboarding as answered without changing the language. */
  keepDefaultLanguage: () => void;
  speech: SpeechState;
  speak: (id: string, parts: (string | null | undefined)[]) => void;
  stopSpeaking: () => void;
};

const fallbackTranslator = translatorFor(DEFAULT_LANGUAGE);

const CareBridgeCtx = createContext<Ctx>({
  ...fallbackTranslator,
  meta: languageMeta(DEFAULT_LANGUAGE),
  voice: DEFAULT_PREFS.voice,
  level: DEFAULT_PREFS.level,
  hydrated: false,
  needsOnboarding: false,
  setLanguage: () => {},
  setVoice: () => {},
  setLevel: () => {},
  keepDefaultLanguage: () => {},
  speech: { supported: false, voiceAvailable: false, speakingId: null },
  speak: () => {},
  stopSpeaking: () => {},
});

export function useCareBridge() {
  return useContext(CareBridgeCtx);
}

export default function CareBridgeProvider({ children }: { children: React.ReactNode }) {
  // The first render must match the server's, so it uses the defaults. The stored
  // preference is applied in the effect below, which is also what sets `hydrated`.
  const [prefs, setPrefs] = useState<Prefs>(DEFAULT_PREFS);
  const [hydrated, setHydrated] = useState(false);
  const [voices, setVoices] = useState<VoiceLike[]>([]);
  const [speakingId, setSpeakingId] = useState<string | null>(null);
  const utteranceRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    setPrefs(loadPrefs());
    setHydrated(true);
  }, []);

  // Keep <html lang> honest: screen readers and the browser's own text handling use it.
  const meta = languageMeta(prefs.lang);
  useEffect(() => {
    if (typeof document !== "undefined") document.documentElement.lang = meta.locale;
  }, [meta.locale]);

  // Voice lists load asynchronously in most browsers, and are empty on the first call.
  useEffect(() => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    const synth = window.speechSynthesis;
    const read = () => setVoices(synth.getVoices() as unknown as VoiceLike[]);
    read();
    synth.addEventListener?.("voiceschanged", read);
    return () => synth.removeEventListener?.("voiceschanged", read);
  }, []);

  // `hydrated` gates this for the same reason it gates `prefs`: the first client render
  // has to produce the markup the server sent. Speech support is a browser-only fact, so
  // without the gate the server renders SpeakButton's "voice unavailable" note while the
  // client's very first render produces the button — a hydration mismatch on every
  // SpeakButton, which on /carebridge made React discard the server tree and throw
  // "Text content does not match server-rendered HTML" six times.
  const supported =
    hydrated &&
    typeof window !== "undefined" &&
    "speechSynthesis" in window &&
    typeof window.SpeechSynthesisUtterance === "function";

  const matchedVoice = useMemo(
    () => (supported ? pickVoice(voices, meta) : null),
    [supported, voices, meta]);

  const stopSpeaking = useCallback(() => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try { window.speechSynthesis.cancel(); } catch { /* nothing to cancel */ }
    }
    utteranceRef.current = null;
    setSpeakingId(null);
  }, []);

  const speak = useCallback((id: string, parts: (string | null | undefined)[]) => {
    if (!supported) return;
    const text = speechText(parts);
    if (!text) return;
    // One queue: whatever was playing stops before anything new starts.
    stopSpeaking();
    let u: SpeechSynthesisUtterance;
    try { u = new window.SpeechSynthesisUtterance(text); }
    catch { return; }
    u.lang = matchedVoice?.lang || meta.locale;
    if (matchedVoice) u.voice = matchedVoice as unknown as SpeechSynthesisVoice;
    // Slightly under normal pace: this is health information being read to someone who
    // may be hearing it for the first time.
    u.rate = 0.95;
    u.onend = () => setSpeakingId(null);
    u.onerror = () => setSpeakingId(null);
    utteranceRef.current = u;
    setSpeakingId(id);
    try { window.speechSynthesis.speak(u); }
    catch { setSpeakingId(null); }
  }, [supported, matchedVoice, meta.locale, stopSpeaking]);

  // Leaving the page must not leave a voice talking to an empty room.
  useEffect(() => () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      try { window.speechSynthesis.cancel(); } catch { /* already gone */ }
    }
  }, []);

  // A language change mid-sentence would finish reading in the old language.
  useEffect(() => { stopSpeaking(); }, [prefs.lang, stopSpeaking]);

  const update = useCallback((patch: Partial<Prefs>) => {
    setPrefs((prev) => {
      const next = { ...prev, ...patch };
      savePrefs(next);
      return next;
    });
  }, []);

  const value = useMemo<Ctx>(() => ({
    ...translatorFor(prefs.lang),
    meta,
    voice: prefs.voice,
    level: prefs.level,
    hydrated,
    needsOnboarding: hydrated && !prefs.chosen,
    setLanguage: (code) => update({ lang: code, chosen: true }),
    setVoice: (on) => update({ voice: on }),
    setLevel: (level) => update({ level }),
    keepDefaultLanguage: () => update({ chosen: true }),
    speech: {
      supported,
      voiceAvailable: Boolean(matchedVoice),
      speakingId,
    },
    speak,
    stopSpeaking,
  }), [prefs, meta, hydrated, update, supported, matchedVoice, speakingId, speak, stopSpeaking]);

  return <CareBridgeCtx.Provider value={value}>{children}</CareBridgeCtx.Provider>;
}
