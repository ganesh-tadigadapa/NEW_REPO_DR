"use client";
/**
 * Translation coverage — a development-only readout.
 *
 * Every key in the English dictionary, checked against every language, with the missing
 * ones named. It renders nothing in a production build: it is a tool for whoever adds
 * the fifth language, not a feature for a patient.
 *
 * It is the third of three guards, and the weakest — `tsc` refuses a dictionary that is
 * missing a key, and tests/test_carebridge_i18n.py refuses one that is blank, out of
 * shape, or quietly left in English. This panel is how you SEE the state.
 */
import { coverageReport } from "@/lib/i18n/coverage";
import { useCareBridge } from "./CareBridgeProvider";

export default function CoveragePanel() {
  const { t } = useCareBridge();
  if (process.env.NODE_ENV === "production") return null;

  const report = coverageReport();
  const complete = report.every((c) => c.missing.length === 0);

  return (
    <section className="card cb-section" aria-labelledby="cb-cov-h">
      <div className="eyebrow">{t("coverage.devOnly")}</div>
      <h3 id="cb-cov-h" className="cb-h">{t("coverage.title")}</h3>
      <p className="cb-lede">{t("coverage.intro")}</p>
      <div className="tblwrap">
        <table>
          <thead>
            <tr>
              <th>{t("coverage.languageColumn")}</th>
              <th style={{ textAlign: "right" }}>{t("coverage.keysColumn")}</th>
              <th style={{ textAlign: "right" }}>{t("coverage.completeColumn")}</th>
            </tr>
          </thead>
          <tbody>
            {report.map((c) => (
              <tr key={c.code}>
                <td>
                  <span lang={c.code}>{c.nativeName}</span>{" "}
                  <span className="muted">· {c.englishName}</span>
                </td>
                <td className="num mono">{c.translated} / {c.total}</td>
                <td className="num mono">
                  <span className={`pill ${c.missing.length === 0 ? "pill-done" : "pill-warn"}`}>
                    {c.percent}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {complete ? (
        <p className="cb-note">{t("coverage.allComplete")}</p>
      ) : (
        <div className="flagbox" style={{ marginTop: 12 }}>
          <strong>{t("coverage.missingTitle")}</strong>
          <ul style={{ paddingLeft: 18, margin: "6px 0 0" }}>
            {report.filter((c) => c.missing.length).map((c) => (
              <li key={c.code} className="mono" style={{ fontSize: ".78rem" }}>
                {c.code}: {c.missing.join(", ")}
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
