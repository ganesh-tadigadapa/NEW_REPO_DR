"use client";
/**
 * CareBridge on the landing page.
 *
 * A screening service whose results only exist in English is not usable by most of the
 * people it is for. That belongs on the front page next to the model architecture, not
 * behind a settings icon — so this band states it plainly and, being itself translated,
 * demonstrates it at the same time.
 */
import Link from "next/link";
import { LANGUAGES } from "@/lib/i18n";
import { useCareBridge } from "./CareBridgeProvider";

export default function CareBridgeBand() {
  const { t, lang, setLanguage } = useCareBridge();
  return (
    <section className="band cb-band" aria-labelledby="cb-band-h">
      <h3 id="cb-band-h">
        <span aria-hidden="true">🌍</span> {t("common.appName")} — {t("common.appTagline")}
      </h3>
      <p className="intro">{t("journey.intro")}</p>

      <div className="cb-bandrow">
        <div className="cb-bandlangs" role="radiogroup" aria-label={t("a11y.chooseLanguage")}>
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              type="button"
              role="radio"
              aria-checked={l.code === lang}
              lang={l.locale}
              className={`cb-bandlang${l.code === lang ? " on" : ""}`}
              onClick={() => setLanguage(l.code)}
            >
              <span className="cb-choicenative">{l.nativeName}</span>
              <span className="cb-choiceen">{l.englishName}</span>
            </button>
          ))}
        </div>
        <ul className="cb-bandlist">
          <li><span aria-hidden="true">🔊</span> {t("onboarding.voiceNote")}</li>
          <li><span aria-hidden="true">💬</span> {t("common.simpleHint")}</li>
          <li><span aria-hidden="true">🩺</span> {t("common.clinicalHint")}</li>
        </ul>
      </div>

      <div className="ctarow">
        <Link href="/carebridge" className="cta line">
          {t("common.appName")} · {t("journey.title")}
        </Link>
      </div>
      <p className="cb-note">{t("common.curatedNote")}</p>
    </section>
  );
}
