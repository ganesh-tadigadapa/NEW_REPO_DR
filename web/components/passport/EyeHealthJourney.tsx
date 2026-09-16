"use client";
/**
 * "Your eye health journey" — the timeline as a list.
 *
 * Two jobs, and the second is the reason it is not optional:
 *
 *   1. It is the narrative the requirement asks for: each visit, its grade, what was
 *      available from it, the follow-up reminder between visits, and the comparison
 *      with the visit before.
 *   2. It is the ACCESSIBLE VIEW of the chart above it. The same data as text, in
 *      order, with the severity named in words — so the timeline never depends on
 *      being able to see an SVG, or to tell teal from gold.
 *
 * It grows by itself: it renders whatever the passport returned, so a screening added
 * next year appears with no change here.
 */
import { gradeTone, shortDate, type FollowUp, type TimelinePoint } from "@/lib/passport";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import { useChangeLabel } from "./changeLabel";

/** The change between this point and the previous GRADED one, or null. */
function changeFrom(points: TimelinePoint[], index: number): number | null {
  const current = points[index];
  if (current.icdr_grade === null || current.gradeable === false) return null;
  for (let i = index - 1; i >= 0; i--) {
    const p = points[i];
    if (p.icdr_grade !== null && p.gradeable !== false) {
      return current.icdr_grade - p.icdr_grade;
    }
  }
  return null;
}

export default function EyeHealthJourney({
  points, followUps = [], onSelect,
}: {
  points: TimelinePoint[];
  followUps?: FollowUp[];
  onSelect?: (point: TimelinePoint) => void;
}) {
  const { t, meta } = useCareBridge();
  const changeLabel = useChangeLabel();
  if (points.length === 0) return null;

  return (
    <section className="cb-section pp-journey" aria-labelledby="pp-j-h">
      <div className="eyebrow">{t("passport.eyebrow")}</div>
      <h3 id="pp-j-h" className="cb-h">{t("passport.journeyTitle")}</h3>
      <p className="cb-lede">{t("passport.journeyHint")}</p>

      <ol className="pp-steps">
        {points.map((p, i) => {
          const change = changeFrom(points, i);
          const graded = p.icdr_grade !== null && p.gradeable !== false;
          // The follow-up that was planned against THIS visit, if any. Rendered as the
          // connector to the next visit — which is what a follow-up actually is.
          const plan = followUps.find((f) => f.screening_id === p.screening_id);
          const last = i === points.length - 1;
          return (
            <li key={p.screening_id} className={`pp-step tone-${gradeTone(p.icdr_grade)}`}>
              <div className="pp-stepmark" aria-hidden="true">
                {graded ? p.icdr_grade : "—"}
              </div>
              <div className="pp-stepbody">
                <time className="pp-stepdate" dateTime={p.date}>
                  {shortDate(p.date, meta.locale)}
                </time>
                <div className="pp-stepgrade">
                  {graded
                    ? <>{t("result.gradeOf", { grade: p.icdr_grade as number })}
                        {" — "}{p.severity_label}</>
                    : t("passport.timelineUngradeable")}
                </div>

                <div className="pp-steptags">
                  {p.report_available && (
                    <span className="pill">{t("passport.journeyReportAvailable")}</span>
                  )}
                  {change !== null && (
                    <span className="pill">{t("passport.journeyComparisonAvailable")}</span>
                  )}
                  {p.clinician_review_status !== "pending" && (
                    <span className="pill">{p.clinician_review_status}</span>
                  )}
                </div>

                {change !== null && (
                  <div className={`pp-stepchange dir-${change > 0 ? "higher" : change < 0 ? "lower" : "same"}`}>
                    {changeLabel(change)}
                  </div>
                )}

                {p.referable && (
                  <div className="pp-stepnote">{t("passport.journeyClinicalFollowUp")}</div>
                )}

                {/* Only where a report actually exists. An ungradeable visit produced
                    no report, and offering to open one that is not there is worse than
                    offering nothing. */}
                {onSelect && p.report_available && (
                  <button type="button" className="linkish"
                          onClick={() => onSelect(p)}>
                    {t("passport.journeyViewReport")}
                  </button>
                )}
              </div>

              {/* The reminder between two visits. Not drawn after the last one: that
                  follow-up has not been answered yet and lives in its own card. */}
              {plan && !last && (
                <div className="pp-connector">
                  <span aria-hidden="true">↓</span>{" "}
                  {t("passport.journeyFollowUpStep")} · {plan.recommended_window.label}
                </div>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
