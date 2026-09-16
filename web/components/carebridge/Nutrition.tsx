"use client";
/**
 * Food and lifestyle support.
 *
 * Two things make this a CareBridge module rather than a page with a list on it:
 *
 *   1. It has NO language control of its own. It calls `useCareBridge()` and is already
 *      in Telugu because the result above it is. That is the whole point of the layer.
 *   2. It is only ever rendered for a graded photograph. General diabetes guidance
 *      attached to an image the system refused to read would be advice built on nothing.
 *
 * The "make this fit your food" choice changes which examples are listed. It is held in
 * component state and never written to storage — what a person eats is not a UI
 * preference, and CareBridge stores only UI preferences.
 */
import { useState } from "react";
import { useCareBridge } from "./CareBridgeProvider";
import SpeakButton from "./SpeakButton";
import WhyThis from "./WhyThis";

type Diet = "mixed" | "vegetarian" | "millet";

const FOCUS_KEY = {
  mixed: "nutrition.focusMixed",
  vegetarian: "nutrition.focusVegetarian",
  millet: "nutrition.focusMillet",
} as const;

const DIET_LABEL = {
  mixed: "nutrition.dietMixed",
  vegetarian: "nutrition.dietVegetarian",
  millet: "nutrition.dietMillet",
} as const;

export default function Nutrition() {
  const { t, tList } = useCareBridge();
  const [diet, setDiet] = useState<Diet>("mixed");

  const focus = tList(FOCUS_KEY[diet]);
  const limit = tList("nutrition.limitItems");

  return (
    <section className="card cb-section" aria-labelledby="cb-nutrition-h">
      <div className="eyebrow">
        <span aria-hidden="true">🥗</span> {t("actions.lifestyleTitle")}
      </div>
      <h3 id="cb-nutrition-h" className="cb-h">{t("nutrition.title")}</h3>
      <p className="cb-lede">{t("nutrition.intro")}</p>

      <SpeakButton
        id="nutrition"
        parts={[t("nutrition.title"), t("nutrition.intro"),
                t("nutrition.focusTitle"), ...focus,
                t("nutrition.limitTitle"), ...limit,
                t("nutrition.activityTitle"), t("nutrition.activityBody")]}
      />

      <div className="cb-personalize">
        <div className="cb-personalizehead">
          <span className="cb-label">{t("nutrition.personalizeTitle")}</span>
          <span className="cb-hint">{t("nutrition.personalizeHint")}</span>
        </div>
        <div className="filterrow" role="radiogroup" aria-label={t("nutrition.personalizeTitle")}>
          {(["mixed", "vegetarian", "millet"] as const).map((d) => (
            <button
              key={d}
              type="button"
              role="radio"
              aria-checked={diet === d}
              className={`chip${diet === d ? " on" : ""}`}
              onClick={() => setDiet(d)}
            >
              {t(DIET_LABEL[d])}
            </button>
          ))}
        </div>
      </div>

      <div className="cb-foodgrid">
        <div className="cb-foodcol good">
          <h4><span aria-hidden="true">✚</span> {t("nutrition.focusTitle")}</h4>
          <ul>{focus.map((item, i) => <li key={i}>{item}</li>)}</ul>
        </div>
        <div className="cb-foodcol limit">
          <h4><span aria-hidden="true">−</span> {t("nutrition.limitTitle")}</h4>
          <ul>{limit.map((item, i) => <li key={i}>{item}</li>)}</ul>
        </div>
      </div>

      <div className="cb-tworow">
        <div className="cb-minicard">
          <h4><span aria-hidden="true">🚶</span> {t("nutrition.activityTitle")}</h4>
          <p>{t("nutrition.activityBody")}</p>
        </div>
        <div className="cb-minicard">
          <h4><span aria-hidden="true">📈</span> {t("nutrition.controlTitle")}</h4>
          <p>{t("nutrition.controlBody")}</p>
        </div>
      </div>

      <p className="cb-note">{t("nutrition.note")}</p>
      <WhyThis />
    </section>
  );
}
