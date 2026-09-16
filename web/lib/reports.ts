// Typed client for the doctor-only report endpoints. Every call carries the session
// token; the API decides whether the caller may see anything.
import { authFetch } from "@/lib/auth";

export type ReportRow = {
  scan_id: string;
  created_at: string;
  ai_grade: number | null;
  ai_label: string | null;
  referable: boolean | null;
  confidence: number | null;
  rule_grade: number | null;
  rule_flag: string | null;
  escalated: boolean;
  quality_status: "pass" | "refused" | "unknown";
  quality_score: number | null;
  recapture_instruction: string | null;
  explanation_available: boolean;
  screening_reviewed: boolean;
  review_status: string;
  review_status_label: string;
  reviewed_at: string | null;
};

export type ReportDetail = {
  scan_id: string;
  created_at: string;
  model_id: string | null;
  synthetic_demo_model?: boolean;
  evidence_available: boolean;
  timing_ms: Record<string, number> | null;
  ai: {
    icdr_grade: number | null; icdr_label: string | null; referable: boolean | null;
    confidence: number | null; confidence_calibrated: boolean | null;
    per_grade_probability: number[] | null; ordinal_score: number | null;
    threshold_set: string | null; unavailable_reason: string | null;
  };
  quality: {
    gradeable: boolean | null; overall_score: number | null;
    checks: Record<string, { passed: boolean; value: number; threshold: number; unit: string }> | null;
    enhanced: boolean | null; recapture_instruction: string | null;
  };
  lesions: Record<string, { count: number; by_quadrant: Record<string, number> }> | null;
  explain: {
    gradcam_available: boolean; gradcam_unavailable_reason: string | null;
    attention_summary: string | null;
    overlay_png_b64?: string; gradcam_png_b64?: string; lesion_overlay_png_b64?: string;
  };
  rule_engine: {
    rule_grade: number | null; rule_label: string | null; rule_referable: boolean | null;
    criteria_fired: string[] | null; agrees_with_cnn: boolean | null;
    referable_agrees: boolean | null; flag: string | null; flag_message: string | null;
    limitations: string[] | null;
  };
  screening_recommendation: {
    referral: boolean | null; recommendation: string | null;
    escalated: boolean; escalation_reason: string | null;
  };
  clinician_review: {
    status: string; status_label: string; clinician_grade: number | null;
    notes: string | null; reviewed_at: string | null;
  };
  clinician_review_history: Array<{
    status: string; status_label: string; clinician_grade: number | null;
    notes: string; reviewed_by: string; reviewed_at: string;
  }>;
};

export const REVIEW_STATUSES = [
  { value: "reviewed", label: "Reviewed" },
  { value: "needs_further_review", label: "Needs further review" },
  { value: "confirmed", label: "Confirmed" },
  { value: "disagreed", label: "Disagreed" },
] as const;

/** 403 carries the reason the UI has to show, so it is surfaced rather than thrown away. */
export class AccessError extends Error {
  code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function unwrap(r: Response) {
  if (r.ok) return r.json();
  const body = await r.json().catch(() => null);
  const e = body?.detail?.error;
  if (r.status === 403 || r.status === 401) {
    throw new AccessError(e?.code || "forbidden", e?.message || "Access denied.");
  }
  throw new Error(e?.message || `Request failed (${r.status})`);
}

export async function listReports(): Promise<{ reports: ReportRow[]; count: number }> {
  return unwrap(await authFetch("/v1/reports?limit=200"));
}

export async function getReport(scanId: string): Promise<ReportDetail> {
  return unwrap(await authFetch(`/v1/reports/${encodeURIComponent(scanId)}`));
}

export async function submitClinicianReview(scanId: string, body: {
  status: string; notes: string; clinician_grade: number | null;
}) {
  return unwrap(await authFetch(`/v1/reports/${encodeURIComponent(scanId)}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}
