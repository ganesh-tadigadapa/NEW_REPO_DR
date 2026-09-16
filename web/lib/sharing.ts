/**
 * Patient -> doctor sharing.
 *
 * The patient decides. A doctor's verified role is the programme's half of the decision;
 * this is the patient's half, and without it a doctor sees nothing about them.
 *
 * Every call here is scoped by the SESSION, not by anything this module sends. There is
 * no account id in any request body below: the patient is whoever holds the session, and
 * the doctor is whoever redeems the code. A request with nowhere to put somebody else's
 * identifier cannot be used to share or revoke somebody else's record.
 */
import { authFetch } from "@/lib/auth";

export type SharedDoctor = {
  doctor_account_id: string;
  /** The doctor's own claimed professional details. Never a mobile number. */
  doctor_name: string;
  hospital: string;
  granted_at: string;
  reason: string | null;
};

export type ShareCode = {
  code_id: string;
  created_at: string;
  expires_at: number;
};

export type Sharing = {
  shared_with: SharedDoctor[];
  count: number;
  active_codes: ShareCode[];
  note: string;
};

/** The one and only time the plaintext code exists outside the patient's screen. */
export type MintedCode = {
  ok: true;
  code_id: string;
  code: string;
  expires_at: number;
  expires_in: number;
  note: string;
};

async function json<T>(r: Response): Promise<T> {
  const body = await r.json().catch(() => null);
  if (!r.ok) {
    const e = body?.detail?.error || body?.error;
    throw Object.assign(new Error(e?.message || `request failed (${r.status})`),
                        { code: e?.code, status: r.status });
  }
  return body as T;
}

export async function getSharing(): Promise<Sharing> {
  return json(await authFetch("/v1/passport/sharing"));
}

export async function mintShareCode(): Promise<MintedCode> {
  return json(await authFetch("/v1/passport/sharing/codes", { method: "POST" }));
}

export async function cancelShareCode(codeId: string): Promise<void> {
  await json(await authFetch(`/v1/passport/sharing/codes/${encodeURIComponent(codeId)}`,
                             { method: "DELETE" }));
}

export async function revokeDoctor(doctorAccountId: string): Promise<void> {
  await json(await authFetch(
    `/v1/passport/sharing/${encodeURIComponent(doctorAccountId)}/revoke`,
    { method: "POST" }));
}

/** Doctor side: redeem a code a patient gave them. */
export async function redeemShareCode(code: string): Promise<{ patient_id: string }> {
  return json(await authFetch("/v1/passport/sharing/redeem", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  }));
}

/** Seconds until an epoch-seconds expiry, floored at zero. */
export function secondsUntil(expiresAt: number): number {
  return Math.max(0, Math.round(expiresAt - Date.now() / 1000));
}
