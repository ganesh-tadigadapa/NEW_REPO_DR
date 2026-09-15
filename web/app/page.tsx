import Link from "next/link";
import Shell from "@/components/Shell";

const STEPS = [
  { n: "01", h: "Capture and upload", p: "A health worker photographs the retina. The browser shrinks the image before upload — a raw fundus JPEG is 6 MB and rural uplink is slow." },
  { n: "02", h: "Quality gate", p: "Focus, illumination and field of view are checked first. An ungradeable image is refused with a specific instruction for retaking it, never guessed at." },
  { n: "03", h: "Grade and explain", p: "An ordinal CNN returns an ICDR grade and a referral decision, with a Grad-CAM heatmap showing what drove it." },
  { n: "04", h: "Cross-check and report", p: "Classical CV counts lesions by quadrant and applies the ICDR clinical rules independently. Disagreements are surfaced, not hidden." },
];

const REQS = [
  { n: "1", h: "Image quality & enhancement", p: "Three checks with thresholds fitted against human labels; CLAHE and Ben-Graham rescue borderline images.", e: "HTTP 422 plus the failed criterion" },
  { n: "2", h: "Structure segmentation", p: "Optic disc, fovea, Frangi vessels, and lesions by classical morphology at full resolution.", e: "Lesion counts per quadrant; Dice vs DRIVE" },
  { n: "3", h: "DR severity grading", p: "EfficientNetV2-S with a CORAL ordinal head, so P(referable) is a direct output with its own tunable threshold.", e: "QWK, sensitivity and specificity with CIs" },
  { n: "4", h: "Explainability", p: "Grad-CAM measured against real lesion masks, the ICDR rule engine as a second opinion, temperature-scaled confidence.", e: "Attribution inside lesions; ECE before/after" },
  { n: "5", h: "Workflow simulation", p: "The district screening programme as a discrete-event model: arrivals, recapture loops, review queue.", e: "Ophthalmologist FTEs with and without AI" },
];

export default function Home() {
  return (
    <Shell>
      <section className="hero">
        <h2>Diabetic retinopathy screening that explains itself</h2>
        <p className="lede">
          India has roughly <strong>77 million diabetics</strong> and about one
          ophthalmologist per 100,000 people in rural areas. Screening every patient by
          hand is arithmetically impossible. This is a triage aid: upload a fundus
          photograph, get an ICDR grade, a referral decision, and — the part that matters
          — <strong>the evidence behind it</strong>.
        </p>
        <div className="ctarow">
          <Link href="/screen" className="cta solid">Screen an image</Link>
          <Link href="/how-it-works" className="cta line">How it works</Link>
        </div>
        <div className="factbar">
          <div className="fact"><span className="k">Grading scale</span><span className="v">ICDR 0–4</span></div>
          <div className="fact"><span className="k">Referral bar</span><span className="v">&gt;90<small>% sens</small></span></div>
          <div className="fact"><span className="k">Specificity bar</span><span className="v">&gt;85<small>%</small></span></div>
          <div className="fact"><span className="k">Sign-off target</span><span className="v">&lt;30<small> seconds</small></span></div>
          <div className="fact"><span className="k">Ungradeable</span><span className="v">refused<small>, not guessed</small></span></div>
        </div>
      </section>

      <section className="band">
        <h3>What happens to an image</h3>
        <p className="intro">
          One request, one pass, a few seconds. Every stage is timed and the timings come
          back with the result.
        </p>
        <div className="steps">
          {STEPS.map((s) => (
            <div className="step" key={s.n}>
              <div className="n">{s.n}</div>
              <h4>{s.h}</h4>
              <p>{s.p}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="band">
        <h3>The five graded requirements</h3>
        <p className="intro">
          Each one has a module and a measured output. Nothing here is asserted without a
          number behind it, and where a number has not been produced yet the interface
          says so.
        </p>
        <div className="tblwrap">
          <table>
            <thead>
              <tr><th>#</th><th>Requirement</th><th>How</th><th>Evidence</th></tr>
            </thead>
            <tbody>
              {REQS.map((r) => (
                <tr key={r.n}>
                  <td className="mono">{r.n}</td>
                  <td><strong>{r.h}</strong></td>
                  <td style={{ color: "var(--ink-2)" }}>{r.p}</td>
                  <td style={{ color: "var(--muted)" }}>{r.e}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="band">
        <h3>What this is not</h3>
        <p className="intro">
          A screening triage aid, not a diagnostic device. It does not discharge anyone:
          every referable case goes to a clinician, and cases where the model and the
          clinical rules disagree are escalated rather than averaged. We publish what it
          cannot see on the <Link href="/limitations">limitations page</Link> — including
          the lesion types our detectors miss entirely.
        </p>
      </section>

      <footer className="site">
        <p>Screening triage aid. Not a diagnostic device. Not for clinical use.</p>
        <p>SIH26038 · datasets: APTOS 2019, IDRiD, DRIVE.</p>
      </footer>
    </Shell>
  );
}
