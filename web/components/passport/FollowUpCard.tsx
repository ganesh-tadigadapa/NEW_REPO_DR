"use client";
/**
 * The suggested follow-up, and the reminder that acts on it.
 *
 * READ THIS BEFORE EDITING. The window, the priority, the target date and the reason
 * are all decided by `src/passport/followup.py` from the programme's configured
 * guideline table. This component chooses no interval and applies no threshold — it
 * renders the plan it is handed.
 *
 * The wording is "suggested", never "you must". A clinician recommendation outranks the
 * table, and when one is in force the card says so rather than presenting it as the
 * system's own idea.
 */
import { useCallback, useRef, useState } from "react";
import { sendFollowUpReminder, shortDate, type FollowUp } from "@/lib/passport";
import { errorKey } from "@/lib/whatsapp";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import type { StringKey } from "@/lib/i18n";

const PRIORITY_KEY: Record<FollowUp["priority"], StringKey> = {
  routine: "passport.priorityRoutine",
  soon: "passport.prioritySoon",
  prompt: "passport.priorityPrompt",
  urgent: "passport.priorityUrgent",
};

type Phase = "idle" | "sending" | "sent" | "error";

export default function FollowUpCard({ followUp, canRemind = true }: {
  followUp: FollowUp | null;
  /** False on a page where a reminder makes no sense (a doctor reading a record). */
  canRemind?: boolean;
}) {
  const { t, lang, meta } = useCareBridge();
  const [phase, setPhase] = useState<Phase>("idle");
  const [code, setCode] = useState<string | undefined>();
  const inFlight = useRef(false);

  const send = useCallback(async () => {
    if (!followUp || inFlight.current) return;
    inFlight.current = true;
    setPhase("sending");
    setCode(undefined);
    try {
      const res = await sendFollowUpReminder(followUp.follow_up_id, lang);
      if (res.success) setPhase("sent");
      else { setCode(res.code); setPhase("error"); }
    } catch {
      setCode(undefined);
      setPhase("error");
    } finally {
      inFlight.current = false;
    }
  }, [followUp, lang]);

  if (!followUp) return null;
  const w = followUp.recommended_window;
  // The reminder status shown is the RECORDED one, until this page changes it.
  const reminded = phase === "sent" || followUp.reminder_status === "sent";

  return (
    <section className={`cb-section pp-followup pri-${followUp.priority}`}
             aria-labelledby="pp-fu-h">
      <div className="eyebrow">{t("passport.followUpSuggested")}</div>
      <h3 id="pp-fu-h" className="cb-h">{t("passport.followUpTitle")}</h3>

      <div className="pp-furow">
        <span className={`pill pp-pri pri-${followUp.priority}`}>
          {t(PRIORITY_KEY[followUp.priority])}
        </span>
        {/* The window as the plan worded it. It is a suggestion and it says so. */}
        <strong className="pp-fuwindow">{w.headline}: {w.label}</strong>
      </div>

      {followUp.due_at && (
        <p className="cb-note mono">
          {t("passport.followUpDue", { date: shortDate(followUp.due_at, meta.locale) })}
        </p>
      )}
      {followUp.status === "due" && (
        <div className="flagbox">{t("passport.followUpDueNow")}</div>
      )}

      <p className="cb-lede">{followUp.reason}</p>

      <p className="cb-note">
        <span className="eyebrow">{t("passport.followUpBasis")}</span>{" "}
        {/* `basis_label` already names the clinician when they set it outright; the
            extra sentence is only for the case where their GRADE drove the window. */}
        {followUp.basis_label}
        {followUp.basis === "clinician_grade"
          && ` · ${t("passport.followUpClinicianSet")}`}
      </p>

      {canRemind && (
        <div className="pp-remind">
          <button
            type="button"
            className="ghost"
            onClick={send}
            disabled={phase === "sending"}
            aria-busy={phase === "sending"}
            aria-describedby="pp-fu-status"
          >
            {phase === "sending"
              ? <><span className="spin" aria-hidden="true" /> {t("passport.followUpSending")}</>
              : <><span aria-hidden="true">🔔</span> {t("passport.followUpSendReminder")}</>}
          </button>
          <p id="pp-fu-status" className="cb-note" role="status" aria-live="polite">
            {phase === "error"
              ? <span className="cb-waerror">⚠ {t(errorKey(code))}</span>
              : reminded
                ? t("passport.followUpReminderSent")
                : followUp.reminder_status === "failed"
                  ? t("passport.followUpReminderFailed")
                  : t("passport.followUpReminderPending")}
          </p>
        </div>
      )}

      {/* Not a prescription. Stated on the card, in the reader's language. */}
      <p className="pp-caveat">{t("passport.followUpNote")}</p>
    </section>
  );
}
