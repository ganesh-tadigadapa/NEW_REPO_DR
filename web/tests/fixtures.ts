/**
 * A screening result shaped exactly like docs/API_CONTRACT.md v1 returns one.
 *
 * Checked against a live /v1/analyze response for web/public/samples/aptos-grade2.png and
 * aptos-ungradeable-focus.png. The live payload also carries `patient_ref`, which this
 * fixture deliberately omits: it is not in the AnalyzeResult type and no component — in
 * CareBridge or anywhere else — may display it.
 */
import type { AnalyzeResult } from "@/lib/api";

export function makeResult(over: Partial<AnalyzeResult> = {}): AnalyzeResult {
  return {
    scan_id: "scan_test_0001",
    created_at: "2026-09-16T09:00:00Z",
    model_id: "effnetv2s-coral-v1",
    disclaimer: "Screening triage aid — not a diagnostic device",
    synthetic_demo_model: false,
    quality: {
      gradeable: true,
      overall_score: 0.88,
      checks: {
        focus: { passed: true, value: 0.71, threshold: 0.4, unit: "norm" },
        illumination: { passed: true, value: 0.63, threshold: 0.3, unit: "norm" },
        field_of_view: { passed: true, value: 0.92, threshold: 0.6, unit: "frac" },
      },
      enhanced: false,
      recapture_instruction: null,
      thresholds_fitted: true,
    },
    grading: {
      icdr_grade: 2,
      icdr_label: "Moderate NPDR",
      referable: true,
      referable_probability: 0.81,
      ordinal_score: 2.1,
      confidence: 0.77,
      confidence_calibrated: true,
      per_grade_probability: [0.04, 0.11, 0.62, 0.18, 0.05],
      threshold_set: "frozen-v1",
    },
    lesions: {
      microaneurysms: { count: 12, by_quadrant: { ST: 4, SN: 3, IT: 3, IN: 2 } },
      haemorrhages: { count: 5, by_quadrant: { ST: 2, SN: 1, IT: 1, IN: 1 } },
      hard_exudates: { count: 3, by_quadrant: { ST: 1, SN: 1, IT: 1, IN: 0 } },
      method: "classical-cv",
    },
    rule_check: {
      rule_grade: 2,
      rule_label: "Moderate NPDR",
      rule_referable: true,
      criteria_fired: ["microaneurysms present in 4 quadrants"],
      four_two_one: {},
      agrees_with_cnn: true,
      referable_agrees: true,
      flag: null,
      flag_message: null,
      recommendation: null,
      assessable_ceiling: 3,
      limitations: ["neovascularisation is not detected by these rules"],
    },
    explain: {
      gradcam_available: true,
      overlay_png_b64: "iVBORw0KGgo=",
      lesion_overlay_png_b64: "iVBORw0KGgo=",
      attention_summary: "Attention concentrated in the superior-temporal quadrant.",
    },
    report: { pdf_b64: "JVBERi0=", filename: "dr-report.pdf" },
    timing_ms: { quality: 40, grading: 180, explain: 95, total: 315 },
    ...over,
  };
}

/** The refusal the quality gate produces for an unreadable photograph. */
export function makeUngradeable(): AnalyzeResult {
  return makeResult({
    quality: {
      gradeable: false,
      overall_score: 0.21,
      checks: {
        focus: { passed: false, value: 0.08, threshold: 0.4, unit: "norm" },
        illumination: { passed: true, value: 0.55, threshold: 0.3, unit: "norm" },
        field_of_view: { passed: true, value: 0.88, threshold: 0.6, unit: "frac" },
      },
      enhanced: true,
      recapture_instruction: "Image is out of focus. Refocus and retake.",
      thresholds_fitted: true,
    },
    grading: null,
    grading_unavailable_reason: "quality gate refused the image",
    lesions: null,
    rule_check: null,
    explain: null,
    report: null,
  });
}

/** A fake speech-synthesis implementation with a controllable voice list. */
export function installSpeech(voiceLangs: string[]) {
  const calls = { speak: 0, cancel: 0, lastText: "", lastLang: "" };
  const voices = voiceLangs.map((lang, i) => ({ lang, name: `voice-${i}`, default: i === 0 }));
  class FakeUtterance {
    text: string; lang = ""; rate = 1; voice: unknown = null;
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;
    constructor(text: string) { this.text = text; }
  }
  const synth = {
    getVoices: () => voices,
    speak: (u: FakeUtterance) => { calls.speak++; calls.lastText = u.text; calls.lastLang = u.lang; },
    cancel: () => { calls.cancel++; },
    addEventListener: () => {},
    removeEventListener: () => {},
  };
  Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true, writable: true });
  Object.defineProperty(window, "SpeechSynthesisUtterance", {
    value: FakeUtterance, configurable: true, writable: true,
  });
  return calls;
}

/** Remove speech synthesis entirely — an older browser, or a locked-down device. */
export function removeSpeech() {
  // @ts-expect-error deleting an optional browser API is the point of the test
  delete window.speechSynthesis;
  // @ts-expect-error same
  delete window.SpeechSynthesisUtterance;
}
