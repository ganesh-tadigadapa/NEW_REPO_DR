"use client";
/**
 * CareBridge — WhatsApp report delivery.
 *
 * READ THIS BEFORE EDITING. This component performs no analysis and displays no clinical
 * value. It knows one thing about the screening: whether a report was generated. The
 * grade, the referral and the explanation are already on the page above it, and the
 * message WhatsApp carries is composed by the backend from that same screening result.
 *
 * It closes the last gap in the patient journey:
 *
 *      screen → understand → report → WhatsApp
 *
 * The report does not stay trapped inside a website the patient may never open again; it
 * arrives on the phone they already have, at the number they already proved is theirs.
 *
 * Three rules this component keeps:
 *
 *   1. **The patient never types their number.** The recipient is the authenticated
 *      account's registered mobile, derived server-side. This component only ever sees
 *      the MASKED form, and only to show it back.
 *   2. **Success is never assumed.** The success state renders only after the backend
 *      confirms Twilio accepted the message. There is no optimistic update and no local
 *      "probably fine" path.
 *   3. **Failure costs nothing.** WhatsApp is an optional channel. Every failure leaves
 *      the result, the explanation and the downloadable PDF exactly where they were.
 */
import { useCallback, useRef, useState } from "react";
import { useAuth } from "@/components/AuthProvider";
import type { AnalyzeResult } from "@/lib/api";
import {
  errorKey, isConfigurationProblem, sendReportOnWhatsApp,
} from "@/lib/whatsapp";
import { useCareBridge } from "./CareBridgeProvider";

type Phase = "idle" | "sending" | "sent" | "error";

/** The journey rail. Four steps that have already happened, plus the one being offered. */
function JourneyRail({ delivered }: { delivered: boolean }) {
  const { t } = useCareBridge();
  const steps = [
    { icon: "👁", label: t("whatsapp.journeyScreen"), done: true },
    { icon: "💡", label: t("whatsapp.journeyUnderstand"), done: true },
    { icon: "📄", label: t("whatsapp.journeyReport"), done: true },
    { icon: "💬", label: t("whatsapp.journeyDeliver"), done: delivered },
  ];
  return (
    <ol className="cb-wajourney" aria-hidden="true">
      {steps.map((s) => (
        <li key={s.label} className={s.done ? "done" : ""}>
          <span className="cb-wastep">{s.icon}</span>
          <span className="cb-walabel">{s.label}</span>
        </li>
      ))}
    </ol>
  );
}

export default function WhatsAppDelivery({ r }: { r: AnalyzeResult }) {
  const { t, lang } = useCareBridge();
  const { authenticated, account } = useAuth();
  const [phase, setPhase] = useState<Phase>("idle");
  const [errorCode, setErrorCode] = useState<string | undefined>();
  const [sentTo, setSentTo] = useState<string | null>(null);
  // Twilio's own status word for the accepted message. "queued"/"accepted" means Twilio
  // took it, NOT that the patient has it, and the status line says exactly that.
  const [sentStatus, setSentStatus] = useState<string | null>(null);
  // The in-flight lock. A ref rather than state because it has to be correct DURING the
  // click handler, before React has re-rendered — that is the double-click race.
  const inFlight = useRef(false);

  const send = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    setPhase("sending");
    setErrorCode(undefined);
    try {
      // The patient's CURRENT CareBridge language travels with the request. There is no
      // separate WhatsApp language preference, and there must not be one.
      const res = await sendReportOnWhatsApp(r.scan_id, lang);
      if (res.success) {
        setSentTo(res.to_masked || account?.mobile_masked || null);
        setSentStatus(res.status ?? null);
        setPhase("sent");
      } else {
        setErrorCode(res.code);
        setPhase("error");
      }
    } catch {
      setErrorCode(undefined);       // a transport failure: the generic sentence
      setPhase("error");
    } finally {
      inFlight.current = false;
    }
  }, [r.scan_id, lang, account?.mobile_masked]);

  // Nothing to deliver, or nobody to deliver it to. Both are silent: an offer the person
  // cannot take is noise on a page they are reading about their own eyes.
  if (!r.report?.pdf_b64) return null;
  if (!authenticated || !account) return null;

  const masked = sentTo || account.mobile_masked;
  const configProblem = phase === "error" && isConfigurationProblem(errorCode);

  return (
    <section
      className={`cb-section cb-whatsapp${phase === "sent" ? " sent" : ""}`}
      aria-labelledby="cb-wa-h"
    >
      <div className="eyebrow"><span aria-hidden="true">📲</span> {t("whatsapp.eyebrow")}</div>
      <h3 id="cb-wa-h" className="cb-h">{t("whatsapp.readyTitle")}</h3>
      <p className="cb-lede">{t("whatsapp.readyBody")}</p>

      <JourneyRail delivered={phase === "sent"} />

      <div className="cb-wacard">
        <div className="cb-warow">
          <span className="cb-waicon" aria-hidden="true">💬</span>
          <div className="cb-wato">
            {/* Before sending, name the destination explicitly — the patient should know
                which number this is going to BEFORE they tap, not after. Once sent, the
                channel label reads better above the number it went to. */}
            <span className="cb-label">
              {phase === "sent"
                ? t("whatsapp.channelLabel")
                : t("whatsapp.verifiedNumberIntro")}
            </span>
            {/* The masked number. The full one is never sent to this browser. */}
            <strong className="mono cb-wanumber">{masked}</strong>
          </div>
        </div>

        {phase === "sent" ? (
          <div className="cb-wasuccess">
            <div className="cb-watick" aria-hidden="true">✓</div>
            <div>
              <h4>{t("whatsapp.successTitle")}</h4>
              <p>{t("whatsapp.successBody")}</p>
              <p className="mono cb-wanumber">{masked}</p>
              <p className="cb-note">{t("whatsapp.successHint")}</p>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="cb-wasend"
            onClick={send}
            // A configuration or account-tier refusal will answer identically however
            // many times it is pressed, so the button stops inviting a retry that cannot
            // succeed. The report stays downloadable either way — see the hint below.
            disabled={phase === "sending" || configProblem}
            aria-busy={phase === "sending"}
            // The accessible name is the VISIBLE text, deliberately. An aria-label
            // saying something longer would break WCAG 2.5.3 (Label in Name) and stop
            // voice control from activating the button by the words written on it. The
            // longer explanation — and, after a failure, the reason — is the live status
            // paragraph below, which this points at.
            aria-describedby="cb-wa-status"
          >
            {phase === "sending" ? (
              <><span className="spin" aria-hidden="true" /> {t("whatsapp.sending")}</>
            ) : phase === "error" && !configProblem ? (
              <><span aria-hidden="true">↻</span> {t("whatsapp.retry")}</>
            ) : phase === "error" ? (
              <><span aria-hidden="true">⚠</span> {t("whatsapp.failedShort")}</>
            ) : (
              <><span aria-hidden="true">💬</span> {t("whatsapp.send")}</>
            )}
          </button>
        )}

        {/* One live region for every outcome, so a screen reader hears the change rather
            than having to go looking for it. */}
        <p id="cb-wa-status" className="cb-wastatus" role="status" aria-live="polite">
          {phase === "sending" && t("whatsapp.sending")}
          {phase === "sent" && (sentStatus === "queued" || sentStatus === "accepted"
            ? t("whatsapp.queuedShort") : t("whatsapp.sentShort"))}
          {phase === "error" && (
            <span className="cb-waerror">
              <span aria-hidden="true">⚠</span> {t(errorKey(errorCode))}
            </span>
          )}
          {phase === "idle" && t("whatsapp.explain")}
        </p>

        {configProblem && (
          <p className="cb-note">{t("whatsapp.errors.notConfiguredHint")}</p>
        )}
      </div>

      <p className="cb-note">
        {phase === "idle" ? t("whatsapp.registeredNote") : t("whatsapp.alsoDownload")}
      </p>
    </section>
  );
}
