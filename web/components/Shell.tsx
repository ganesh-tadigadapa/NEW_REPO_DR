"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { getHealth, type Health } from "@/lib/api";
import { ROLE_LABEL } from "@/lib/auth";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import LanguageControl from "@/components/carebridge/LanguageControl";
import type { StringKey } from "@/lib/i18n";

// Base navigation. Same routes and same order as before; the labels now come from the
// translation layer instead of being literals, so the navigation is in the reader's
// language like the rest of the journey. CareBridge itself sits next to screening
// because that is where a patient needs it, not buried in a settings page.
//
// The Reports tab is inserted for verified doctors only — and only as a convenience:
// the page itself is protected by the API, not by this list.
const TABS: { href: string; key: StringKey }[] = [
  { href: "/", key: "nav.overview" },
  { href: "/screen", key: "nav.screen" },
  { href: "/carebridge", key: "nav.carebridge" },
  // The longitudinal record sits next to screening because that is where a returning
  // patient looks for it, not in a settings page.
  { href: "/passport", key: "nav.passport" },
  { href: "/review", key: "nav.review" },
  { href: "/dashboard", key: "nav.evidence" },
  { href: "/how-it-works", key: "nav.howItWorks" },
  { href: "/limitations", key: "nav.limitations" },
];

const REPORTS_TAB = { href: "/reports", key: "nav.reports" as StringKey };

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const { authenticated, account, doctorVerificationPending, signOut } = useAuth();
  const { t } = useCareBridge();

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setErr(String(e.message || e)));
  }, []);

  // Reports sits after Evidence so the informational pages stay at the end.
  const evidenceAt = TABS.findIndex((tab) => tab.href === "/dashboard") + 1;
  const tabs = account?.can_read_reports
    ? [...TABS.slice(0, evidenceAt), REPORTS_TAB, ...TABS.slice(evidenceAt)]
    : TABS;

  return (
    <>
      {health?.synthetic_demo_model && (
        <div className="synthbar">
          Demo model trained on synthetic images — predictions are meaningless and no
          number here may be quoted as a result.
        </div>
      )}
      {authenticated && doctorVerificationPending && (
        <div className="pendingbar">
          Doctor verification pending. Screening is available; the reports area opens once
          a programme administrator confirms your registration.
        </div>
      )}
      <div className="wrap">
        <header className="site">
          <div className="brandrow">
            <div>
              <h1 className="brand">{t("common.brand")}</h1>
              <div className="sub">
                SIH26038 · explainable AI triage for primary health centres
              </div>
            </div>
            <div className="brandright">
              {/* The language in force, readable without opening anything. */}
              <LanguageControl />
              <div className="sub mono" style={{ textAlign: "right" }}>
                {err && <span style={{ color: "var(--crimson)" }}>API unreachable</span>}
                {health && (
                  <>
                    <div>
                      API {health.status} · {health.version}
                    </div>
                    <div>
                      {health.model_loaded
                        ? `model ${health.model_id}`
                        : "no model loaded — quality + rules only"}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>

          <nav className="tabs">
            {tabs.map((tab) => (
              <Link
                key={tab.href}
                href={tab.href}
                className={`${path === tab.href ? "on" : ""}${
                  tab.href === "/carebridge" ? " cb-navtab" : ""}`}
              >
                {tab.href === "/carebridge" && <span aria-hidden="true">🌍 </span>}
                {t(tab.key)}
              </Link>
            ))}

            <span className="navspacer" />

            {/* A role indicator, and nothing else about the person. No name, no number. */}
            {authenticated && account ? (
              <>
                <span className={`rolechip role-${account.role}`}>
                  {ROLE_LABEL[account.role] || account.role.toUpperCase()}
                  {account.role === "doctor" && !account.doctor_verified && " · PENDING"}
                </span>
                <button className="navbtn" onClick={signOut}>{t("nav.logout")}</button>
              </>
            ) : (
              <>
                <Link href="/login" className="navlogin">{t("nav.login")}</Link>
                <Link href="/signup">{t("nav.signup")}</Link>
              </>
            )}
          </nav>
        </header>
        {children}
      </div>
    </>
  );
}
