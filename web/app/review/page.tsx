"use client";
/**
 * Clinician review screen. The <30 s sign-off requirement is MEASURED here, not asserted:
 * the timer starts when the scan renders and stops on submit, and the elapsed seconds go
 * to the API with the decision.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import Guard from "@/components/Guard";
import Shell from "@/components/Shell";
import { getScans, ICDR_LABELS, submitReview } from "@/lib/api";

type Scan = {
  scan_id: string; created_at: string; icdr_grade: number | null;
  referable: boolean | null; gradeable: boolean | null; rule_grade: number | null;
  rule_flag: string | null; confidence: number | null; review?: any;
};

export default function Review() {
  const [scans, setScans] = useState<Scan[]>([]);
  const [i, setI] = useState(0);
  const [notes, setNotes] = useState("");
  const [corrected, setCorrected] = useState<number | "">("");
  const [saved, setSaved] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const t0 = useRef<number>(Date.now());

  const load = () =>
    getScans(50)
      .then((d) => setScans((d.scans || []).filter((s: Scan) => s.gradeable)))
      .catch((e) => setErr(String(e.message || e)));

  useEffect(() => { load(); }, []);
  const pending = useMemo(() => scans.filter((s) => !s.review), [scans]);
  const cur = pending[i];
  useEffect(() => { t0.current = Date.now(); setNotes(""); setCorrected(""); }, [cur?.scan_id]);

  const decide = async (agrees: boolean) => {
    if (!cur) return;
    const seconds = (Date.now() - t0.current) / 1000;
    try {
      await submitReview(cur.scan_id, {
        agrees,
        corrected_grade: corrected === "" ? null : Number(corrected),
        notes,
        seconds_to_decide: seconds,
      });
      setSaved(`Recorded in ${seconds.toFixed(1)} s`);
      await load();
      setI(0);
    } catch (e: any) { setErr(e.message); }
  };

  return (
    <Guard>
    <Shell>
      {err && <div className="err" style={{ marginBottom: 14 }}>{err}</div>}
      {!cur ? (
        <div className="card">
          <div className="eyebrow">Review queue</div>
          <p style={{ marginTop: 8 }}>
            Nothing waiting. Screen an image first, then it appears here.
          </p>
          {saved && <p className="muted">{saved}</p>}
        </div>
      ) : (
        <div className="grid2" style={{ alignItems: "start" }}>
          <div className="card">
            <div className="eyebrow">Scan {i + 1} of {pending.length}</div>
            <p className="mono" style={{ fontSize: ".78rem", color: "var(--muted)" }}>
              {cur.scan_id} · {new Date(cur.created_at).toLocaleString()}
            </p>
            <p style={{ fontSize: "1.05rem", marginTop: 10 }}>
              Model: <strong>grade {cur.icdr_grade} — {ICDR_LABELS[cur.icdr_grade ?? 0]}</strong>{" "}
              {cur.referable ? <span className="pill">REFER</span> : <span className="pill">clear</span>}
            </p>
            <p style={{ fontSize: ".9rem" }}>
              Clinical rules: grade {cur.rule_grade}
              {cur.rule_flag && <> · <span className="pill">{cur.rule_flag}</span></>}
            </p>
            {cur.confidence != null && (
              <p className="muted" style={{ fontSize: ".84rem" }}>
                confidence {(cur.confidence * 100).toFixed(0)}%
              </p>
            )}
          </div>
          <div className="card">
            <div className="eyebrow">Your decision</div>
            <label style={{ fontSize: ".84rem", display: "block", marginTop: 10 }}>
              <span className="muted">Amend grade (leave blank to accept)</span>
              <select
                value={corrected}
                onChange={(e) => setCorrected(e.target.value === "" ? "" : Number(e.target.value))}
                style={{
                  width: "100%", marginTop: 5, padding: "9px 11px",
                  border: "1px solid var(--line-2)", borderRadius: 6,
                  background: "var(--surface)", color: "var(--ink)",
                }}
              >
                <option value="">— accept model grade —</option>
                {[0, 1, 2, 3, 4].map((g) => (
                  <option key={g} value={g}>{g} · {ICDR_LABELS[g]}</option>
                ))}
              </select>
            </label>
            <label style={{ fontSize: ".84rem", display: "block", marginTop: 10 }}>
              <span className="muted">Notes</span>
              <textarea
                value={notes} onChange={(e) => setNotes(e.target.value)} rows={3}
                style={{
                  width: "100%", marginTop: 5, padding: "9px 11px",
                  border: "1px solid var(--line-2)", borderRadius: 6,
                  background: "var(--surface)", color: "var(--ink)", fontFamily: "inherit",
                }}
              />
            </label>
            <div style={{ display: "flex", gap: 8, marginTop: 14, flexWrap: "wrap" }}>
              <button className="primary" onClick={() => decide(true)}>Agree</button>
              <button className="ghost" onClick={() => decide(false)}>Disagree</button>
              <button className="ghost" onClick={() => setI((x) => Math.min(x + 1, pending.length - 1))}>
                Skip
              </button>
            </div>
            <p className="muted" style={{ fontSize: ".76rem", marginTop: 10 }}>
              Time to decide is measured from when this card rendered, and stored with your
              answer. That is how we report the &lt;30 s target instead of asserting it.
            </p>
            {saved && <p style={{ fontSize: ".84rem", color: "var(--teal)" }}>{saved}</p>}
          </div>
        </div>
      )}
    </Shell>
    </Guard>
  );
}
