"use client";
/**
 * The comparison report, on the phone the patient already has.
 *
 * Structurally a sibling of `carebridge/WhatsAppDelivery.tsx` and it keeps the same
 * three rules, because they are what make the channel safe:
 *
 *   1. **The patient never types their number.** The recipient is the authenticated
 *      account's verified mobile, read server-side. This component only ever sees the
 *      masked form, and only to show it back.
 *   2. **Success is never assumed.** The sent state renders only after the backend
 *      confirms the provider accepted the message. No optimistic update.
 *   3. **Failure costs nothing.** The comparison stays on the page and the PDF stays
 *      downloadable — and the download button below is here, visible, in every state,
 *      rather than appearing only once something has gone wrong.
 */
import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import { downloadComparisonPdf, sendComparisonOnWhatsApp } from "@/lib/passport";
import { errorKey, isConfigurationProblem } from "@/lib/whatsapp";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";

type Phase = "idle" | "sending" | "sent" | "error";

export default function ComparisonDelivery({ screeningId }: { screeningId: string }) {
  const { t, lang } = useCareBridge();
  const { authenticated, account } = useAuth();
  const [phase, setPhase] = useState<Phase>("idle");
  const [code, setCode] = useState<string | undefined>();
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [sentStatus, setSentStatus] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState(false);
  // A ref, not state: the lock has to be correct DURING the click handler, before React
  // has re-rendered. That is the double-click race.
  const inFlight = useRef(false);

  const send = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPhase("sending");
    setCode(undefined);
    try {
      // The patient's CURRENT CareBridge language travels with the request. There is no
      // separate WhatsApp language preference, and there must not be one.
      const res = await sendComparisonOnWhatsApp(screeningId, lang);
      if (res.success) {
        setSentTo(res.to_masked || account?.mobile_masked || null);
        setSentStatus(res.status ?? null);
        setPhase("sent");
      } else {
        setCode(res.code);
        setPhase("error");
      }
    } catch {
      setCode(undefined);
      setPhase("error");
    } finally {
      inFlight.current = false;
    }
  }, [screeningId, lang, account?.mobile_masked]);

  const download = useCallback(async () => {
    setDownloading(true);
    setDownloadError(false);
    try {
      const ok = await downloadComparisonPdf(screeningId);
      setDownloadError(!ok);
    } catch {
      setDownloadError(true);
    } finally {
      setDownloading(false);
    }
  }, [screeningId]);

  if (!authenticated || !account) return null;
  const masked = sentTo || account.mobile_masked;
  const configProblem = phase === "error" && isConfigurationProblem(code);

  return (
    <section className={`cb-section cb-whatsapp${phase === "sent" ? " sent" : ""}`}
             aria-labelledby="pp-send-h">
      <div className="eyebrow"><span aria-hidden="true">📲</span> {t("whatsapp.eyebrow")}</div>
      <h3 id="pp-send-h" className="cb-h">{t("passport.sendTitle")}</h3>
      <p className="cb-lede">{t("passport.sendBody")}</p>

      <div className="cb-wacard">
        <div className="cb-warow">
          <span className="cb-waicon" aria-hidden="true">💬</span>
          <div className="cb-wato">
            <span className="cb-label">
              {phase === "sent" ? t("whatsapp.channelLabel")
                                : t("whatsapp.verifiedNumberIntro")}
            </span>
            {/* The masked number. The full one never crosses into this browser. */}
            <strong className="mono cb-wanumber">{masked}</strong>
          </div>
        </div>

        {phase === "sent" ? (
          <div className="cb-wasuccess">
            <div className="cb-watick" aria-hidden="true">✓</div>
            <div>
              <h4>{t("passport.sendSentTitle")}</h4>
              <p>{t("passport.sendSentBody")}</p>
              <p className="mono cb-wanumber">{masked}</p>
              <p className="cb-note">{t("whatsapp.successHint")}</p>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="cb-wasend"
            onClick={send}
            // A configuration refusal answers identically however many times it is
            // pressed, so the button stops inviting a retry that cannot succeed.
            disabled={phase === "sending" || configProblem}
            aria-busy={phase === "sending"}
            aria-describedby="pp-send-status"
          >
            {phase === "sending"
              ? <><span className="spin" aria-hidden="true" /> {t("passport.sendSending")}</>
              : phase === "error" && !configProblem
                ? <><span aria-hidden="true">↻</span> {t("passport.sendRetry")}</>
                : phase === "error"
                  ? <><span aria-hidden="true">⚠</span> {t("passport.sendFailed")}</>
                  : <><span aria-hidden="true">💬</span> {t("passport.sendButton")}</>}
          </button>
        )}

        <p id="pp-send-status" className="cb-wastatus" role="status" aria-live="polite">
          {phase === "sending" && t("passport.sendSending")}
          {phase === "sent" && (sentStatus === "queued" || sentStatus === "accepted"
            ? t("passport.sendQueued") : t("whatsapp.sentShort"))}
          {phase === "error" && (
            <span className="cb-waerror">
              <span aria-hidden="true">⚠</span>{" "}
              {code === "comparison_not_available"
                ? t("passport.sendNotAvailable") : t(errorKey(code))}
            </span>
          )}
          {phase === "idle" && t("whatsapp.explain")}
        </p>

        {/* Present in EVERY state, not only after a failure. The promise that the
            comparison is reachable without WhatsApp is only true if the button is
            there before anyone needs it. */}
        <div className="pp-dlrow">
          <button type="button" className="ghost" onClick={download}
                  disabled={downloading} aria-busy={downloading}>
            {downloading
              ? <><span className="spin" aria-hidden="true" /> {t("passport.downloading")}</>
              : <><span aria-hidden="true">📄</span> {t("passport.download")}</>}
          </button>
          {downloadError && (
            <span className="cb-waerror">{t("passport.downloadFailed")}</span>
          )}
        </div>
      </div>

      <p className="cb-note">{t("passport.alsoDownload")}</p>
    </section>
  );
}
