// Typed client for the CareBridge Eye Health Passport.
//
// Note what this file does NOT do: it does not add a field to `AnalyzeResult`. The
// longitudinal record is fetched by its own endpoints AFTER a screening completes, so
// the /v1/analyze contract is untouched — a screening result must not start depending
// on how many times the person has been screened before.
//
// Every call carries the session token; the API decides what exists. Nothing here
// names a patient, and the only ids it handles are opaque internal ones.
import { authFetch } from "@/lib/auth";

/** One point on the ICDR Grade Timeline. `icdr_grade` is null for a refused image. */
export type TimelinePoint = {
  screening_id: string;
  date: string;
  icdr_grade: number | null;
  severity_label: string | null;
  quality_status: "pass" | "refused" | "unknown";
  gradeable: boolean | null;
  referable: boolean | null;
  confidence: number | null;
  report_available: boolean;
  clinician_review_status: string;
  clinician_grade: number | null;
};

export type ComparisonSide = {
  screening_id: string;
  date: string;
  icdr_grade: number | null;
  severity_label: string | null;
  referable: boolean | null;
  confidence: number | null;
  quality_status: string;
  report_available: boolean;
  clinician_review_status: string;
  clinician_grade: number | null;
  clinician_reviewed_at: string | null;
};

/** The comparison, or an explicit reason there is none. Never a bare null. */
export type Comparison =
  | {
      available: true;
      previous: ComparisonSide;
      current: ComparisonSide;
      previous_grade: number;
      current_grade: number;
      grade_change: number;
      change_direction: "higher" | "lower" | "same";
      change_label: string;
      statement: string;
      quality_change: { previous: string; current: string; changed: boolean };
      referral_change: {
        previous: boolean | null; current: boolean | null;
        newly_referable: boolean; no_longer_referable: boolean;
      };
      clinician_review_change: { previous: string; current: string };
      interval_days: number | null;
      disclaimer: string;
    }
  | { available: false; reason: string; disclaimer: string };

export type FollowUp = {
  follow_up_id: string;
  account_id: string;
  screening_id: string;
  created_at: string;
  recommended_window: {
    min_months: number; max_months: number; label: string;
    priority: "routine" | "soon" | "prompt" | "urgent";
    headline: string;
  };
  due_at: string | null;
  basis: string;
  basis_label: string;
  basis_note: string;
  reason: string;
  clinician_override: boolean;
  status: "scheduled" | "due" | "completed" | "superseded";
  reminder_status: "pending" | "sent" | "failed";
  channel: string;
  priority: "routine" | "soon" | "prompt" | "urgent";
  referral_indicated: boolean;
  specialist_referral: boolean;
};

export type Passport = {
  enabled: boolean;
  history_count: number;
  has_history: boolean;
  returning_patient: boolean;
  timeline: TimelinePoint[];
  latest_screening: TimelinePoint | null;
  latest_comparison: Comparison | null;
  follow_up: FollowUp | null;
  follow_up_history: FollowUp[];
  disclaimer: string;
};

/** The probe the screening page runs BEFORE an upload, to know who is returning. */
export type PassportStatus = {
  has_history: boolean;
  history_count: number;
  last_screening: TimelinePoint | null;
  follow_up: FollowUp | null;
};

export type PatientHistory = {
  patient_id: string;
  anonymised: boolean;
  history_count: number;
  timeline: TimelinePoint[];
  comparisons: Extract<Comparison, { available: true }>[];
  latest_comparison: Extract<Comparison, { available: true }> | null;
  follow_up: FollowUp | null;
  follow_up_history: FollowUp[];
  disclaimer: string;
  note: string;
};

/** Mirrors `WhatsAppSendResponse`: the same provider, so the same honest shape. */
export type SendResponse = {
  success: boolean;
  channel: "whatsapp";
  message: string;
  to_masked?: string;
  sent_at?: string | null;
  message_sid?: string | null;
  status?: string | null;
  duplicate?: boolean;
  code?: string;
};

async function unwrap<T>(r: Response): Promise<T> {
  if (r.ok) return r.json() as Promise<T>;
  const body = await r.json().catch(() => null);
  const e = body?.detail?.error;
  throw new Error(e?.message || `Request failed (${r.status})`);
}

export async function getPassport(): Promise<Passport> {
  return unwrap(await authFetch("/v1/passport"));
}

export async function getPassportStatus(): Promise<PassportStatus> {
  return unwrap(await authFetch("/v1/passport/status"));
}

export async function getComparison(screeningId: string): Promise<Comparison> {
  return unwrap(await authFetch(
    `/v1/passport/screenings/${encodeURIComponent(screeningId)}/comparison`));
}

/** Doctor-facing. 404 for a patient this doctor holds no grant for — see routes.py. */
export async function getPatientHistoryByScan(scanId: string): Promise<PatientHistory> {
  return unwrap(await authFetch(`/v1/passport/by-scan/${encodeURIComponent(scanId)}`));
}

export async function setClinicianFollowUp(accountId: string, body: {
  screening_id: string; follow_up_months: number; reason: string;
  priority: FollowUp["priority"] | null;
}) {
  return unwrap(await authFetch(
    `/v1/passport/patients/${encodeURIComponent(accountId)}/follow-up`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }));
}

/**
 * Ask the backend to deliver the comparison report.
 *
 * Never throws for a delivery failure, for the same reason `sendReportOnWhatsApp` does
 * not: a refusal is a `success: false` answer the card renders, because the comparison
 * on the page must survive a messaging problem.
 */
export async function sendComparisonOnWhatsApp(
  screeningId: string, language: string,
): Promise<SendResponse> {
  const r = await authFetch(
    `/v1/passport/screenings/${encodeURIComponent(screeningId)}/comparison/whatsapp`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language }),
    });
  const body = await r.json().catch(() => null);
  if (r.ok && body?.success) return body as SendResponse;
  return {
    success: false, channel: "whatsapp",
    message: body?.message || body?.detail?.error?.message || "",
    code: body?.code || body?.detail?.error?.code,
  };
}

export async function sendFollowUpReminder(
  followUpId: string, language: string,
): Promise<SendResponse> {
  const r = await authFetch(
    `/v1/passport/follow-up/${encodeURIComponent(followUpId)}/reminder`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language }),
    });
  const body = await r.json().catch(() => null);
  if (r.ok && body?.success) return body as SendResponse;
  return {
    success: false, channel: "whatsapp",
    message: body?.message || body?.detail?.error?.message || "",
    code: body?.code || body?.detail?.error?.code,
  };
}

/**
 * Download the comparison PDF through the session.
 *
 * Returns false when there is nothing to download, so the caller can say so rather than
 * handing the browser an error page. The blob URL is revoked immediately — a clinical
 * document should not stay addressable in the tab after the download starts.
 */
export async function downloadComparisonPdf(screeningId: string): Promise<boolean> {
  const r = await authFetch(
    `/v1/passport/screenings/${encodeURIComponent(screeningId)}/comparison.pdf`);
  if (!r.ok) return false;
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `carebridge-comparison-${screeningId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
  return true;
}

/** Grade -> the status vocabulary the whole product already uses for a verdict. */
export function gradeTone(grade: number | null | undefined): "clear" | "warn" | "refer" | "none" {
  if (grade === null || grade === undefined) return "none";
  if (grade >= 3) return "refer";
  if (grade >= 2) return "warn";
  return "clear";
}

export function shortDate(iso: string | null | undefined, locale?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale, { day: "2-digit", month: "short", year: "numeric" });
}

export function monthYear(iso: string | null | undefined, locale?: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale, { month: "short", year: "numeric" });
}
