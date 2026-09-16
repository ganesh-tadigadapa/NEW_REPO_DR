"use client";
/**
 * Sign in with a mobile number. That is the whole of it.
 *
 * There is no code, no password and no verification step: the number is taken as
 * CLAIMED. The screen says so, because a person handing over a phone number on a
 * medical site is entitled to know what it does and does not protect.
 *
 * The number is still asked for, and still matters: it is the account identity that
 * owns this person's screening history, their Eye Health Passport and the WhatsApp
 * number their report is delivered to. Removing verification did not remove identity.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthLayout, FieldLabel } from "@/components/AuthCard";
import { useAuth } from "@/components/AuthProvider";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import { normaliseMobile, signIn, signInErrorMessage } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const { refresh, authenticated, account } = useAuth();
  const { t } = useCareBridge();

  const [mobile, setMobile] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Already signed in? Don't make them do it again.
  useEffect(() => {
    if (authenticated && account) {
      router.replace(account.can_read_reports ? "/reports" : "/screen");
    }
  }, [authenticated, account, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const m = normaliseMobile(mobile);
    if (!m) {
      setError("Enter a 10-digit mobile number.");
      return;
    }
    setBusy(true);
    try {
      // `next` is computed by the BACKEND from the stored role. The browser does not
      // decide where a doctor lands, because the browser does not decide who is one.
      const r = await signIn({ mobile: m, intent: "login" });
      await refresh();
      router.replace(r.next || "/screen");
    } catch (err: any) {
      setError(signInErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title={t("auth.signInTitle")}
      subtitle={t("auth.signInSub")}
      footer={
        <>
          Don’t have an account? <Link href="/signup">Create Account</Link>
        </>
      }
    >
      {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

      <form onSubmit={submit}>
        <label className="field">
          <FieldLabel>Mobile Number</FieldLabel>
          <div className="mobileinput">
            <span className="cc">+91</span>
            <input
              autoFocus
              type="tel"
              inputMode="numeric"
              autoComplete="tel"
              placeholder="98765 43210"
              value={mobile}
              onChange={(e) => setMobile(e.target.value)}
            />
          </div>
        </label>
        <button className="primary bigbtn" type="submit" disabled={busy}>
          {busy ? <><span className="spin" /> Signing in…</> : "Continue"}
        </button>
      </form>

      {/* Stated on the screen rather than buried in a doc. */}
      <p className="cb-note" style={{ marginTop: 16 }}>
        This build does not verify your number — there is no code to enter. Your number
        identifies your records and is where your report is sent.
      </p>
    </AuthLayout>
  );
}
