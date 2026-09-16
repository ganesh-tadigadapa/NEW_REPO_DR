"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Guard from "@/components/Guard";
import Shell from "@/components/Shell";
import Samples, { type Sample } from "@/components/Samples";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import LanguageOnboarding from "@/components/carebridge/LanguagePicker";
import CareResult from "@/components/carebridge/CareResult";
import ComparisonCard from "@/components/passport/ComparisonCard";
import ComparisonDelivery from "@/components/passport/ComparisonDelivery";
import FollowUpCard from "@/components/passport/FollowUpCard";
import GradeTimeline from "@/components/passport/GradeTimeline";
import ReturningBanner from "@/components/passport/ReturningBanner";
import { analyze, downscale, type AnalyzeResult } from "@/lib/api";
import { getPassport, type Passport } from "@/lib/passport";

export default function Screen() {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<AnalyzeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [patientRef, setPatientRef] = useState("");
  const [over, setOver] = useState(false);
  const [elapsed, setElapsed] = useState<number | null>(null);
  const [sampleNote, setSampleNote] = useState<string | null>(null);
  /**
   * The longitudinal answer for the screening that just finished.
   *
   * Fetched SEPARATELY, after `/v1/analyze` has returned, and deliberately so: the
   * analyse response contract is unchanged, and a screening result must not start
   * depending on how many times this person has been screened before. A failure here
   * leaves the result on the page untouched.
   */
  const [passport, setPassport] = useState<Passport | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const { t, tList } = useCareBridge();

  /**
   * Bring the finished result into view.
   *
   * CareResult renders full width BELOW the upload form and the samples grid, which puts
   * it roughly 2000px down the page — about two screens below the fold on a laptop. The
   * screening itself is fine, but nothing in the visible area changes when it lands, and
   * the "what you get" card that was sitting there is replaced by the result further
   * down. Clicking a sample therefore looked like it did nothing at all.
   *
   * A refusal (HTTP 422) sets `result` on the same path, so the recapture instruction
   * scrolls into view too — that message is useless to a health worker who cannot see it.
   */
  useEffect(() => {
    if (!result) return;
    const el = resultRef.current;
    if (!el) return;
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches;
    el.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "start" });
  }, [result]);

  const run = useCallback(async (file: File, note?: string) => {
    setBusy(true); setError(null); setResult(null); setElapsed(null);
    setPassport(null);
    setSampleNote(note ?? null);
    setPreview(URL.createObjectURL(file));
    const t0 = performance.now();
    try {
      const small = await downscale(file);
      const r = await analyze(small, patientRef || undefined);
      setResult(r);
      setElapsed(Math.round(performance.now() - t0));
      // The comparison, the updated timeline and the next follow-up. Best effort: the
      // screening result above is already on the page and stays there if this fails.
      getPassport().then(setPassport).catch(() => setPassport(null));
    } catch (e: any) {
      setError(e?.message || t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }, [patientRef, t]);

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
    <Guard>
    <Shell>
      {/* Shown only until the person has actually chosen a language. */}
      <LanguageOnboarding />
      {/* "Your previous screening is available." Renders nothing for a first-time
          patient, and asks the server rather than guessing from this browser. */}
      <ReturningBanner />
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
              {busy
                ? <><span className="spin" /> {t("screen.analyzing")}</>
                : t("screen.upload")}
            </div>
            <div className="muted" style={{ fontSize: ".84rem" }}>
              {busy ? t("screen.analyzingHint") : t("screen.uploadHint")}
            </div>
          </div>

          <label style={{ fontSize: ".84rem" }}>
            <span className="muted">{t("screen.patientRef")}</span>
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
                {t("screen.asUploaded")}
              </figcaption>
            </figure>
          )}
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {error && <div className="err">{error}</div>}

          {!result && !busy && !error && (
            <div className="card">
              <div className="eyebrow">{t("screen.whatYouGetTitle")}</div>
              <ul style={{ fontSize: ".88rem", color: "var(--ink-2)", paddingLeft: 18 }}>
                {tList("screen.whatYouGet").map((line, i) => <li key={i}>{line}</li>)}
              </ul>
            </div>
          )}

          {sampleNote && (
            <div className="muted" style={{ fontSize: ".8rem" }}>{sampleNote}</div>
          )}

          {busy && (
            <div className="card">
              <div className="eyebrow">{t("common.appName")}</div>
              <p style={{ margin: "8px 0 0" }}>
                <span className="spin" /> {t("screen.analyzing")}
              </p>
              <p className="muted" style={{ fontSize: ".84rem", margin: "6px 0 0" }}>
                {t("screen.analyzingHint")}
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Same AnalyzeResult, presented for the person it is about. CareResult re-orders
          and translates; it renders the existing clinical components unchanged inside
          its clinical section, and calls nothing. Full width, because a patient reading
          their own result should not be doing it in a side column. */}
      {result && (
        <div className="cb-results" ref={resultRef}>
          <CareResult r={result} onDownload={downloadPdf} />

          {/* ---- CareBridge Eye Health Passport -------------------------------
              What changed since last time, the timeline it sits on, the follow-up
              that comes out of it, and the comparison report on WhatsApp. All of it
              is drawn from the passport endpoints; none of it can change the result
              above. */}
          {passport?.has_history && (
            <>
              <ComparisonCard comparison={passport.latest_comparison} />
              {passport.timeline.length > 1 && (
                <section className="cb-section" aria-labelledby="pp-scr-tl">
                  <h3 id="pp-scr-tl" className="cb-h">
                    {t("passport.timelineTitle")}
                  </h3>
                  <GradeTimeline points={passport.timeline} />
                </section>
              )}
              <FollowUpCard followUp={passport.follow_up} />
              {passport.latest_comparison?.available && (
                <ComparisonDelivery screeningId={result.scan_id} />
              )}
            </>
          )}
          {elapsed !== null && (
            <div className="muted mono" style={{ fontSize: ".76rem" }}>
              {elapsed} ms end-to-end from this browser · scan {result.scan_id}
            </div>
          )}
        </div>
      )}
    </Shell>
    </Guard>
  );
}
