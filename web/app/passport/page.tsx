"use client";
/**
 * The patient's own Eye Health Passport.
 *
 * One page that answers three questions a person actually has between screenings:
 * what has happened to my eyes so far, what changed last time, and when should I come
 * back? Everything on it is read from `/v1/passport`, which is scoped to the caller's
 * own account by ownership — this page cannot ask for anybody else's record because
 * there is no endpoint that would take another account's id from it.
 */
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import Guard from "@/components/Guard";
import Shell from "@/components/Shell";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import LanguageOnboarding from "@/components/carebridge/LanguagePicker";
import ComparisonCard from "@/components/passport/ComparisonCard";
import ComparisonDelivery from "@/components/passport/ComparisonDelivery";
import EyeHealthJourney from "@/components/passport/EyeHealthJourney";
import FollowUpCard from "@/components/passport/FollowUpCard";
import GradeTimeline from "@/components/passport/GradeTimeline";
import ShareWithDoctor from "@/components/passport/ShareWithDoctor";
import { getPassport, type Passport, type TimelinePoint } from "@/lib/passport";

function PassportBody() {
  const { t } = useCareBridge();
  const router = useRouter();
  const [data, setData] = useState<Passport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    getPassport().then(setData).catch((e) => setError(e.message));
  }, []);

  // A point on the chart and a row in the journey both open that screening's report.
  const open = useCallback((point: TimelinePoint) => {
    setSelected(point.screening_id);
    if (point.report_available) router.push(`/reports/${point.screening_id}`);
  }, [router]);

  if (error) return <div className="err">{error}</div>;
  if (!data) {
    return (
      <div className="card">
        <span className="spin" /> <span className="muted">{t("common.loading")}</span>
      </div>
    );
  }

  // An empty passport is a normal state with a next step, not an error.
  if (!data.has_history) {
    return (
      <div className="card pp-empty">
        <div className="eyebrow">{t("passport.eyebrow")}</div>
        <h2>{t("passport.emptyTitle")}</h2>
        <p className="muted">{t("passport.emptyBody")}</p>
        <Link href="/screen" className="cta solid">{t("passport.emptyCta")}</Link>
      </div>
    );
  }

  const latest = data.latest_screening;
  // The comparison PDF only exists where a comparison does. Offering to send one for a
  // first screening would be an offer the backend has to refuse.
  const canSendComparison = Boolean(
    latest && data.latest_comparison?.available);

  return (
    <>
      <header className="pp-head">
        <div>
          <div className="eyebrow">{t("passport.eyebrow")}</div>
          <h2 className="pp-title">{t("passport.title")}</h2>
          <p className="muted">{t("passport.subtitle")}</p>
        </div>
        <div className="pp-count mono">
          {data.history_count === 1
            ? t("passport.oneScreening")
            : t("passport.screeningsCount", { count: data.history_count })}
        </div>
      </header>

      <section className="cb-section" aria-labelledby="pp-tl-h">
        <h3 id="pp-tl-h" className="cb-h">{t("passport.timelineTitle")}</h3>
        <GradeTimeline points={data.timeline} onSelect={open} selectedId={selected} />
      </section>

      <ComparisonCard comparison={data.latest_comparison} />
      <FollowUpCard followUp={data.follow_up} />
      {canSendComparison && latest && (
        <ComparisonDelivery screeningId={latest.screening_id} />
      )}
      <EyeHealthJourney
        points={data.timeline}
        followUps={data.follow_up_history}
        onSelect={open}
      />
      {/* The patient's half of the authorisation decision. Nothing above this line is
          visible to any doctor until the patient shares it from here. */}
      <ShareWithDoctor />
    </>
  );
}

export default function PassportPage() {
  return (
    <Guard>
      <Shell>
        <LanguageOnboarding />
        <div className="cb-results">
          <PassportBody />
        </div>
      </Shell>
    </Guard>
  );
}
