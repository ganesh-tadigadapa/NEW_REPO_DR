"use client";
import { type AnalyzeResult } from "@/lib/api";

const QUADS = ["ST", "SN", "IT", "IN"] as const;
const QUAD_LABEL: Record<string, string> = {
  ST: "Sup-temporal", SN: "Sup-nasal", IT: "Inf-temporal", IN: "Inf-nasal",
};

function png(b64?: string) {
  return b64 ? `data:image/png;base64,${b64}` : undefined;
}

export function Verdict({ r }: { r: AnalyzeResult }) {
  // Three states, kept distinct: refused / graded-referable / graded-clear.
  if (!r.quality.gradeable) {
    return (
      <div className="verdict v-reject">
        <div>
          <h2>Image rejected — please retake</h2>
          <p className="body">{r.quality.recapture_instruction}</p>
        </div>
        <div className="mono" style={{ fontSize: ".75rem" }}>
          quality {(r.quality.overall_score * 100).toFixed(0)}%
        </div>
      </div>
    );
  }
  if (!r.grading) {
    return (
      <div className="verdict v-reject">
        <div>
          <h2>Model grade unavailable</h2>
          <p className="body">
            Image quality passed. Lesion evidence and the clinical-rule grade below are
            still valid. {r.grading_unavailable_reason}
          </p>
        </div>
      </div>
    );
  }
  const g = r.grading;
  return (
    <div className={`verdict ${g.referable ? "v-refer" : "v-clear"}`}>
      <div>
        <h2>{g.referable ? "Refer to ophthalmologist" : "No referral indicated"}</h2>
        <p className="body">
          {g.referable
            ? "Referable diabetic retinopathy (ICDR grade 2 or above)."
            : "Below the referral threshold. Re-screen at the routine interval."}
        </p>
      </div>
      <div style={{ textAlign: "right" }}>
        <div className="gradebig">{g.icdr_grade}</div>
        <div className="mono" style={{ fontSize: ".72rem" }}>
          ICDR · {g.icdr_label}
        </div>
        <div className="mono" style={{ fontSize: ".72rem" }}>
          {(g.confidence * 100).toFixed(0)}% confidence{" "}
          {g.confidence_calibrated ? "(calibrated)" : "(UNCALIBRATED)"}
        </div>
      </div>
    </div>
  );
}

export function QualityPanel({ r }: { r: AnalyzeResult }) {
  const c = r.quality.checks;
  return (
    <div className="card">
      <div className="eyebrow">Image quality gate</div>
      <div className="checks">
        {(["focus", "illumination", "field_of_view"] as const).map((k) => (
          <div className="check" key={k}>
            <span className={`dot ${c[k].passed ? "ok" : "bad"}`} />
            <div>
              <div style={{ fontWeight: 600 }}>{k.replace(/_/g, " ")}</div>
              <div className="muted mono" style={{ fontSize: ".74rem" }}>
                {c[k].value.toFixed(2)} vs {c[k].threshold.toFixed(2)} {c[k].unit}
              </div>
            </div>
          </div>
        ))}
      </div>
      {r.quality.thresholds_fitted === false && (
        <p className="muted" style={{ fontSize: ".76rem", marginTop: 10 }}>
          Thresholds are provisional defaults — not yet fitted against human labels.
        </p>
      )}
    </div>
  );
}

export function Images({ r }: { r: AnalyzeResult }) {
  const e = r.explain;
  if (!e) return null;
  return (
    <div className="card">
      <div className="eyebrow">Explainability</div>
      <div className="imgs" style={{ marginTop: 12 }}>
        {e.overlay_png_b64 && (
          <figure>
            <img src={png(e.overlay_png_b64)} alt="Grad-CAM attention overlay" />
            <figcaption>
              Grad-CAM — where the model looked when deciding referability.
            </figcaption>
          </figure>
        )}
        {e.lesion_overlay_png_b64 && (
          <figure>
            <img src={png(e.lesion_overlay_png_b64)} alt="Detected lesions and landmarks" />
            <figcaption>
              Classical lesion detection. Red microaneurysms, blue haemorrhages, green
              exudates; yellow optic disc, magenta fovea.
            </figcaption>
          </figure>
        )}
      </div>
      {e.attention_summary && (
        <p style={{ fontSize: ".86rem", marginTop: 12 }}>{e.attention_summary}</p>
      )}
      {!e.gradcam_available && (
        <p className="muted" style={{ fontSize: ".8rem", marginTop: 10 }}>
          Heatmap unavailable: {e.gradcam_unavailable_reason}
        </p>
      )}
    </div>
  );
}

export function Evidence({ r }: { r: AnalyzeResult }) {
  if (!r.lesions) return null;
  const rows = [
    ["Microaneurysms", r.lesions.microaneurysms],
    ["Haemorrhages", r.lesions.haemorrhages],
    ["Hard exudates", r.lesions.hard_exudates],
  ] as const;
  return (
    <div className="card">
      <div className="eyebrow">Lesion evidence</div>
      <div className="tblwrap" style={{ marginTop: 12 }}>
        <table>
          <thead>
            <tr>
              <th>Lesion</th>
              <th style={{ textAlign: "right" }}>Total</th>
              {QUADS.map((q) => (
                <th key={q} style={{ textAlign: "right" }} title={QUAD_LABEL[q]}>{q}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, blk]) => (
              <tr key={label}>
                <td>{label}</td>
                <td className="num">{blk.count}</td>
                {QUADS.map((q) => (
                  <td className="num" key={q}>{blk.by_quadrant?.[q] ?? 0}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="muted" style={{ fontSize: ".76rem", marginTop: 8 }}>
        Counts from classical computer vision, not the neural network. Quadrants are
        defined by the disc–fovea axis, which is what the ICDR 4-2-1 rule requires.
      </p>
    </div>
  );
}

export function RulePanel({ r }: { r: AnalyzeResult }) {
  const rc = r.rule_check;
  if (!rc) return null;
  return (
    <div className="card">
      <div className="eyebrow">ICDR clinical rule cross-check</div>
      <p style={{ marginTop: 10, fontSize: ".95rem" }}>
        <strong>Rule grade {rc.rule_grade}</strong> — {rc.rule_label}{" "}
        <span className="pill">{rc.rule_referable ? "referable" : "not referable"}</span>
      </p>
      <ul style={{ fontSize: ".84rem", color: "var(--ink-2)", paddingLeft: 18, marginTop: 8 }}>
        {rc.criteria_fired.map((c, i) => <li key={i}>{c}</li>)}
      </ul>
      {rc.flag_message && (
        <div className="flagbox" style={{ marginTop: 12 }}>
          <strong>Cross-check:</strong> {rc.flag_message}
        </div>
      )}
      {!rc.flag && rc.agrees_with_cnn && (
        <p className="muted" style={{ fontSize: ".82rem", marginTop: 10 }}>
          The clinical rules and the model agree. Two independent estimators reaching the
          same grade is stronger evidence than either alone.
        </p>
      )}
      <details style={{ marginTop: 10 }}>
        <summary className="muted" style={{ fontSize: ".8rem", cursor: "pointer" }}>
          What these rules cannot see
        </summary>
        <ul style={{ fontSize: ".8rem", color: "var(--muted)", paddingLeft: 18 }}>
          {rc.limitations.map((l, i) => <li key={i}>{l}</li>)}
        </ul>
      </details>
    </div>
  );
}

export function Confidence({ r }: { r: AnalyzeResult }) {
  const g = r.grading;
  if (!g) return null;
  return (
    <div className="card">
      <div className="eyebrow">Grade probability</div>
      <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
        {g.per_grade_probability.map((p, i) => (
          <div key={i}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: ".78rem" }}>
              <span>{i} · {["No DR","Mild","Moderate","Severe","Proliferative"][i]}</span>
              <span className="mono">{(p * 100).toFixed(1)}%</span>
            </div>
            <div className="bar"><span style={{ width: `${Math.max(p * 100, 0.5)}%` }} /></div>
          </div>
        ))}
      </div>
      <p className="muted" style={{ fontSize: ".76rem", marginTop: 10 }}>
        P(referable) = {(g.referable_probability * 100).toFixed(1)}% — read directly from
        the ordinal head, not summed from class scores.
      </p>
      {g.grade_from_threshold_not_argmax && (
        <div className="flagbox" style={{ marginTop: 10, fontSize: ".82rem" }}>
          <strong>Why the reported grade isn&apos;t the most likely one.</strong> The single
          most probable grade here is {g.most_likely_grade}, but we report grade{" "}
          {g.icdr_grade}. That is deliberate: the referral threshold is tuned for
          sensitivity, so borderline cases are knowingly over-called. A false alarm costs
          one appointment; a missed referable case costs sight. The confidence shown is the
          probability of the grade we actually reported, not of the most likely one —
          quoting the latter would flatter the number.
        </div>
      )}
    </div>
  );
}

export function Timing({ r }: { r: AnalyzeResult }) {
  const t = r.timing_ms;
  const keys = Object.keys(t).filter((k) => k !== "total");
  return (
    <div className="card">
      <div className="eyebrow">Latency — measured, this request</div>
      <div className="tblwrap" style={{ marginTop: 10 }}>
        <table>
          <tbody>
            {keys.map((k) => (
              <tr key={k}><td>{k}</td><td className="num mono">{t[k]} ms</td></tr>
            ))}
            <tr><td><strong>total</strong></td>
                <td className="num mono"><strong>{t.total} ms</strong></td></tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}
