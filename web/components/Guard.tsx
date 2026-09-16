"use client";
/**
 * Route gating in the UI.
 *
 * This is a NAVIGATION aid, not a security boundary. The security boundary is the API:
 * every protected endpoint re-reads the caller's role from the account store, so a user
 * who forces their way onto /reports in devtools gets an empty page and a 403, not data.
 * That separation is the point — this component decides what to draw, the backend
 * decides what exists.
 */
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/AuthProvider";
import Shell from "@/components/Shell";

function Panel({ title, body, action }: {
  title: string; body: React.ReactNode; action?: React.ReactNode;
}) {
  return (
    <Shell>
      <div className="card" style={{ maxWidth: 560, marginTop: 24 }}>
        <div className="eyebrow">Access</div>
        <h2 style={{ fontFamily: "var(--f-display)", fontWeight: 500, margin: "6px 0 8px" }}>
          {title}
        </h2>
        <div style={{ color: "var(--ink-2)", fontSize: ".92rem" }}>{body}</div>
        {action && <div style={{ marginTop: 16 }}>{action}</div>}
      </div>
    </Shell>
  );
}

export default function Guard({ children, requireDoctor = false }: {
  children: React.ReactNode;
  requireDoctor?: boolean;
}) {
  const { loading, authenticated, account, doctorVerificationPending } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !authenticated) router.replace("/login");
  }, [loading, authenticated, router]);

  if (loading) {
    return (
      <Shell>
        <div className="card" style={{ marginTop: 24 }}>
          <span className="spin" /> <span className="muted">Checking your session…</span>
        </div>
      </Shell>
    );
  }

  if (!authenticated) {
    return (
      <Panel
        title="Sign in to continue"
        body="This area needs a verified mobile number."
        action={<Link href="/login" className="cta solid">Sign in</Link>}
      />
    );
  }

  if (requireDoctor && !account?.can_read_reports) {
    // Two different refusals, because they mean two different things to the person.
    if (account?.role === "doctor" && doctorVerificationPending) {
      return (
        <Panel
          title="Doctor verification pending."
          body={
            <>
              <p style={{ marginTop: 0 }}>
                Your doctor account has been created and your mobile number is verified.
                A programme administrator still has to confirm your medical registration
                before the reports area opens.
              </p>
              <p className="muted" style={{ fontSize: ".85rem" }}>
                Registration submitted: {account.doctor_profile?.registration_number || "—"}
                {account.doctor_profile?.hospital ? ` · ${account.doctor_profile.hospital}` : ""}
              </p>
              <p style={{ marginBottom: 0 }}>
                Screening and review are available to you in the meantime.
              </p>
            </>
          }
          action={<Link href="/screen" className="cta solid">Go to screening</Link>}
        />
      );
    }
    return (
      <Panel
        title="Doctor access required."
        body="The reports area is limited to verified doctor accounts. Your account can screen images and see its own results."
        action={<Link href="/screen" className="cta solid">Go to screening</Link>}
      />
    );
  }

  return <>{children}</>;
}
