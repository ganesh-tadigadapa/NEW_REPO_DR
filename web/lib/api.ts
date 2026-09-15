// Typed client for docs/API_CONTRACT.md v1. The contract is frozen; this file mirrors it.
export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") || "http://localhost:8080";

export type QualityCheck = {
  passed: boolean; value: number; threshold: number; unit: string;
};
export type Quality = {
  gradeable: boolean;
  overall_score: number;
  checks: Record<"focus" | "illumination" | "field_of_view", QualityCheck>;
  enhanced: boolean;
  recapture_instruction: string | null;
  thresholds_fitted?: boolean;
  threshold_source?: string;
};
export type Grading = {
  icdr_grade: number; icdr_label: string; referable: boolean;
  referable_probability: number; ordinal_score: number;
  confidence: number; confidence_calibrated: boolean;
  most_likely_grade?: number; grade_from_threshold_not_argmax?: boolean;
  per_grade_probability: number[]; threshold_set: string;
} | null;
export type LesionBlock = { count: number; by_quadrant: Record<string, number> };
export type Lesions = {
  microaneurysms: LesionBlock; haemorrhages: LesionBlock; hard_exudates: LesionBlock;
  method: string;
} | null;
export type RuleCheck = {
  rule_grade: number; rule_label: string; rule_referable: boolean;
  criteria_fired: string[];
  four_two_one: Record<string, unknown>;
  agrees_with_cnn: boolean | null;
  referable_agrees: boolean | null;
  flag: string | null; flag_message: string | null;
  recommendation: string | null;
  assessable_ceiling: number; limitations: string[];
} | null;
export type Explain = {
  gradcam_available: boolean;
  gradcam_unavailable_reason?: string | null;
  gradcam_png_b64?: string; overlay_png_b64?: string;
  lesion_overlay_png_b64?: string; attention_summary?: string;
} | null;
export type AnalyzeResult = {
  scan_id: string; created_at: string; model_id: string | null;
  disclaimer: string; synthetic_demo_model?: boolean;
  quality: Quality; grading: Grading;
  grading_unavailable_reason?: string | null;
  lesions: Lesions; rule_check: RuleCheck; explain: Explain;
  report: { pdf_b64?: string; filename?: string; error?: string } | null;
  timing_ms: Record<string, number>;
};
export type Health = {
  status: string; version: string; model_loaded: boolean; model_id: string;
  model_unavailable_reason: string | null; synthetic_demo_model?: boolean;
  store: string; disclaimer: string;
};

export async function getHealth(): Promise<Health> {
  const r = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!r.ok) throw new Error(`health ${r.status}`);
  return r.json();
}

/** 422 is a SUCCESSFUL refusal, not an error — it carries the recapture instruction. */
export async function analyze(file: File, patientRef?: string): Promise<AnalyzeResult> {
  const fd = new FormData();
  fd.append("file", file);
  if (patientRef) fd.append("patient_ref", patientRef);
  const r = await fetch(`${API_BASE}/v1/analyze`, { method: "POST", body: fd });
  const body = await r.json().catch(() => null);
  if (r.ok || r.status === 422) return body as AnalyzeResult;
  const msg = body?.detail?.error?.message || body?.error?.message || `request failed (${r.status})`;
  throw new Error(msg);
}

export async function submitReview(scanId: string, payload: {
  agrees: boolean; corrected_grade: number | null; notes: string; seconds_to_decide: number;
}) {
  const r = await fetch(`${API_BASE}/v1/review/${scanId}`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`review failed (${r.status})`);
  return r.json();
}

export async function getMetrics() {
  const r = await fetch(`${API_BASE}/v1/metrics`, { cache: "no-store" });
  return r.json();
}
export async function getOperational() {
  const r = await fetch(`${API_BASE}/v1/operational`, { cache: "no-store" });
  return r.json();
}

/**
 * Downscale before upload. A raw fundus JPEG is 4-6 MB and rural uplink is slow; 1024 px
 * is above the model's 512 px input so nothing diagnostic is lost, and it cuts a
 * 40-second upload to a few seconds. This is the single biggest UX win for the actual
 * deployment context, and it happens in the browser so the server never waits.
 */
export async function downscale(file: File, maxSide = 1024, quality = 0.92): Promise<File> {
  if (typeof window === "undefined") return file;
  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file;
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  if (scale >= 1) return file;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const blob: Blob | null = await new Promise((res) =>
    canvas.toBlob(res, "image/jpeg", quality));
  if (!blob) return file;
  return new File([blob], file.name.replace(/\.[^.]+$/, "") + ".jpg", { type: "image/jpeg" });
}

export const ICDR_LABELS: Record<number, string> = {
  0: "No DR", 1: "Mild NPDR", 2: "Moderate NPDR", 3: "Severe NPDR", 4: "Proliferative DR",
};
