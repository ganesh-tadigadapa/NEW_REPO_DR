"use client";
/**
 * Evidence screen. Every number here is fetched from the API — /v1/metrics (dataset
 * evaluation) and /v1/operational (this deployment's own traffic). Nothing is hardcoded.
 * When an evaluation has not been run, this page says "not run yet" rather than showing
 * a plausible number. That is the anti-fabrication rule, enforced in the UI.
 */
import { useEffect, useState } from "react";
import Guard from "@/components/Guard";
import Shell from "@/components/Shell";
import { getMetrics, getOperational } from "@/lib/api";

function Stat({ label, value, sub, void_: isVoid }: {
  label: string; value: React.ReactNode; sub?: string; void_?: boolean;
}) {
  return (
    <div className="card" style={isVoid ? { opacity: 0.55 } : undefined}>
      <div className="eyebrow">{label}</div>
      <div style={{
        fontSize: "1.6rem", fontWeight: 600, marginTop: 6,
        textDecoration: isVoid ? "line-through" : undefined,
      }}>{value}</div>
      {sub && <div className="muted" style={{ fontSize: ".78rem" }}>{sub}</div>}
    </div>
  );
}

export default function Dashboard() {
  const [m, setM] = useState<any>(null);
  const [op, setOp] = useState<any>(null);

  useEffect(() => {
    getMetrics().then(setM).catch(() => setM({ available: false, reason: "API unreachable" }));
    getOperational().then(setOp).catch(() => setOp({ available: false }));
  }, []);

  const NA = <span className="muted" style={{ fontSize: "1rem" }}>not run yet</span>;

  return (
    <Guard>
    <Shell>
      <h2 style={{ fontFamily: "var(--f-display)", fontWeight: 500, marginTop: 0 }}>
        Dataset evaluation
      </h2>
      {m?.available && m.synthetic_demo_model && (
        <div className="err" style={{ marginBottom: 14 }}>
          <strong>These numbers are meaningless.</strong> They come from a model trained on
          synthetic images to exercise the serving path — not from any real dataset. A
          perfect score on ten generated pictures measures nothing. Nothing on this screen
          may be quoted, screenshotted into a deck, or copied into a benchmark table until
          a real training run replaces it.
        </div>
      )}
      {m?.available && (
        <div className={m.is_external_validation ? "card" : "flagbox"}
             style={{ marginBottom: 14 }}>
          <strong>
            {m.is_external_validation
              ? "External holdout — opened once, nothing tuned on it."
              : "These are VALIDATION numbers, not an external validation."}
          </strong>
          {m.caveat && <div style={{ marginTop: 4 }}>{m.caveat}</div>}
          <div className="mono muted" style={{ fontSize: ".74rem", marginTop: 6 }}>
            run {m.run_id} · source {m._source}
          </div>
        </div>
      )}
      {m && !m.available && (
        <div className="flagbox" style={{ marginBottom: 14 }}>
          No evaluation has been run yet ({m.reason}). This page deliberately shows
          nothing rather than a placeholder — every number in our deck must trace to a
          file in <code>results/</code>.
        </div>
      )}
      <div className="grid2">
        <Stat void_={!!m?.synthetic_demo_model} label="Referable sensitivity"
              value={m?.referable?.sensitivity != null ? `${(m.referable.sensitivity * 100).toFixed(1)}%` : NA}
              sub={m?.referable?.sensitivity_ci95 ? `95% CI ${m.referable.sensitivity_ci95.lo}–${m.referable.sensitivity_ci95.hi}` : "target >90%"} />
        <Stat void_={!!m?.synthetic_demo_model} label="Referable specificity"
              value={m?.referable?.specificity != null ? `${(m.referable.specificity * 100).toFixed(1)}%` : NA}
              sub={m?.referable?.specificity_ci95 ? `95% CI ${m.referable.specificity_ci95.lo}–${m.referable.specificity_ci95.hi}` : "target >85%"} />
        <Stat void_={!!m?.synthetic_demo_model} label="Quadratic weighted kappa" value={m?.qwk ?? NA}
              sub={m?.split ? `on ${m.split} (n=${m.n})` : "published work sits ~0.90–0.92"} />
        <Stat void_={!!m?.synthetic_demo_model} label="Within one grade"
              value={m?.within_one_grade != null ? `${(m.within_one_grade * 100).toFixed(1)}%` : NA} />
      </div>

      <h2 style={{ fontFamily: "var(--f-display)", fontWeight: 500, marginTop: 30 }}>
        This deployment, measured
      </h2>
      <p className="muted" style={{ fontSize: ".84rem", marginTop: -6 }}>
        Computed from requests this service has actually served — demo traffic, not a
        dataset evaluation.
      </p>
      <div className="grid2">
        <Stat label="Scans served" value={op?.n_scans ?? "—"} />
        <Stat label="Median latency"
              value={op?.median_latency_ms != null ? `${op.median_latency_ms} ms` : "—"} />
        <Stat label="Ungradeable rate"
              value={op?.ungradeable_rate != null ? `${(op.ungradeable_rate * 100).toFixed(0)}%` : "—"}
              sub="images the gate refused" />
        <Stat label="Median review time"
              value={op?.median_seconds_to_decide != null ? `${op.median_seconds_to_decide.toFixed(1)} s` : "—"}
              sub="target <30 s" />
      </div>
    </Shell>
    </Guard>
  );
}
