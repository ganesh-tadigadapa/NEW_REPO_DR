import Shell from "@/components/Shell";

const CANNOT_SEE = [
  { h: "Neovascularisation", p: "New vessel growth is what defines proliferative disease — ICDR grade 4, the most sight-threatening grade. We have no detector for it.", c: "The rule engine can never confirm grade 4. It returns unknown and escalates, rather than reporting no disease." },
  { h: "Venous beading", p: "One of the three limbs of the 4-2-1 rule for severe non-proliferative disease.", c: "That limb is reported as unassessable, not as negative." },
  { h: "IRMA", p: "Intraretinal microvascular abnormalities — the third limb of the 4-2-1 rule.", c: "Also reported as unassessable." },
];

const NOT_BUILT = [
  ["A trained lesion segmentation network", "IDRiD provides 54 pixel-annotated training images. A network trained on that is a model of 54 images, not of diabetic retinopathy. We use classical morphology instead, which needs no training data and is inspectable."],
  ["Messidor-2 validation", "Access approval takes days. IDRiD's test set is the external holdout instead."],
  ["Five-fold cross-validation", "A single stratified split with a fixed seed. Cross-validation would give tighter error bars and buys nothing else here."],
  ["Authentication and patient records", "This is a screening demonstrator, not a clinical system. There is no login and no patient database, and no real patient data should be uploaded to it."],
];

export default function Limitations() {
  return (
    <Shell>
      <section className="hero" style={{ paddingBlock: "26px 24px" }}>
        <h2>Limitations</h2>
        <p className="lede">
          Published before anyone asks. Naming your own gaps is what buys credibility for
          the numbers that <strong>are</strong> here — and a system that hides what it
          cannot see is more dangerous than one that admits it.
        </p>
      </section>

      <section className="band">
        <h3>What the lesion detectors cannot see</h3>
        <p className="intro">
          This is the most important section on the site. Our classical detectors find
          microaneurysms, haemorrhages and hard exudates. They do not find the following —
          and in every case the system reports <em>unknown</em> rather than <em>absent</em>,
          because treating "I cannot see it" as "it is not there" would systematically
          under-grade the sickest patients.
        </p>
        <div className="grid2">
          {CANNOT_SEE.map((x) => (
            <div className="card" key={x.h}>
              <h4 style={{ margin: "0 0 6px", fontSize: ".98rem" }}>{x.h}</h4>
              <p style={{ margin: "0 0 8px", fontSize: ".86rem", color: "var(--ink-2)" }}>{x.p}</p>
              <div className="flagbox" style={{ fontSize: ".82rem" }}>{x.c}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="band">
        <h3>Deliberately not built</h3>
        <div className="tblwrap">
          <table>
            <thead><tr><th>Not built</th><th>Why</th></tr></thead>
            <tbody>
              {NOT_BUILT.map(([h, p]) => (
                <tr key={h}><td><strong>{h}</strong></td><td style={{ color: "var(--ink-2)" }}>{p}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="band">
        <h3>What has not been validated</h3>
        <ul style={{ fontSize: ".9rem", color: "var(--ink-2)", paddingLeft: 20, lineHeight: 1.7 }}>
          <li>
            <strong>No field trial on a real portable fundus camera.</strong> The quality
            gate exists because portable cameras produce worse images, but we have not put
            one in front of it. That is the next step, not a claim.
          </li>
          <li>
            <strong>Quality-gate thresholds are provisional</strong> until they are fitted
            against a few hundred human-labelled images. Until then every response carries
            <code> thresholds_fitted: false</code> and the report page says so.
          </li>
          <li>
            <strong>Unaided read time is an assumption.</strong> The staffing saving in the
            workflow model depends on how long an ophthalmologist takes to grade a raw
            photograph, which we have not measured. It is reported as a range across a
            sensitivity sweep rather than a single number.
          </li>
          <li>
            <strong>Vessel segmentation is a supporting component</strong>, not a
            leaderboard entry. It exists to stop vessels being counted as haemorrhages.
          </li>
        </ul>
      </section>

      <section className="band">
        <h3>How the numbers are guarded</h3>
        <p className="intro">
          The dashboard reads its figures from a results file. If an evaluation has not
          been run, it prints <em>not run yet</em> — there is no placeholder value anywhere
          that could be shipped by accident. Validation figures are labelled as tuned-on
          and distinguished from the external holdout, which is opened once against a
          frozen configuration; the holdout runner refuses a second look unless explicitly
          overridden, and records it permanently if you do.
        </p>
      </section>

      <footer className="site">
        <p>Screening triage aid. Not a diagnostic device. Do not upload real patient data.</p>
      </footer>
    </Shell>
  );
}
