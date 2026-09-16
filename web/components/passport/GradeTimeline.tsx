"use client";
/**
 * The longitudinal ICDR Grade Timeline.
 *
 * READ THIS BEFORE EDITING. Three decisions here are clinical, not stylistic.
 *
 * 1. **It is a STEP line, not a smooth one.** The ICDR grade is an ordinal CATEGORY
 *    (0-4), so there is no defined value between two screenings and a sloped segment
 *    would draw one. The line holds each grade until the next screening changes it.
 *    For the same reason nothing here averages grades, fits a trend, or computes a rate
 *    of change per month.
 *
 * 2. **Position is the encoder; colour is redundant.** The grade is read off the y
 *    axis and is printed next to every marker as "G2". The status colour (the product's
 *    existing teal/gold/crimson verdict palette) repeats that information and never
 *    carries it alone — which is what keeps the chart legible under colour-vision
 *    deficiency, in forced-colors mode and in print. The list view below the figure is
 *    the same data as text.
 *
 * 3. **An ungradeable visit is drawn, but not on the line.** It is a real event on the
 *    patient's timeline and hiding it would misrepresent the history; it is also not a
 *    result, so the step does not pass through it. It renders as a hollow marker on the
 *    axis floor, labelled as such.
 *
 * The component performs no analysis. Every grade, label and date is taken verbatim
 * from the passport API.
 */
import { useId, useMemo, useState } from "react";
import { gradeTone, monthYear, shortDate, type TimelinePoint } from "@/lib/passport";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";

const GRADES = [0, 1, 2, 3, 4];

// Geometry in user units. The SVG scales to its container through the viewBox, so these
// are stable whatever the screen is.
const VB_W = 720;
const VB_H = 240;
const PAD = { top: 26, right: 34, bottom: 44, left: 40 };
const PLOT_W = VB_W - PAD.left - PAD.right;
const PLOT_H = VB_H - PAD.top - PAD.bottom;

export default function GradeTimeline({
  points, onSelect, selectedId,
}: {
  points: TimelinePoint[];
  onSelect?: (point: TimelinePoint) => void;
  selectedId?: string | null;
}) {
  const { t, meta } = useCareBridge();
  const titleId = useId();
  const [active, setActive] = useState<string | null>(null);

  const laid = useMemo(() => {
    const span = Math.max(1, points.length - 1);
    return points.map((p, i) => ({
      p,
      // A single screening sits in the middle rather than hard against the left edge.
      x: points.length === 1
        ? PAD.left + PLOT_W / 2
        : PAD.left + (PLOT_W * i) / span,
      // Grade 0 at the bottom, grade 4 at the top. An ungradeable visit has no grade,
      // so it is pinned to the floor and excluded from the line below.
      y: PAD.top + PLOT_H - (PLOT_H * ((p.icdr_grade ?? 0) / 4)),
      graded: p.icdr_grade !== null && p.gradeable !== false,
    }));
  }, [points]);

  if (points.length === 0) return null;

  const graded = laid.filter((d) => d.graded);

  // The step path: hold the previous grade across to the new x, then change category.
  const path = graded.reduce((acc, d, i) => (
    i === 0 ? `M ${d.x} ${d.y}` : `${acc} L ${d.x} ${graded[i - 1].y} L ${d.x} ${d.y}`
  ), "");

  const activePoint = laid.find((d) => d.p.screening_id === active);

  return (
    <figure className="pp-figure">
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        className="pp-chart"
        role="img"
        aria-labelledby={titleId}
        preserveAspectRatio="xMidYMid meet"
      >
        <title id={titleId}>{t("passport.timelineTitle")}</title>

        {/* --- grid and y axis. Recessive by design: the data is the subject. --- */}
        {GRADES.map((g) => {
          const y = PAD.top + PLOT_H - (PLOT_H * (g / 4));
          return (
            <g key={g}>
              <line
                x1={PAD.left} x2={VB_W - PAD.right} y1={y} y2={y}
                className="pp-grid"
              />
              <text x={PAD.left - 9} y={y + 4} className="pp-axis" textAnchor="end">
                G{g}
              </text>
            </g>
          );
        })}

        {/* --- the step line --- */}
        {graded.length > 1 && <path d={path} className="pp-line" fill="none" />}

        {/* --- the points --- */}
        {laid.map((d) => {
          const tone = d.graded ? gradeTone(d.p.icdr_grade) : "none";
          const isActive = d.p.screening_id === active
            || d.p.screening_id === selectedId;
          return (
            <g
              key={d.p.screening_id}
              className={`pp-point tone-${tone}${isActive ? " on" : ""}`}
              tabIndex={0}
              role={onSelect ? "button" : undefined}
              aria-label={
                d.graded
                  ? t("passport.timelinePointLabel", {
                      date: shortDate(d.p.date, meta.locale),
                      grade: d.p.icdr_grade as number,
                    })
                  : `${shortDate(d.p.date, meta.locale)} — ${t("passport.timelineUngradeable")}`
              }
              onMouseEnter={() => setActive(d.p.screening_id)}
              onMouseLeave={() => setActive(null)}
              onFocus={() => setActive(d.p.screening_id)}
              onBlur={() => setActive(null)}
              onClick={() => onSelect?.(d.p)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onSelect?.(d.p);
                }
              }}
            >
              {/* An invisible hit target far larger than the mark, so the point is
                  reachable with a finger as well as a mouse. */}
              <circle cx={d.x} cy={d.graded ? d.y : PAD.top + PLOT_H} r={20}
                      className="pp-hit" />
              <circle
                cx={d.x} cy={d.graded ? d.y : PAD.top + PLOT_H} r={7}
                className={d.graded ? "pp-dot" : "pp-dot hollow"}
              />
              {d.graded && (
                <text x={d.x} y={d.y - 14} className="pp-plabel" textAnchor="middle">
                  G{d.p.icdr_grade}
                </text>
              )}
            </g>
          );
        })}

        {/* --- x axis: the month of each visit --- */}
        {laid.map((d, i) => (
          // Every label on a crowded axis collides, so past six visits only every other
          // one is printed. The list view below carries all of them.
          (laid.length <= 6 || i % 2 === 0 || i === laid.length - 1) && (
            <text
              key={`x-${d.p.screening_id}`}
              x={d.x} y={VB_H - PAD.bottom + 20}
              className="pp-axis" textAnchor="middle"
            >
              {monthYear(d.p.date, meta.locale)}
            </text>
          )
        ))}
      </svg>

      {/* The hover/focus readout. A live region so a screen reader hears the point that
          keyboard focus just landed on. */}
      <p className="pp-readout" role="status" aria-live="polite">
        {activePoint ? (
          <>
            <strong>{shortDate(activePoint.p.date, meta.locale)}</strong>
            {" — "}
            {activePoint.graded
              ? `${t("result.gradeOf", { grade: activePoint.p.icdr_grade as number })} · ${activePoint.p.severity_label ?? ""}`
              : t("passport.timelineUngradeable")}
          </>
        ) : (
          <span className="muted">{t("passport.timelineHint")}</span>
        )}
      </p>

      <figcaption className="pp-caption">{t("passport.timelineAxis")} · 0–4</figcaption>
    </figure>
  );
}
