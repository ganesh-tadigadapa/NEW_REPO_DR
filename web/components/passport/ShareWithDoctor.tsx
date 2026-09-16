"use client";
/**
 * "Who can see my screening history?" — the patient's own control panel.
 *
 * This is the half of the authorisation decision that belongs to the patient. A verified
 * doctor cannot open their timeline, their reports or their follow-up plan until they
 * appear here, and stops being able to the moment they are removed.
 *
 * The code is shown ONCE, when it is minted. It is stored hashed on the server, so it
 * cannot be looked up again or re-displayed — losing it means minting another, which is
 * the correct trade for a credential that hands over a medical history.
 */
import { useCallback, useEffect, useState } from "react";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import WhyThis from "@/components/carebridge/WhyThis";
import {
  cancelShareCode, getSharing, mintShareCode, revokeDoctor, secondsUntil,
  type MintedCode, type Sharing,
} from "@/lib/sharing";

function minutes(seconds: number): string {
  const m = Math.ceil(seconds / 60);
  return m <= 1 ? "1 minute" : `${m} minutes`;
}

export default function ShareWithDoctor() {
  const { t } = useCareBridge();
  const [data, setData] = useState<Sharing | null>(null);
  const [minted, setMinted] = useState<MintedCode | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    getSharing().then(setData).catch((e) => setError(e.message));
  }, []);

  useEffect(() => { load(); }, [load]);

  const mint = async () => {
    setBusy(true); setError(null);
    try {
      setMinted(await mintShareCode());
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (doctorId: string) => {
    setBusy(true); setError(null);
    try {
      await revokeDoctor(doctorId);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const cancel = async (codeId: string) => {
    setBusy(true); setError(null);
    try {
      await cancelShareCode(codeId);
      if (minted?.code_id === codeId) setMinted(null);
      load();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="card cb-section" aria-labelledby="share-h">
      <div className="eyebrow">
        <span aria-hidden="true">🤝</span> {t("sharing.eyebrow")}
      </div>
      <h3 id="share-h" className="cb-h">{t("sharing.title")}</h3>
      <p className="cb-lede">{t("sharing.intro")}</p>

      {error && <div className="err" style={{ marginTop: 12 }}>{error}</div>}

      {/* ---------------------------------------------------- who has access */}
      <h4 className="cb-label" style={{ marginTop: 18 }}>{t("sharing.whoHasAccess")}</h4>
      {data === null ? (
        <p className="muted"><span className="spin" /> {t("common.loading")}</p>
      ) : data.shared_with.length === 0 ? (
        <p className="cb-note">{t("sharing.nobody")}</p>
      ) : (
        <ul className="sharelist">
          {data.shared_with.map((d) => (
            <li key={d.doctor_account_id}>
              <div>
                <strong>{d.doctor_name || t("sharing.unnamedDoctor")}</strong>
                {d.hospital && <span className="muted"> · {d.hospital}</span>}
                <div className="muted mono sharewhen">
                  {t("sharing.sharedOn")} {new Date(d.granted_at).toLocaleDateString()}
                </div>
              </div>
              <button
                type="button"
                className="ghost"
                disabled={busy}
                onClick={() => revoke(d.doctor_account_id)}
              >
                {t("sharing.revoke")}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* ------------------------------------------------------- mint a code */}
      <h4 className="cb-label" style={{ marginTop: 22 }}>{t("sharing.giveAccess")}</h4>
      <p className="cb-note" style={{ marginTop: 4 }}>{t("sharing.howItWorks")}</p>

      {minted && (
        <div className="sharecode" role="status">
          <div className="sharecodevalue mono">{minted.code}</div>
          <p className="cb-note" style={{ margin: "8px 0 0" }}>
            {t("sharing.codeExpires", { minutes: minutes(secondsUntil(minted.expires_at)) })}
          </p>
          <p className="cb-note" style={{ margin: "4px 0 0" }}>{t("sharing.codeOnce")}</p>
        </div>
      )}

      <button type="button" className="primary" disabled={busy} onClick={mint}
              style={{ marginTop: 12 }}>
        {busy ? <><span className="spin" /> {t("common.loading")}</>
              : t("sharing.createCode")}
      </button>

      {data && data.active_codes.length > 0 && (
        <div style={{ marginTop: 14 }}>
          <p className="cb-note" style={{ marginBottom: 6 }}>
            {t("sharing.unusedCodes", { count: data.active_codes.length })}
          </p>
          <div className="filterrow">
            {data.active_codes.map((c) => (
              <button key={c.code_id} type="button" className="chip" disabled={busy}
                      onClick={() => cancel(c.code_id)}>
                {t("sharing.cancelCode")} · {minutes(secondsUntil(c.expires_at))}
              </button>
            ))}
          </div>
        </div>
      )}

      <WhyThis extra={t("sharing.why")} />
    </section>
  );
}
