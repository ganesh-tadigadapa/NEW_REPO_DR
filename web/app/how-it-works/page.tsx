import Shell from "@/components/Shell";

const DECISIONS = [
  {
    h: "An ordinal head, not a 5-way softmax",
    p: `The ICDR grades are ordered. Ordinary classification treats "predicted 0, actually 4" and "predicted 3, actually 4" as equally wrong — clinically the first could blind someone and the second is a rounding error. We use a CORAL ordinal head that answers four cumulative questions instead: is it worse than 0, than 1, than 2, than 3? The grade is how many are yes.`,
    why: `The second question is exactly the referral decision. P(grade ≥ 2) is a direct model output with its own threshold, so hitting a sensitivity target is a dial we turn, not a hope.`,
  },
  {
    h: "Sharpness measured relative to the image's own contrast",
    p: `The textbook focus measure is variance of the Laplacian. It conflates blurry with smooth: a healthy retina has few lesions and therefore few edges, and scored as blurrier than a diseased out-of-focus one.`,
    why: `Left alone, the gate would have quietly rejected healthy eyes and biased every prevalence number downstream. We normalise gradient energy by the retina's own contrast, and a test pins the ordering.`,
  },
  {
    h: "Vessel suppression only on elongated structures",
    p: `Vessels and dark lesions are indistinguishable to an intensity threshold, so the lesion detector suppresses vessels first. But at small scales a microaneurysm — a two-pixel dark dot — is itself a perfectly good ridge, and naive suppression deleted every one of them.`,
    why: `We raised the filter's minimum scale and restricted suppression to components that are genuinely long and thin. A compact blob of vessel-like response is far more likely to be the lesion we are counting.`,
  },
  {
    h: "The model runs inside our own server",
    p: `Grad-CAM needs the gradient of an output with respect to an intermediate activation. A managed prediction endpoint returns the answer tensor and nothing else.`,
    why: `The explainability requirement makes the fashionable architecture impossible. We load the model in-process instead — which also happens to be cheaper.`,
  },
  {
    h: "Confidence is calibrated, and we show the correction",
    p: `A raw network score is not a probability; modern networks are systematically overconfident. Temperature scaling fits a single scalar on validation data to correct it.`,
    why: `One parameter, so it cannot overfit, and it changes no ranking — accuracy and thresholds are mathematically untouched. It only makes the number honest. We report calibration error before and after.`,
  },
  {
    h: "Two independent opinions, and disagreements are surfaced",
    p: `Separately from the network, classical computer vision counts lesions per quadrant and applies the published ICDR criteria — including the 4-2-1 rule, which is why we locate the optic disc and fovea at all.`,
    why: `When the two disagree we escalate to clinician review rather than averaging them. A false alarm costs one appointment; a missed grade 3 costs sight.`,
  },
];

export default function HowItWorks() {
  return (
    <Shell>
      <section className="hero" style={{ paddingBlock: "26px 24px" }}>
        <h2>How it works</h2>
        <p className="lede">
          The decisions worth defending, and the reasoning behind each. Several of these
          were changed after measurement contradicted the obvious choice.
        </p>
      </section>

      <section className="band">
        <h3>Pipeline</h3>
        <p className="intro">
          One request, one process, one pass. Every stage is timed and the timings are
          returned with the result — the latency you see in the interface is measured, not
          quoted.
        </p>
        <div className="tblwrap">
          <table>
            <thead><tr><th>Stage</th><th>What it does</th><th>Can it fail alone?</th></tr></thead>
            <tbody>
              <tr><td><strong>Quality gate</strong></td><td>Focus, illumination, field of view</td><td>A failure stops everything — an ungradeable image is never graded</td></tr>
              <tr><td><strong>Preprocess</strong></td><td>Retina crop, Ben-Graham, CLAHE on green</td><td>Identical code at train and inference time</td></tr>
              <tr><td><strong>Grade</strong></td><td>EfficientNetV2-S + CORAL ordinal head</td><td>Yes — lesions and rules still return without it</td></tr>
              <tr><td><strong>Grad-CAM</strong></td><td>Attention for the referral decision</td><td>Yes — the grade still returns</td></tr>
              <tr><td><strong>Lesion CV</strong></td><td>Microaneurysms, haemorrhages, exudates by quadrant</td><td>Yes — the grade still returns</td></tr>
              <tr><td><strong>ICDR rules</strong></td><td>Independent grade from the clinical criteria</td><td>Needs lesion counts only, not the network</td></tr>
              <tr><td><strong>Report</strong></td><td>One-page PDF for sign-off</td><td>Yes — the result is still valid</td></tr>
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ fontSize: ".82rem", marginTop: 10 }}>
          Nothing in this chain can turn a partial result into no result. If the model is
          absent the interface says so and still returns the lesion evidence and the
          rule-based grade.
        </p>
      </section>

      <section className="band">
        <h3>Design decisions</h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {DECISIONS.map((d) => (
            <div className="card" key={d.h}>
              <h4 style={{ margin: "0 0 7px", fontSize: "1rem" }}>{d.h}</h4>
              <p style={{ margin: "0 0 8px", fontSize: ".88rem", color: "var(--ink-2)" }}>{d.p}</p>
              <p style={{ margin: 0, fontSize: ".88rem" }}>
                <strong>Why it matters: </strong>{d.why}
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="band">
        <h3>Where MATLAB stays</h3>
        <p className="intro">
          The problem statement asks for a MATLAB-based pipeline and we built a hybrid, so
          this is stated up front rather than waited on.
        </p>
        <div className="grid2">
          <div className="card">
            <div className="eyebrow" style={{ color: "var(--teal)" }}>MATLAB / Simulink</div>
            <ul style={{ fontSize: ".87rem", color: "var(--ink-2)", paddingLeft: 18, marginTop: 8 }}>
              <li><strong>The Simulink workflow model.</strong> A discrete-event resource study is genuinely what SimEvents is for, and it needs no GPU.</li>
              <li><strong>The classical CV baseline.</strong> Top-hat exudates, extended-minima microaneurysms, matched-filter vessels, SVM grading — on identical splits.</li>
            </ul>
            <p style={{ fontSize: ".86rem", marginTop: 8 }}>
              That second one turns a constraint into a scoring advantage: the problem
              statement asks for proof the integrated pipeline beats any single technique,
              and the classical pipeline <em>is</em> that single technique. It is the
              control arm, not an omission.
            </p>
          </div>
          <div className="card">
            <div className="eyebrow" style={{ color: "var(--crimson)" }}>Cloud, for the CNN</div>
            <ul style={{ fontSize: ".87rem", color: "var(--ink-2)", paddingLeft: 18, marginTop: 8 }}>
              <li><strong>No GPU in the room.</strong> Two hours on a rented T4 against over a day on a laptop CPU.</li>
              <li><strong>Toolbox risk.</strong> Six toolboxes are named; a licence gap found at hour 20 is fatal.</li>
              <li><strong>Deployability.</strong> "Deployment in primary healthcare centres" is not answered by a model on a developer&apos;s laptop.</li>
              <li><strong>Reproducibility.</strong> Versioned, re-runnable jobs are what clinical validation rigour means in practice.</li>
            </ul>
          </div>
        </div>
      </section>

      <footer className="site">
        <p>Screening triage aid. Not a diagnostic device.</p>
      </footer>
    </Shell>
  );
}
