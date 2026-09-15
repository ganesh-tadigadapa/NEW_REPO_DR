"use client";
import { useCallback, useRef, useState } from "react";
import Shell from "@/components/Shell";
import {
  Confidence, Evidence, Images, QualityPanel, RulePanel, Timing, Verdict,
} from "@/components/Result";
import Samples, { type Sample } from "@/components/Samples";
import { analyze, downscale, type AnalyzeResult } from "@/lib/api";

export default function Screen() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [patientRef, setPatientRef] = useState("");
  const [over, setOver] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [sampleNote, setSampleNote] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const run = useCallback(async (file: File, note?: string) => {
    setBusy(true); setError(null); setResult(null); setElapsed(null);
    setSampleNote(note ?? null);
    setPreview(URL.createObjectURL(file));
    const t0 = performance.now();
    try {
      const small = await downscale(file);
      const r = await analyze(small, patientRef || undefined);
      setResult(r);
      setElapsed(Math.round(performance.now() - t0));
    } catch (e: any) {
      setError(e?.message || "something went wrong");
    } finally {
      setBusy(false);
    }
  }, [patientRef]);

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); setOver(false);
    const f = e.dataTransfer.files?.[0];
    if (f) run(f);
  };

  const downloadPdf = () => {
    if (!result?.report?.pdf_b64) return;
    const bin = atob(result.report.pdf_b64);
    const arr = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
    const url = URL.createObjectURL(new Blob([arr], { type: "application/pdf" }));
    const a = document.createElement("a");
    a.href = url; a.download = result.report.filename || "dr-report.pdf";
    a.click(); URL.revokeObjectURL(url);
  };

  return (
    <Shell>
      <div className="grid2" style={{ alignItems: "start" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div
            className={`drop ${over ? "over" : ""}`}
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={onDrop}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => e.key === "Enter" && inputRef.current?.click()}
          >
            <input
              ref={inputRef} type="file" accept="image/*"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) run(f); }}
            />
            <div style={{ fontWeight: 600, marginBottom: 6 }}>
              {busy ? <><span className="spin" /> Analysing…</> : "Upload a fundus photograph"}
            </div>
            <div className="muted" style={{ fontSize: ".84rem" }}>
              Drag and drop, or tap to choose. Resized in your browser before upload.
            </div>
          </div>

          <label style={{ fontSize: ".84rem" }}>
            <span className="muted">Patient reference (optional)</span>
            <input
              value={patientRef}
              onChange={(e) => setPatientRef(e.target.value)}
              placeholder="PHC-2026-0001"
              style={{
                width: "100%", marginTop: 5, padding: "9px 11px",
                border: "1px solid var(--line-2)", borderRadius: 6,
                background: "var(--surface)", color: "var(--ink)", fontSize: ".9rem",
              }}
            />
          </label>

          <Samples
            disabled={busy}
            onPick={(f: File, sm: Sample) =>
              run(f, `Sample: ${sm.title} — expected to be ${sm.expect}.`)}
          />

          {preview && (
            <figure style={{ margin: 0 }}>
              <img
                src={preview} alt="uploaded fundus"
                style={{ width: "100%", borderRadius: 8, border: "1px solid var(--line)" }}
              />
              <figcaption className="muted" style={{ fontSize: ".74rem", marginTop: 6 }}>
                As uploaded
              </figcaption>
            </figure>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {error && <div className="err">{error}</div>}

          {!result && !busy && !error && (
            <div className="card">
              <div className="eyebrow">What you get back</div>
              <ul style={{ fontSize: ".88rem", color: "var(--ink-2)", paddingLeft: 18 }}>
                <li>An ICDR 0–4 severity grade and a referral decision</li>
                <li>A Grad-CAM heatmap of what the model looked at</li>
                <li>Lesion counts by quadrant, checked against the ICDR clinical rules</li>
                <li>A calibrated confidence, and a one-page PDF for sign-off</li>
                <li>Or a refusal with a specific instruction, if the image can’t be graded</li>
              </ul>
            </div>
          )}

          {sampleNote && (
            <div className="muted" style={{ fontSize: ".8rem" }}>{sampleNote}</div>
          )}

          {result && (
            <>
              <Verdict r={result} />
              {elapsed !== null && (
                <div className="muted mono" style={{ fontSize: ".76rem" }}>
                  {elapsed} ms end-to-end from this browser · scan {result.scan_id}
                </div>
              )}
              <QualityPanel r={result} />
              {result.report?.pdf_b64 && (
                <button className="primary" onClick={downloadPdf}>
                  Download one-page report (PDF)
                </button>
              )}
              <Images r={result} />
              <Evidence r={result} />
              <RulePanel r={result} />
              <Confidence r={result} />
              <Timing r={result} />
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}
