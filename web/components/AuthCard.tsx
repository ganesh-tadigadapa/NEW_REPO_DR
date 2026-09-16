"use client";
/** Shared chrome for /login and /signup so the two pages are visibly one system. */
import Link from "next/link";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import LanguageControl from "@/components/carebridge/LanguageControl";

export function AuthLayout({ title, subtitle, children, footer }: {
  title: string; subtitle: string;
  children: React.ReactNode; footer?: React.ReactNode;
}) {
  const { t } = useCareBridge();
  return (
    <div className="wrap">
      <header className="site" style={{ marginBottom: 0 }}>
        <div className="brandrow">
          <div>
            <h1 className="brand">{t("common.brand")}</h1>
            <div className="sub">SIH26038 · explainable AI triage for primary health centres</div>
          </div>
          {/* The language has to be changeable before there is an account to attach it
              to — otherwise the first screen is the one nobody can read. */}
          <div className="brandright">
            <LanguageControl />
            <Link href="/" className="sub" style={{ textDecoration: "none" }}>
              ← {t("nav.overview")}
            </Link>
          </div>
        </div>
      </header>

      <div className="authpage">
        <div className="card authcard">
          <h2 className="authtitle">{title}</h2>
          <p className="authsub">{subtitle}</p>
          {children}
          {footer && <div className="authfoot">{footer}</div>}
          <p className="cb-note">{t("auth.noPassword")} {t("auth.languageStays")}</p>
        </div>

        <aside className="authaside">
          <div className="eyebrow">Why a mobile number</div>
          <p>
            There is no password to remember or reset. A health worker signs in with the
            number they already carry, and a one-time code confirms it is them.
          </p>
          <div className="eyebrow" style={{ marginTop: 18 }}>Two kinds of account</div>
          <p>
            A <strong>user account</strong> screens images and sees its own results. A{" "}
            <strong>doctor account</strong> can additionally open the anonymised report
            queue — once a programme administrator has confirmed the medical registration.
          </p>
          <p className="muted" style={{ fontSize: ".8rem", marginBottom: 0 }}>
            Reports carry a scan identifier only. No patient name or phone number is
            stored in, or shown on, the clinician view.
          </p>
        </aside>
      </div>

      <footer className="site">
        <p>Screening triage aid. Not a diagnostic device. Not for clinical use.</p>
      </footer>
    </div>
  );
}

export function FieldLabel({ children }: { children: React.ReactNode }) {
  return <span className="fieldlabel">{children}</span>;
}
