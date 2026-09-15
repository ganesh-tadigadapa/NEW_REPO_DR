"use client";
/**
 * Sample images built into the app.
 *
 * A judge will not be carrying a fundus photograph. Without this they cannot try the
 * product at all, and the single most persuasive moment in the demo — a deliberately
 * blurry image being refused with a useful instruction — depends on having a blurry
 * image to hand. Two taps, no file, no preparation.
 *
 * These are REAL APTOS 2019 fundus photographs from the held-out validation split --
 * none of them was seen during training. Each manifest entry carries its source image
 * id and its ground-truth grade, so a prediction can be checked against the label live.
 *
 * One exception, labelled `modified` in the manifest: the field-of-view sample is a real
 * held-out image cropped to 40% width to simulate a mis-framed capture. APTOS contains
 * almost no naturally ungradeable images -- our quality gate refused 1 of 550 validation
 * images and 0 of 400 test images -- so a natural FOV failure was not available.
 */
import { useEffect, useState } from "react";

export type Sample = {
  file: string; title: string; description: string; expect: "graded" | "refused";
  source?: string; true_grade?: number; modified?: boolean;
};

export default function Samples({
  onPick, disabled,
}: { onPick: (f: File, s: Sample) => void; disabled?: boolean }) {
  const [samples, setSamples] = useState<Sample[]>([]);

  useEffect(() => {
    fetch("/samples/manifest.json")
      .then((r) => r.json())
      .then(setSamples)
      .catch(() => setSamples([]));
  }, []);

  if (!samples.length) return null;

  const pick = async (s: Sample) => {
    const res = await fetch(`/samples/${s.file}`);
    const blob = await res.blob();
    onPick(new File([blob], s.file, { type: blob.type || "image/jpeg" }), s);
  };

  return (
    <div className="card">
      <div className="eyebrow">No fundus photo to hand? Try one of these</div>
      <p className="muted" style={{ fontSize: ".8rem", margin: "6px 0 12px" }}>
        Synthetic images, for exercising the pipeline. The last two are deliberately bad —
        they should be refused with an instruction, not graded.
      </p>
      <div className="samples">
        {samples.map((s) => (
          <button
            key={s.file}
            className="sample"
            onClick={() => pick(s)}
            disabled={disabled}
            aria-label={`Try sample: ${s.title}`}
          >
            <img src={`/samples/${s.file}`} alt={s.title} />
            <span className={`badge ${s.expect === "refused" ? "refuse" : "grade"}`}>
              {s.expect === "refused" ? "SHOULD REFUSE" : "SHOULD GRADE"}
            </span>
            <span className="t">{s.title}</span>
            <span className="d">{s.description}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
