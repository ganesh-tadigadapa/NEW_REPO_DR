/**
 * Sign-in — what the screen does now that there is no code to enter.
 *
 * `fetch` is stubbed in every test, so the only thing these pages can talk to is a
 * recorded fake of this project's own API.
 *
 * The properties worth protecting after removing verification:
 *   * the browser never decides where a doctor lands — the backend's `next` does;
 *   * a role can be REQUESTED at signup but never granted by the client;
 *   * the session token is stored, and nothing else is;
 *   * the screen says plainly that the number is not verified, rather than implying it is;
 *   * there is no OTP input, no resend, no SMS claim anywhere in the UI.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CareBridgeProvider from "@/components/carebridge/CareBridgeProvider";
import LoginPage from "@/app/login/page";
import SignupPage from "@/app/signup/page";

const MOBILE_TYPED = "9876543210";
const MOBILE_E164 = "+919876543210";

const session = { authenticated: false, account: null as any, refresh: vi.fn() };
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => session,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

const replaced: string[] = [];
vi.mock("next/navigation", () => ({
  usePathname: () => "/login",
  useRouter: () => ({ replace: (p: string) => { replaced.push(p); }, push: () => {} }),
}));

type Call = { url: string; body: any };

const OK_SESSION = {
  ok: true, created: false, token: "app-session-token", token_type: "bearer",
  account: { account_id: "acc_1", mobile: MOBILE_E164, role: "user",
             can_read_reports: false, doctor_verified: false },
  next: "/screen", doctor_verification_pending: false,
};

function stubApi(status = 200, body: any = OK_SESSION): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: any, init: any) => {
    calls.push({ url: String(url), body: JSON.parse(init?.body || "{}") });
    return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
  }));
  return calls;
}

const refusal = (code: string, message: string) => ({ detail: { error: { code, message } } });

const renderLogin = () => render(<CareBridgeProvider><LoginPage /></CareBridgeProvider>);
const renderSignup = () => render(<CareBridgeProvider><SignupPage /></CareBridgeProvider>);

beforeEach(() => {
  replaced.length = 0;
  session.authenticated = false;
  session.account = null;
  session.refresh = vi.fn();
  window.localStorage.clear();
  stubApi();
});

// ------------------------------------------------------------------- sign-in
describe("sign-in", () => {
  it("asks for a mobile number and nothing else", () => {
    renderLogin();
    expect(screen.getByPlaceholderText("98765 43210")).toBeTruthy();
    expect(screen.getByRole("button", { name: /continue/i })).toBeTruthy();
  });

  it("signs in with ONE call — there is no code step", async () => {
    const calls = stubApi();
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toContain("/v1/auth/sign-in");
    expect(calls[0].body).toEqual({ mobile: MOBILE_E164, intent: "login" });
    // Never a second request, and never an OTP endpoint.
    expect(calls.some((c) => /otp/i.test(c.url))).toBe(false);
  });

  it("normalises a 10-digit number to E.164 before the API sees it", async () => {
    const calls = stubApi();
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: "98765 43210" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(calls[0].body.mobile).toBe(MOBILE_E164));
  });

  it("refuses a short number without calling the API", async () => {
    const calls = stubApi();
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: "12345" } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByText(/enter a 10-digit mobile number/i);
    expect(calls).toHaveLength(0);
  });

  it("stores the application session token", async () => {
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() =>
      expect(window.localStorage.getItem("dr_session_token")).toBe("app-session-token"));
  });

  it("goes where the BACKEND says, not where the browser thinks", async () => {
    stubApi(200, { ...OK_SESSION, next: "/reports",
                   account: { ...OK_SESSION.account, role: "doctor", can_read_reports: true } });
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await waitFor(() => expect(replaced).toContain("/reports"));
  });

  it("says plainly that the number is not verified", () => {
    renderLogin();
    expect(screen.getByText(/does not verify your number/i)).toBeTruthy();
  });

  it("shows no OTP input, no resend and no SMS claim", () => {
    renderLogin();
    const text = (document.body.textContent || "").toLowerCase();
    for (const gone of ["otp", "resend", "sent by sms", "verification code"]) {
      expect(text).not.toContain(gone);
    }
    // Exactly one input — the phone number. The six OTP boxes are gone with the step
    // they belonged to.
    expect(document.querySelectorAll("input")).toHaveLength(1);
    expect(document.querySelector("input")?.getAttribute("type")).toBe("tel");
  });
});

// -------------------------------------------------------------- error states
describe("error states", () => {
  it("surfaces a suspended account rather than signing in", async () => {
    stubApi(403, refusal("account_suspended", "This account is not active."));
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(await screen.findByText(/not active/i)).toBeTruthy();
    expect(window.localStorage.getItem("dr_session_token")).toBeNull();
    expect(replaced).toHaveLength(0);
  });

  it("says the backend is unreachable when the request cannot connect", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    expect(await screen.findByText(/cannot connect to the screening server/i)).toBeTruthy();
  });

  it("never shows a raw error code to the person", async () => {
    stubApi(403, refusal("account_suspended", "This account is not active."));
    renderLogin();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /continue/i }));
    await screen.findByText(/not active/i);
    const text = document.body.textContent || "";
    for (const leak of ["account_suspended", "detail", "Traceback"]) {
      expect(text).not.toContain(leak);
    }
  });
});

// -------------------------------------------------------------------- signup
describe("signup", () => {
  it("creates a user account in one call", async () => {
    const calls = stubApi(200, { ...OK_SESSION, created: true });
    renderSignup();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toContain("/v1/auth/sign-in");
    expect(calls[0].body.intent).toBe("signup");
    expect(calls[0].body.role).toBe("user");
  });

  it("refuses to submit a doctor account without the claimed credentials", async () => {
    const calls = stubApi();
    renderSignup();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByText("Doctor Account"));
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));
    await screen.findByText(/enter the doctor.s full name/i);
    expect(calls).toHaveLength(0);
  });

  it("sends the doctor claim, and lands on pending rather than on reports", async () => {
    const calls = stubApi(200, {
      ...OK_SESSION, created: true, doctor_verification_pending: true,
      account: { ...OK_SESSION.account, role: "doctor", doctor_verified: false,
                 can_read_reports: false },
    });
    renderSignup();
    fireEvent.change(screen.getByPlaceholderText("98765 43210"),
                     { target: { value: MOBILE_TYPED } });
    fireEvent.click(screen.getByText("Doctor Account"));
    fireEvent.change(screen.getByPlaceholderText("Dr A. Sharma"),
                     { target: { value: "Dr Rao" } });
    fireEvent.change(screen.getByPlaceholderText("TN/12345/2018"),
                     { target: { value: "TN-12345" } });
    fireEvent.change(screen.getByPlaceholderText("District Hospital, Erode"),
                     { target: { value: "District Hospital" } });
    fireEvent.click(screen.getByRole("button", { name: /create account/i }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].body.role).toBe("doctor");
    expect(calls[0].body.doctor_profile).toEqual({
      doctor_name: "Dr Rao",
      registration_number: "TN-12345",
      hospital: "District Hospital",
    });
    // The claim does not become a privilege: the UI lands on "pending", not /reports.
    expect(await screen.findByText(/verification pending/i)).toBeTruthy();
    expect(replaced).not.toContain("/reports");
  });
});
