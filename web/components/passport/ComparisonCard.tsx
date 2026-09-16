"use client";
/**
 * SCREENING COMPARISON — previous, current, change.
 *
 * READ THIS BEFORE EDITING. This component performs no comparison. The grades, the
 * difference, the label for it and the sentence describing it are all produced by
 * `src/passport/comparison.py` and are rendered verbatim. In particular, the wording is
 * never re-derived here: the backend owns the rule that a screening comparison talks
 * about the RESULT and never about the disease, and this file must not invent a phrase
 * that gets around it.
 *
 * The two "not available" states are first-class, not error states:
 *   * a first screening has no previous result, and
 *   * an ungradeable screening produced no result to compare.
 * Both render as an explanation, never as a blank card or a zero.
 */
import { gradeTone, shortDate, type Comparison } from "@/lib/passport";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import { useChangeLabel } from "./changeLabel";

function Side({ heading, grade, label, date }: {
  heading: string; grade: number | null; label: string | null; date: string;
}) {
  const { meta } = useCareBridge();
  return (
    <div className={`pp-side tone-${gradeTone(grade)}`}>
      <span className="eyebrow">{heading}</span>
      <div className="pp-sidegrade">
        <span className="pp-gradenum">{grade ?? "—"}</span>
        <span className="pp-gradelabel">{label ?? "—"}</span>
      </div>
      <span className="pp-sidedate">{shortDate(date, meta.locale)}</span>
    </div>
  );
}

export default function ComparisonCard({ comparison }: { comparison: Comparison | null }) {
  const { t, meta } = useCareBridge();
  const changeLabel = useChangeLabel();
  if (!comparison) return null;

  if (!comparison.available) {
    const ungradeable = comparison.reason === "current_screening_ungradeable";
    return (
      <section className="cb-section pp-comparison none" aria-labelledby="pp-cmp-h">
        <div className="eyebrow">{t("passport.eyebrow")}</div>
        <h3 id="pp-cmp-h" className="cb-h">
          {t(ungradeable ? "passport.comparisonUngradeableTitle"
                         : "passport.comparisonNoPreviousTitle")}
        </h3>
        <p className="cb-lede">
          {t(ungradeable ? "passport.comparisonUngradeableBody"
                         : "passport.comparisonNoPreviousBody")}
        </p>
      </section>
    );
  }

  const change = comparison.grade_change;
  const direction = comparison.change_direction;
  // The words come from the reader's dictionary; the NUMBER comes from the backend.
  // Nothing here decides what changed.
  const changeText = changeLabel(change);

  return (
    <section className={`cb-section pp-comparison dir-${direction}`}
             aria-labelledby="pp-cmp-h">
      <div className="eyebrow">{t("passport.eyebrow")}</div>
      <h3 id="pp-cmp-h" className="cb-h">{t("passport.comparisonTitle")}</h3>

      <div className="pp-sides">
        <Side heading={t("passport.comparisonPrevious")}
              grade={comparison.previous.icdr_grade}
              label={comparison.previous.severity_label}
              date={comparison.previous.date} />
        <div className="pp-arrow" aria-hidden="true">→</div>
        <Side heading={t("passport.comparisonCurrent")}
              grade={comparison.current.icdr_grade}
              label={comparison.current.severity_label}
              date={comparison.current.date} />
      </div>

      <div className={`pp-change dir-${direction}`}>
        <span className="eyebrow">{t("passport.comparisonChange")}</span>
        <strong className="pp-changeno">
          {/* Written as the requirement writes it: 1 → 2, +1 category. The sign is
              printed explicitly so "+1" and "-1" cannot be misread as each other. */}
          {comparison.previous_grade} → {comparison.current_grade}
          <span className="pp-delta">
            {change > 0 ? `+${change}` : change}
          </span>
        </strong>
        <span className="pp-changelabel">{changeText}</span>
      </div>

      {/* The backend's own sentence, rendered as it was written. */}
      <p className="pp-statement">{comparison.statement}</p>

      {comparison.referral_change.newly_referable && (
        <div className="flagbox">{t("passport.comparisonNewlyReferable")}</div>
      )}
      {comparison.referral_change.no_longer_referable && (
        <p className="cb-note">{t("passport.comparisonNoLongerReferable")}</p>
      )}
      {comparison.quality_change.changed && (
        <p className="cb-note">{t("passport.comparisonQualityChanged")}</p>
      )}
      {comparison.current.clinician_review_status !== "pending" && (
        <p className="cb-note">
          {t("passport.comparisonClinicianReview")}:{" "}
          {comparison.current.clinician_review_status}
          {comparison.current.clinician_grade !== null
            && ` · ${t("result.gradeOf", { grade: comparison.current.clinician_grade })}`}
        </p>
      )}

      <p className="cb-note mono pp-interval">
        {comparison.interval_days !== null
          && t("passport.comparisonInterval", { days: comparison.interval_days })}
      </p>

      {/* The caveat is part of the card, not a footnote somewhere else. */}
      <p className="pp-caveat">{t("passport.comparisonNotDiagnosis")}</p>
    </section>
  );
}
