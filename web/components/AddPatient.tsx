"use client";
/**
 * "Add a patient" — the doctor's side of patient-initiated sharing.
 *
 * A verified doctor role is not a licence to read every patient. This is how a doctor
 * reaches someone: the patient generates a code on their own Eye Health Passport and
 * reads it out; entering it here creates the care relationship, and the patient can end
 * it whenever they like.
 *
 * There is deliberately no patient search, no patient directory and no way to type an
 * account id. The code names the patient, so there is nowhere to put somebody else's
 * identifier.
 */
import { useState } from "react";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import { redeemShareCode } from "@/lib/sharing";

export default function AddPatient({ onAdded }: { onAdded?: () => void }) {
  const { t } = useCareBridge();
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null); setAdded(false);
    try {
      await redeemShareCode(code.trim());
      setAdded(true);
      setCode("");
      onAdded?.();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="card addpatient" onSubmit={submit}>
      <div className="eyebrow">{t("sharing.doctorAdd")}</div>
      <p className="cb-note" style={{ marginTop: 6 }}>{t("sharing.doctorAddHint")}</p>
      <div className="addpatientrow">
        <label className="cb-sronly" htmlFor="share-code">
          {t("sharing.doctorCodeLabel")}
        </label>
        <input
          id="share-code"
          className="txt mono"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          placeholder="ABCD-2345"
          autoComplete="off"
          spellCheck={false}
          maxLength={16}
        />
        <button className="primary" type="submit" disabled={busy || code.trim().length < 4}>
          {busy ? <><span className="spin" /> {t("common.loading")}</>
                : t("sharing.doctorAdd")}
        </button>
      </div>
      {error && <div className="err" style={{ marginTop: 10 }}>{error}</div>}
      {added && (
        <p className="cb-note" style={{ marginTop: 10, color: "var(--teal)" }}>
          ✓ {t("sharing.doctorAdded")}
        </p>
      )}
    </form>
  );
}
