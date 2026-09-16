"use client";
/**
 * One report, in full, for a verified doctor.
 *
 * The layout mirrors the medical data model deliberately: the AI's prediction, the
 * classical evidence, the rule engine's independent opinion, the resulting screening
 * recommendation, and the clinician's review are five separate blocks. Recording a
 * review adds a block; it never rewrites the one above it.
 */
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import Guard from "@/components/Guard";
import Shell from "@/components/Shell";
import {
  getReport, REVIEW_STATUSES, submitClinicianReview, type ReportDetail,
} from "@/lib/reports";
import { ICDR_LABELS } from "@/lib/api";
import PatientHistory from "@/components/passport/PatientHistory";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="kv">
      <span className="kvk">{k}</span>
      <span className="kvv">{v}</span>
    </div>
  );
}

function pct(x: number | null | undefined) {
  return x == null ? "—" : `${(x * 100).toFixed(0)}%`;
}

function Detail({ scanId }: { scanId: string }) {
  const [d, setD] = useState<ReportDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [notes, setNotes] = useState("");
  const [grade, setGrade] = useState<number | "">("");
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  const load = () => getReport(scanId).then(setD).catch((e) => setError(e.message));
  useEffect(() => { load(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [scanId]);

  const save = async () => {
    if (!status) { setError("Choose a review status."); return; }
    setBusy(true); setError(null);
    try {
      await submitClinicianReview(scanId, {
        status, notes, clinician_grade: grade === "" ? null : Number(grade),
      });
      setSaved("Review recorded. The AI result is unchanged.");
      setStatus(""); setNotes(""); setGrade("");
      await load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  if (error && !d) return <div className="err">{error}</div>;
  if (!d) return <div className="card"><span className="spin" /> <span className="muted">Loading report…</span></div>;

  const img = d.explain;
  const hasImages = img.overlay_png_b64 || img.lesion_overlay_png_b64 || img.gradcam_png_b64;

  return (
    <>
      <div className="brandrow" style={{ marginBottom: 14 }}>
        <div>
          <div className="eyebrow">Report</div>
          <h2 className="mono" style={{ margin: "4px 0 0", fontSize: "1.2rem" }}>{d.scan_id}</h2>
          <div className="muted" style={{ fontSize: ".84rem" }}>
            {new Date(d.created_at).toLocaleString()} · model {d.model_id || "none"}
          </div>
        </div>
        <Link href="/reports" className="ghost" style={{ textDecoration: "none", padding: "9px 16px", border: "1px solid var(--line-2)", borderRadius: 6 }}>
          ← All reports
        </Link>
      </div>

      {d.synthetic_demo_model && (
        <div className="err" style={{ marginBottom: 14 }}>
          <strong>Synthetic demo model.</strong> This prediction is meaningless and must
          not be used for any clinical judgement.
        </div>
      )}

      <div className="grid2" style={{ alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* ---------------------------------------------------- 1. AI */}
          <div className="card">
            <div className="eyebrow">1 · AI prediction</div>
            <div style={{ display: "flex", gap: 16, alignItems: "baseline", marginTop: 8 }}>
              <div className="gradebig">{d.ai.icdr_grade ?? "—"}</div>
              <div>
                <div style={{ fontWeight: 600 }}>{d.ai.icdr_label || d.ai.unavailable_reason || "not graded"}</div>
                <div className="muted" style={{ fontSize: ".85rem" }}>
                  {d.ai.referable ? "Referable" : d.ai.referable === false ? "No referral" : "—"}
                  {" · confidence "}{pct(d.ai.confidence)}
                  {d.ai.confidence_calibrated ? " (calibrated)" : ""}
                </div>
              </div>
            </div>
            {d.ai.per_grade_probability && (
              <div style={{ marginTop: 12 }}>
                {d.ai.per_grade_probability.map((p, i) => (
                  <div key={i} style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 4 }}>
                    <span className="mono" style={{ fontSize: ".72rem", width: 74 }}>{i} · {ICDR_LABELS[i]}</span>
                    <span className="bar" style={{ flex: 1 }}><span style={{ width: `${p * 100}%` }} /></span>
                    <span className="mono" style={{ fontSize: ".72rem", width: 38, textAlign: "right" }}>{(p * 100).toFixed(0)}%</span>
                  </div>
                ))}
              </div>
            )}
            <p className="muted" style={{ fontSize: ".76rem", marginBottom: 0, marginTop: 12 }}>
              This block is the model’s output as recorded at screening time. A clinician
              review never modifies it.
            </p>
          </div>

          {/* ------------------------------------------- 2. image evidence */}
          {hasImages ? (
            <div className="card">
              <div className="eyebrow">2 · Visual evidence</div>
              <div className="imgs" style={{ marginTop: 10 }}>
                {img.lesion_overlay_png_b64 && (
                  <figure>
                    <img src={`data:image/png;base64,${img.lesion_overlay_png_b64}`} alt="retinal image with lesion overlay" />
                    <figcaption>Retinal image · detected lesions and landmarks</figcaption>
                  </figure>
                )}
                {img.overlay_png_b64 && (
                  <figure>
                    <img src={`data:image/png;base64,${img.overlay_png_b64}`} alt="Grad-CAM overlay" />
                    <figcaption>Grad-CAM · what the model looked at</figcaption>
                  </figure>
                )}
              </div>
              {img.attention_summary && (
                <p style={{ fontSize: ".86rem", marginBottom: 0 }}>{img.attention_summary}</p>
              )}
            </div>
          ) : (
            <div className="card">
              <div className="eyebrow">2 · Visual evidence</div>
              <p className="muted" style={{ marginBottom: 0 }}>
                {d.evidence_available
                  ? (img.gradcam_unavailable_reason || "No heat map was produced for this scan.")
                  : "Images for this scan are not in the evidence store (it was screened before evidence storage was enabled, or storage is turned off)."}
              </p>
            </div>
          )}

          {/* ------------------------------------------- 3. lesion counts */}
          {d.lesions && (
            <div className="card">
              <div className="eyebrow">3 · Lesion evidence (classical CV)</div>
              <div className="tblwrap" style={{ marginTop: 10 }}>
                <table>
                  <thead><tr><th>Lesion</th><th>Count</th><th>By quadrant</th></tr></thead>
                  <tbody>
                    {Object.entries(d.lesions).map(([k, v]: any) => (
                      <tr key={k}>
                        <td style={{ textTransform: "capitalize" }}>{k.replace(/_/g, " ")}</td>
                        <td className="num">{v?.count ?? "—"}</td>
                        <td className="mono" style={{ fontSize: ".76rem" }}>
                          {v?.by_quadrant ? Object.entries(v.by_quadrant).map(([q, n]) => `${q}:${n}`).join("  ") : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* -------------------------------------------- 4. quality gate */}
          <div className="card">
            <div className="eyebrow">4 · Quality gate</div>
            <Row k="Result" v={d.quality.gradeable ? "Pass — graded" : "Refused — not graded"} />
            <Row k="Overall score" v={d.quality.overall_score != null ? d.quality.overall_score.toFixed(2) : "—"} />
            {d.quality.checks && (
              <div className="checks" style={{ marginTop: 10 }}>
                {Object.entries(d.quality.checks).map(([name, c]) => (
                  <div className="check" key={name}>
                    <span className={`dot ${c.passed ? "ok" : "bad"}`} />
                    <span>
                      <strong style={{ textTransform: "capitalize" }}>{name.replace(/_/g, " ")}</strong>
                      <br />
                      <span className="mono" style={{ fontSize: ".72rem" }}>
                        {c.value} / {c.threshold} {c.unit}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
            {d.quality.recapture_instruction && (
              <div className="flagbox" style={{ marginTop: 10 }}>{d.quality.recapture_instruction}</div>
            )}
          </div>

          {/* --------------------------------------- 5. rule engine + agreement */}
          <div className="card">
            <div className="eyebrow">5 · ICDR rule engine (independent)</div>
            <Row k="Rule grade" v={d.rule_engine.rule_grade ?? "—"} />
            <Row k="Rule referable" v={d.rule_engine.rule_referable == null ? "—" : d.rule_engine.rule_referable ? "Yes" : "No"} />
            <Row
              k="Agreement with AI"
              v={d.rule_engine.agrees_with_cnn == null ? "—"
                : d.rule_engine.agrees_with_cnn
                  ? <span style={{ color: "var(--teal)" }}>Agrees</span>
                  : <span style={{ color: "var(--crimson)" }}>Disagrees</span>}
            />
            {d.rule_engine.criteria_fired?.length ? (
              <Row k="Criteria fired" v={<span className="mono" style={{ fontSize: ".76rem" }}>{d.rule_engine.criteria_fired.join(", ")}</span>} />
            ) : null}
            {d.rule_engine.flag_message && (
              <div className="flagbox" style={{ marginTop: 10 }}>{d.rule_engine.flag_message}</div>
            )}
          </div>

          {/* ------------------------------- 6. screening recommendation */}
          <div className={`verdict ${d.screening_recommendation.referral ? "v-refer" : "v-clear"}`}>
            <div>
              <h2>{d.screening_recommendation.referral ? "Refer" : "No referral"}</h2>
              <p className="body">
                {d.screening_recommendation.recommendation || "Screening recommendation as recorded."}
                {d.screening_recommendation.escalated ? " · Escalated" : ""}
              </p>
            </div>
          </div>

          {/* ---------------------------------------- 7. clinician review */}
          <div className="card">
            <div className="eyebrow">6 · Clinician review</div>
            <p style={{ marginTop: 8, marginBottom: 10 }}>
              Current status:{" "}
              <strong>{d.clinician_review.status_label}</strong>
              {d.clinician_review.clinician_grade != null && (
                <> · clinician grade <strong>{d.clinician_review.clinician_grade}</strong></>
              )}
            </p>

            {saved && <div style={{ color: "var(--teal)", fontSize: ".86rem", marginBottom: 10 }}>{saved}</div>}
            {error && <div className="err" style={{ marginBottom: 10 }}>{error}</div>}

            <label className="field">
              <span className="fieldlabel">Review status</span>
              <select className="txt" value={status} onChange={(e) => setStatus(e.target.value)}>
                <option value="">— choose —</option>
                {REVIEW_STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="fieldlabel">Your grade (optional — recorded alongside the AI grade)</span>
              <select className="txt" value={grade}
                      onChange={(e) => setGrade(e.target.value === "" ? "" : Number(e.target.value))}>
                <option value="">— no clinician grade —</option>
                {[0, 1, 2, 3, 4].map((g) => (
                  <option key={g} value={g}>{g} · {ICDR_LABELS[g]}</option>
                ))}
              </select>
            </label>

            <label className="field">
              <span className="fieldlabel">Notes</span>
              <textarea className="txt" rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} />
            </label>

            <button className="primary" onClick={save} disabled={busy || !status}>
              {busy ? <><span className="spin" /> Saving…</> : "Record review"}
            </button>

            <p className="muted" style={{ fontSize: ".76rem", marginTop: 10, marginBottom: 0 }}>
              Your review is stored as a new entry alongside the AI result, not in place
              of it. Both remain readable, which is what makes the record auditable.
            </p>
          </div>

          {/* The longitudinal record for the patient this scan belongs to. Renders an
              explanation instead when this doctor holds no access grant for them —
              being a verified doctor is not by itself enough to read one person's
              history over time. See components/passport/PatientHistory.tsx. */}
          <PatientHistory scanId={scanId} />

          {d.clinician_review_history.length > 0 && (
            <div className="card">
              <div className="eyebrow">Review history</div>
              <div className="tblwrap" style={{ marginTop: 10 }}>
                <table>
                  <thead><tr><th>When</th><th>Status</th><th>Grade</th><th>Notes</th></tr></thead>
                  <tbody>
                    {d.clinician_review_history.map((h, i) => (
                      <tr key={i}>
                        <td className="mono" style={{ fontSize: ".74rem" }}>
                          {new Date(h.reviewed_at).toLocaleString()}
                        </td>
                        <td>{h.status_label}</td>
                        <td className="num">{h.clinician_grade ?? "—"}</td>
                        <td style={{ fontSize: ".8rem" }}>{h.notes || <span className="muted">—</span>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}

export default function ReportDetailPage() {
  const params = useParams();
  const scanId = String(params?.scan_id || "");
  return (
    <Guard requireDoctor>
      <Shell>
        <Detail scanId={scanId} />
      </Shell>
    </Guard>
  );
}
