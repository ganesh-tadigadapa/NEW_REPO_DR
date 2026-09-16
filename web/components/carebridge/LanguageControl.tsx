"use client";
/**
 * The global CareBridge control — one compact button in the header, on every page.
 *
 * It shows the language currently in force, so a person never has to open anything to
 * find out what they are reading, and a judge can see at a glance that the whole journey
 * is running in Telugu. Opening it exposes the three preferences and nothing else; this
 * is a language panel, not a settings screen.
 */
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { LANGUAGES } from "@/lib/i18n";
import { useCareBridge } from "./CareBridgeProvider";

export default function LanguageControl() {
  const {
    t, lang, meta, voice, level, setLanguage, setVoice, setLevel, speech,
  } = useCareBridge();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  // Close on Escape and on a click outside. Both are expected of a popover, and both
  // are what a keyboard-only user needs to get back out of it.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        rootRef.current?.querySelector<HTMLButtonElement>(".cb-trigger")?.focus();
      }
    };
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  useEffect(() => {
    if (open) panelRef.current?.querySelector<HTMLElement>("[data-first]")?.focus();
  }, [open]);

  return (
    <div className="cb-control" ref={rootRef}>
      <button
        type="button"
        className="cb-trigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={t("a11y.openLanguageMenu")}
        onClick={() => setOpen((v) => !v)}
      >
        <span aria-hidden="true">🌐</span>
        <span className="cb-triggerlang">{meta.nativeName}</span>
        {voice && <span aria-hidden="true" className="cb-triggervoice">🔊</span>}
      </button>

      {open && (
        <div
          className="cb-panel"
          role="dialog"
          aria-label={t("a11y.languageMenu")}
          ref={panelRef}
        >
          <div className="cb-panelhead">
            <span className="eyebrow">{t("common.appName")}</span>
            <button
              type="button"
              className="cb-panelclose"
              onClick={() => setOpen(false)}
              aria-label={t("common.close")}
            >
              ✕
            </button>
          </div>

          <fieldset className="cb-group">
            <legend>{t("common.yourCareLanguage")}</legend>
            <div className="cb-langlist" role="radiogroup" aria-label={t("a11y.chooseLanguage")}>
              {LANGUAGES.map((l, i) => (
                <button
                  key={l.code}
                  type="button"
                  role="radio"
                  aria-checked={l.code === lang}
                  data-first={i === 0 ? "" : undefined}
                  className={`cb-langrow${l.code === lang ? " on" : ""}`}
                  onClick={() => setLanguage(l.code)}
                  lang={l.locale}
                >
                  <span className="cb-tick" aria-hidden="true">{l.code === lang ? "✓" : ""}</span>
                  <span className="cb-langnative">{l.nativeName}</span>
                  <span className="cb-langen">{l.englishName}</span>
                </button>
              ))}
            </div>
          </fieldset>

          <fieldset className="cb-group">
            <legend>{t("common.voiceGuidance")}</legend>
            <button
              type="button"
              role="switch"
              aria-checked={voice}
              aria-label={t("a11y.voiceToggle")}
              className={`cb-switch${voice ? " on" : ""}`}
              onClick={() => setVoice(!voice)}
            >
              <span className="cb-switchtrack" aria-hidden="true"><span /></span>
              <span>{voice ? t("common.on") : t("common.off")}</span>
            </button>
            {voice && speech.supported && !speech.voiceAvailable && (
              <p className="cb-panelnote">
                {t("errors.voiceNoLanguage", { language: meta.nativeName })}
              </p>
            )}
            {voice && !speech.supported && (
              <p className="cb-panelnote">{t("errors.voiceUnsupported")}</p>
            )}
          </fieldset>

          <fieldset className="cb-group">
            <legend>{t("common.explanationLevel")}</legend>
            <div className="cb-seg" role="radiogroup" aria-label={t("a11y.explanationLevelGroup")}>
              {(["simple", "clinical"] as const).map((v) => (
                <button
                  key={v}
                  type="button"
                  role="radio"
                  aria-checked={level === v}
                  className={`cb-segbtn${level === v ? " on" : ""}`}
                  onClick={() => setLevel(v)}
                >
                  {t(v === "simple" ? "common.simple" : "common.clinical")}
                </button>
              ))}
            </div>
            <p className="cb-panelnote">
              {t(level === "simple" ? "common.simpleHint" : "common.clinicalHint")}
            </p>
          </fieldset>

          <Link href="/carebridge" className="cb-panellink" onClick={() => setOpen(false)}>
            {t("common.appName")} · {t("journey.title")}
          </Link>
        </div>
      )}
    </div>
  );
}
