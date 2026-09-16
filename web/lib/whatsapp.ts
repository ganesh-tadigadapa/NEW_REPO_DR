// Client for WhatsApp report delivery.
//
// Note what this file does NOT contain: a phone number, a Twilio credential, a Twilio
// URL, or any way to name a recipient. The backend reads the number off the
// authenticated session, so the request body carries one thing — which language the
// message should be written in — and the browser never learns or handles the number in
// full. The masked form shown in the UI comes from /v1/auth/session, which is the
// caller's own account.
import { authFetch } from "@/lib/auth";
import type { StringKey } from "@/lib/i18n";

export type WhatsAppSendResponse = {
  success: boolean;
  channel: "whatsapp";
  message: string;
  /** "+91 ***** 43210". Present on success; the full number never crosses this boundary. */
  to_masked?: string;
  sent_at?: string | null;
  /** Twilio's own message SID, passed through by the backend. Present only when Twilio
   *  actually accepted the message, so it is the one honest proof of a real send. */
  message_sid?: string | null;
  /** Twilio's status word: normally "queued"/"accepted" at this point, not "delivered".
   *  The UI reports acceptance, never receipt. */
  status?: string | null;
  /** True when the report had already been delivered moments ago and was not re-sent. */
  duplicate?: boolean;
  /** A stable code, mapped to a translated sentence by `errorKey` below. */
  code?: string;
};

/**
 * Backend code -> translation key.
 *
 * Deliberately a lookup rather than a rendered sentence from the server: the server
 * answers in one language, and the patient reads in theirs. An unrecognised code falls
 * through to the generic sentence — never to a raw provider string.
 */
const ERROR_KEYS: Record<string, StringKey> = {
  not_configured: "whatsapp.errors.notConfigured",
  provider_unconfigured: "whatsapp.errors.notConfigured",
  provider_trial_limited: "whatsapp.errors.trialLimited",
  sender_not_whatsapp: "whatsapp.errors.notConfigured",
  recipient_not_reachable: "whatsapp.errors.notReachable",
  // Meta-only: the WhatsApp app is still in test mode and this number has not been
  // added to its allow-list in the Meta console. An operator action, not a patient one.
  recipient_not_allowed: "whatsapp.errors.recipientNotAllowed",
  session_window_closed: "whatsapp.errors.sessionClosed",
  invalid_recipient: "whatsapp.errors.invalidRecipient",
  recipient_opted_out: "whatsapp.errors.optedOut",
  rate_limited: "whatsapp.errors.rateLimited",
  media_unreachable: "whatsapp.errors.mediaUnreachable",
  provider_unreachable: "whatsapp.errors.unreachable",
  report_not_ready: "whatsapp.errors.reportMissing",
  report_not_found: "whatsapp.errors.reportMissing",
  already_sending: "whatsapp.errors.alreadySending",
};

export function errorKey(code?: string): StringKey {
  return (code && ERROR_KEYS[code]) || "whatsapp.errors.generic";
}

/** Codes that mean "this will never work until an operator changes something", as
 *  opposed to "try again". The UI offers Retry only for the second kind. */
export function isConfigurationProblem(code?: string): boolean {
  return code === "not_configured" || code === "provider_unconfigured"
    || code === "sender_not_whatsapp" || code === "provider_trial_limited"
    // Retrying will answer identically until someone adds the number in the Meta
    // console, so the button stops inviting a retry that cannot succeed.
    || code === "recipient_not_allowed";
}

/**
 * Ask the backend to deliver an already-generated report.
 *
 * Never throws for a delivery failure: a refusal is a `success: false` answer the card
 * renders, because the screening result on the page must survive a messaging problem.
 * The only throw is a transport failure, and the caller treats that as a generic error.
 */
export async function sendReportOnWhatsApp(
  scanId: string, language: string,
): Promise<WhatsAppSendResponse> {
  const r = await authFetch(`/v1/reports/${encodeURIComponent(scanId)}/whatsapp`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });
  const body = await r.json().catch(() => null);
  if (r.ok && body?.success) return body as WhatsAppSendResponse;
  return {
    success: false,
    channel: "whatsapp",
    message: body?.message || body?.detail?.error?.message || "",
    code: body?.code || body?.detail?.error?.code,
  };
}
