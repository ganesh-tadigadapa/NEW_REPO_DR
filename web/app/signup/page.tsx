"use client";
/**
 * Create an account: mobile number and account type. One step.
 *
 * There is no code, no password and no verification: the number is taken as CLAIMED.
 * The number still matters — it is the identity that owns this person's screening
 * history and the number their WhatsApp report is delivered to.
 *
 * What has NOT changed is that choosing "Doctor Account" grants nothing. The backend
 * creates every doctor with `doctor_verified = false` (src/auth/storage.py::create) and
 * only `service.approve_doctor()` — an admin endpoint or a local script — can change
 * that. This form records a claim for a human to check.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { AuthLayout, FieldLabel } from "@/components/AuthCard";
import { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import { useAuth } from "@/components/AuthProvider";
import { normaliseMobile, signIn, signInErrorMessage } from "@/lib/auth";

type Role = "user" | "doctor";

export default function SignupPage() {
  const router = useRouter();
  const { t } = useCareBridge();
  const { refresh, authenticated, account } = useAuth();

  const [done, setDone] = useState(false);
  const [mobile, setMobile] = useState("");
  const [role, setRole] = useState<Role>("user");
  const [doctorName, setDoctorName] = useState("");
  const [regNumber, setRegNumber] = useState("");
  const [hospital, setHospital] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!done && authenticated && account) {
      router.replace(account.can_read_reports ? "/reports" : "/screen");
    }
  }, [done, authenticated, account, router]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    const m = normaliseMobile(mobile);
    if (!m) { setError("Enter a 10-digit mobile number."); return; }
    if (role === "doctor") {
      if (doctorName.trim().length < 2) { setError("Enter the doctor’s full name."); return; }
      if (regNumber.trim().length < 3) { setError("Enter the medical registration number."); return; }
      if (hospital.trim().length < 2) { setError("Enter the hospital or clinic name."); return; }
    }
    setBusy(true);
    try {
      const r = await signIn({
        mobile: m,
        intent: "signup",
        role,
        doctor_profile: role === "doctor"
          ? {
              doctor_name: doctorName.trim(),
              registration_number: regNumber.trim(),
              hospital: hospital.trim(),
            }
          : undefined,
      });
      await refresh();
      if (r.doctor_verification_pending) {
        setDone(true);
      } else {
        router.replace(r.next || "/screen");
      }
    } catch (err: any) {
      setError(signInErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthLayout
      title={t("auth.createTitle")}
      subtitle={t("auth.createSub")}
      footer={done ? undefined : <>Already registered? <Link href="/login">Sign in</Link></>}
    >
      {error && <div className="err" style={{ marginBottom: 14 }}>{error}</div>}

      {!done && (
        <form onSubmit={submit}>
          <label className="field">
            <FieldLabel>Mobile Number</FieldLabel>
            <div className="mobileinput">
              <span className="cc">+91</span>
              <input
                autoFocus type="tel" inputMode="numeric" autoComplete="tel"
                placeholder="98765 43210"
                value={mobile} onChange={(e) => setMobile(e.target.value)}
              />
            </div>
          </label>

          <div className="field">
            <FieldLabel>Choose account type</FieldLabel>
            <div className="roletiles">
              <button
                type="button"
                className={`roletile ${role === "user" ? "on" : ""}`}
                onClick={() => setRole("user")}
                aria-pressed={role === "user"}
              >
                <span className="rt">User Account</span>
                <span className="rd">Screen retinal images and see your own results.</span>
              </button>
              <button
                type="button"
                className={`roletile ${role === "doctor" ? "on" : ""}`}
                onClick={() => setRole("doctor")}
                aria-pressed={role === "doctor"}
              >
                <span className="rt">Doctor Account</span>
                <span className="rd">Everything above, plus the anonymised report queue after verification.</span>
              </button>
            </div>
          </div>

          {role === "doctor" && (
            <div className="verifyblock">
              <div className="eyebrow">Verification information</div>
              <p className="verifynote">
                Checked by a programme administrator before the reports area opens.
                Your account is created immediately, with reports access pending.
              </p>
              <label className="field">
                <FieldLabel>Doctor Name</FieldLabel>
                <input className="txt" value={doctorName} onChange={(e) => setDoctorName(e.target.value)}
                       placeholder="Dr A. Sharma" autoComplete="name" />
              </label>
              <label className="field">
                <FieldLabel>Medical Registration Number</FieldLabel>
                <input className="txt mono" value={regNumber} onChange={(e) => setRegNumber(e.target.value)}
                       placeholder="TN/12345/2018" />
              </label>
              <label className="field">
                <FieldLabel>Hospital / Clinic Name</FieldLabel>
                <input className="txt" value={hospital} onChange={(e) => setHospital(e.target.value)}
                       placeholder="District Hospital, Erode" />
              </label>
            </div>
          )}

          <button className="primary bigbtn" type="submit" disabled={busy}>
            {busy ? <><span className="spin" /> Creating…</> : "Create account"}
          </button>

          {/* Stated on the screen rather than buried in a doc. */}
          <p className="cb-note" style={{ marginTop: 16 }}>
            This build does not verify your number — there is no code to enter. Your
            number identifies your records and is where your report is sent.
          </p>
        </form>
      )}

      {done && (
        <div>
          <div className="pendingbox">
            <strong>Doctor verification pending.</strong>
            <p style={{ margin: "6px 0 0" }}>
              Your account is active. A programme administrator has to confirm your
              medical registration ({regNumber || "—"}) before the reports area opens.
            </p>
          </div>
          <p className="muted" style={{ fontSize: ".88rem" }}>
            You can screen images and review results now. The Reports tab appears on its
            own once you are approved.
          </p>
          <Link href="/screen" className="cta solid" style={{ display: "inline-block" }}>
            Go to screening
          </Link>
        </div>
      )}
    </AuthLayout>
  );
}
