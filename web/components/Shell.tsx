"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getHealth, type Health } from "@/lib/api";

const TABS = [
  { href: "/", label: "Overview" },
  { href: "/screen", label: "Screen an image" },
  { href: "/review", label: "Clinician review" },
  { href: "/dashboard", label: "Evidence" },
  { href: "/how-it-works", label: "How it works" },
  { href: "/limitations", label: "Limitations" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [health, setHealth] = useState<Health | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    getHealth().then(setHealth).catch((e) => setErr(String(e.message || e)));
  }, []);

  return (
    <>
      {health?.synthetic_demo_model && (
        <div className="synthbar">
          Demo model trained on synthetic images — predictions are meaningless and no
          number here may be quoted as a result.
        </div>
      )}
      <div className="wrap">
        <header className="site">
          <div className="brandrow">
            <div>
              <h1 className="brand">Diabetic Retinopathy Screening</h1>
              <div className="sub">
                SIH26038 · explainable AI triage for primary health centres
              </div>
            </div>
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
          <nav className="tabs">
            {TABS.map((t) => (
              <Link key={t.href} href={t.href} className={path === t.href ? "on" : ""}>
                {t.label}
              </Link>
            ))}
          </nav>
        </header>
        {children}
      </div>
    </>
  );
}
