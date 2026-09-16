"use client";
/**
 * "Your previous screening is available."
 *
 * Shown above the upload form to somebody who has been screened before, so the person
 * knows BEFORE they upload that this photograph will be compared with their last one.
 *
 * It asks the server rather than guessing from local state: a health centre's shared
 * device has many patients through it and browser storage would be the wrong answer for
 * every one of them. It renders nothing at all while it does not know, and nothing for
 * a first-time patient — an empty history is a normal state, not an error.
 */
import { useEffect, useState } from "react";
import Link from "next/link";
import { getPassportStatus, shortDate, type PassportStatus } from "@/lib/passport";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";

export default function ReturningBanner() {
  const { t, meta } = useCareBridge();
  const [status, setStatus] = useState<PassportStatus | null>(null);

  useEffect(() => {
    let live = true;
    // A failure is silent: the screening page must work whether or not the longitudinal
    // layer answers, so an unreachable passport simply shows no banner.
    getPassportStatus().then((s) => { if (live) setStatus(s); }).catch(() => {});
    return () => { live = false; };
  }, []);

  if (!status?.has_history || !status.last_screening) return null;
  const last = status.last_screening;

  return (
    <section className="pp-returning" aria-labelledby="pp-ret-h">
      <span className="pp-reticon" aria-hidden="true">🪪</span>
      <div>
        <div className="eyebrow">{t("passport.eyebrow")}</div>
        <h3 id="pp-ret-h">{t("passport.returnTitle")}</h3>
        <p>{t("passport.returnBody", { date: shortDate(last.date, meta.locale) })}</p>
        {last.icdr_grade !== null && (
          <p className="cb-note">
            {t("passport.returnLastGrade", { grade: last.icdr_grade })}
            {last.severity_label ? ` — ${last.severity_label}` : ""}
          </p>
        )}
        {status.follow_up && (
          <p className="cb-note">
            {t("passport.followUpSuggested")}:{" "}
            {status.follow_up.recommended_window.label}
          </p>
        )}
      </div>
      <Link href="/passport" className="ghost pp-retcta">
        {t("passport.returnCta")}
      </Link>
    </section>
  );
}
