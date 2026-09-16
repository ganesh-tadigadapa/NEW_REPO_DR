"use client";
/**
 * The doctor-facing longitudinal view, opened from one report.
 *
 * READ THIS BEFORE EDITING — two rules, both enforced by the API rather than by this
 * component, and neither of which this component may work around.
 *
 *   1. **Authorisation.** A verified doctor can read the anonymised report collection.
 *      A longitudinal record is a different object — it links several screenings to one
 *      person over time — so it additionally needs an access grant for that patient,
 *      created by recording a clinician review on one of their screenings or by an
 *      administrator. `/v1/passport/by-scan/{scan_id}` answers 404 without one, and
 *      this component renders that as an explanation of how to get access.
 *
 *   2. **Anonymity.** Nothing here shows a name, a mobile number or a patient
 *      reference, because the API does not return those fields at all — see the
 *      whitelist in `src/passport/service.py::patient_history_for_doctor`.
 *
 * The clinician follow-up form below sets the follow-up PLAN and nothing else. The AI
 * grade, the referral decision and the comparison are untouched by it, and the response
 * echoes them back so that is visible rather than merely claimed.
 */
import { useCallback, useEffect, useState } from "react";
import {
  getPatientHistoryByScan, setClinicianFollowUp, shortDate,
  type FollowUp, type PatientHistory as History,
} from "@/lib/passport";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import ComparisonCard from "./ComparisonCard";
import GradeTimeline from "./GradeTimeline";

const PRIORITIES: FollowUp["priority"][] = ["routine", "soon", "prompt", "urgent"];

export default function PatientHistory({ scanId }: { scanId: string }) {
  const { t, meta } = useCareBridge();
  const [history, setHistory] = useState<History | null>(null);
  const [denied, setDenied] = useState(false);
  const [months, setMonths] = useState<number | "">("");
  const [reason, setReason] = useState("");
  const [priority, setPriority] = useState<FollowUp["priority"] | "">("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getPatientHistoryByScan(scanId)
      .then((h) => { setHistory(h); setDenied(false); })
      // 404 is the ordinary answer for "no grant", and is not an error to shout about.
      .catch(() => setDenied(true));
  }, [scanId]);

  useEffect(() => { load(); }, [load]);

  const save = useCallback(async () => {
    if (!history || months === "") return;
    setBusy(true);
    setError(null);
    try {
      await setClinicianFollowUp(history.patient_id, {
        screening_id: scanId,
        follow_up_months: Number(months),
        reason,
        priority: priority || null,
      });
      setSaved(true);
      setMonths(""); setReason(""); setPriority("");
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [history, months, reason, priority, scanId, load]);

  if (denied) {
    return (
      <div className="card">
        <div className="eyebrow">{t("passport.eyebrow")}</div>
        <h3 style={{ margin: "6px 0 8px" }}>{t("passport.doctorNoAccessTitle")}</h3>
        <p className="muted" style={{ fontSize: ".86rem", marginBottom: 0 }}>
          {t("passport.doctorNoAccessBody")}
        </p>
      </div>
    );
  }
  if (!history) return null;
  // One screening is a record, not a history: there is nothing longitudinal to show.
  if (history.history_count < 1) return null;

  return (
    <div className="card pp-doctor">
      <div className="eyebrow">{t("passport.doctorTitle")}</div>
      <p className="muted" style={{ fontSize: ".8rem", marginTop: 6 }}>
        {t("passport.doctorHint")}
      </p>
      <p className="mono muted" style={{ fontSize: ".72rem" }}>
        {history.patient_id} · {history.history_count === 1
          ? t("passport.oneScreening")
          : t("passport.screeningsCount", { count: history.history_count })}
      </p>

      {history.timeline.length > 1 && <GradeTimeline points={history.timeline} />}

      <div className="tblwrap" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Date</th><th>Grade</th><th>Severity</th><th>Quality</th>
              <th>Referral</th><th>Change</th>
            </tr>
          </thead>
          <tbody>
            {history.timeline.map((p, i) => {
              const comparison = history.comparisons.find(
                (c) => c.current.screening_id === p.screening_id);
              const change = comparison?.grade_change;
              return (
                <tr key={p.screening_id}>
                  <td className="mono" style={{ fontSize: ".74rem" }}>
                    {shortDate(p.date, meta.locale)}
                  </td>
                  <td className="num">{p.icdr_grade ?? "—"}</td>
                  <td>{p.severity_label || <span className="muted">—</span>}</td>
                  <td>
                    <span className={`pill ${p.quality_status === "refused" ? "pill-warn" : ""}`}>
                      {p.quality_status}
                    </span>
                  </td>
                  <td>
                    {p.referable
                      ? <span className="pill pill-refer">Referable</span>
                      : p.referable === false
                        ? <span className="pill pill-clear">No referral</span>
                        : <span className="pill">—</span>}
                  </td>
                  <td className="num mono">
                    {change === undefined ? "—"
                      : change > 0 ? `+${change}` : String(change)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {history.latest_comparison && (
        <ComparisonCard comparison={history.latest_comparison} />
      )}

      {history.follow_up && (
        <p className="muted" style={{ fontSize: ".82rem", marginTop: 12 }}>
          <strong>{t("passport.followUpSuggested")}:</strong>{" "}
          {history.follow_up.recommended_window.label} · {history.follow_up.basis_label}
        </p>
      )}

      {/* The clinician's own follow-up. Takes precedence over the guideline window. */}
      <div className="pp-doctorform">
        <div className="eyebrow">{t("passport.doctorSetFollowUp")}</div>
        <div className="pp-formrow">
          <label>
            <span className="muted">{t("passport.doctorMonths")}</span>
            <input
              type="number" min={0} max={60} value={months}
              onChange={(e) => setMonths(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </label>
          <label>
            <span className="muted">{t("passport.doctorPriority")}</span>
            <select value={priority}
                    onChange={(e) => setPriority(e.target.value as FollowUp["priority"] | "")}>
              <option value="">—</option>
              {PRIORITIES.map((p) => <option key={p} value={p}>{p}</option>)}
            </select>
          </label>
        </div>
        <label style={{ display: "block", marginTop: 8 }}>
          <span className="muted">{t("passport.doctorReason")}</span>
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button className="primary" style={{ marginTop: 10 }}
                onClick={save} disabled={busy || months === ""}>
          {busy ? <><span className="spin" /> …</> : t("passport.doctorSave")}
        </button>
        {saved && <p className="cb-note">{t("passport.doctorSaved")}</p>}
        {error && <p className="err">{error}</p>}
      </div>
    </div>
  );
}
