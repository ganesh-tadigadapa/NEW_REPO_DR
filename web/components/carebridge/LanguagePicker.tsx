"use client";
/**
 * The first thing a patient meets: choose the language you want your result in.
 *
 * Not a <select>. A person who cannot read the interface cannot find their language
 * inside a closed dropdown — every option is visible at once, written in its own script,
 * and each is a full-width target you can hit with a thumb.
 *
 * `LanguageChoices` is the list on its own, reused by the onboarding card and by the
 * CareBridge page.
 */
import { LANGUAGES } from "@/lib/i18n";
import { useCareBridge } from "./CareBridgeProvider";

export function LanguageChoices({ onPick }: { onPick?: () => void }) {
  const { lang, setLanguage, t } = useCareBridge();
  return (
    <div className="cb-choices" role="radiogroup" aria-label={t("a11y.chooseLanguage")}>
      {LANGUAGES.map((l) => {
        const on = l.code === lang;
        return (
          <button
            key={l.code}
            type="button"
            role="radio"
            aria-checked={on}
            className={`cb-choice${on ? " on" : ""}`}
            lang={l.locale}
            onClick={() => { setLanguage(l.code); onPick?.(); }}
          >
            <span className="cb-choicenative">{l.nativeName}</span>
            <span className="cb-choiceen">{l.englishName}</span>
            <span className="cb-choicemark" aria-hidden="true">{on ? "✓" : ""}</span>
            {on && <span className="cb-sronly">{t("onboarding.selected")}</span>}
          </button>
        );
      })}
    </div>
  );
}

/**
 * The full welcome card. Shown until the person has actually chosen — after that the
 * header control is where the language lives, because nobody wants to answer the same
 * question on every page.
 */
export default function LanguageOnboarding({ compact = false }: { compact?: boolean }) {
  const { t, needsOnboarding, keepDefaultLanguage } = useCareBridge();
  if (!needsOnboarding) return null;

  return (
    <section className={`cb-welcome${compact ? " compact" : ""}`} aria-labelledby="cb-welcome-h">
      <div className="cb-welcomeinner">
        <div className="eyebrow">
          <span aria-hidden="true">🌍</span> {t("onboarding.eyebrow")}
        </div>
        <h2 id="cb-welcome-h">{t("onboarding.title")}</h2>
        <p className="cb-welcomesub">{t("onboarding.subtitle")}</p>

        <LanguageChoices />

        <div className="cb-welcomefoot">
          <span className="cb-voiceflag">
            <span aria-hidden="true">🔊</span> {t("onboarding.voiceNote")}
          </span>
          <span className="cb-welcomehint">{t("onboarding.changeLater")}</span>
          <button type="button" className="linkbtn" onClick={keepDefaultLanguage}>
            {t("onboarding.dismiss")}
          </button>
        </div>
      </div>
    </section>
  );
}
