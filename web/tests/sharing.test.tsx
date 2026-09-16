/**
 * Patient -> doctor sharing, from the browser's side.
 *
 * The property this file protects is narrow and important: the UI never decides who may
 * see anything. It mints a code, shows it once, lists what the server says, and asks the
 * server to revoke. Every authorisation answer comes from the API, and no request this
 * page can make carries another account's identifier.
 *
 * `fetch` is stubbed throughout, so nothing here reaches a server.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CareBridgeProvider from "@/components/carebridge/CareBridgeProvider";
import ShareWithDoctor from "@/components/passport/ShareWithDoctor";
import AddPatient from "@/components/AddPatient";
import { en } from "@/lib/i18n/translations/en";
import { DICTIONARIES } from "@/lib/i18n";

type Call = { url: string; method: string; body: any };

const NOBODY = { shared_with: [], count: 0, active_codes: [], note: "" };

const SHARED = {
  shared_with: [{
    doctor_account_id: "acc_doc1", doctor_name: "Dr Rao",
    hospital: "District Hospital", granted_at: "2026-09-16T09:00:00Z",
    reason: "patient_shared_code",
  }],
  count: 1,
  active_codes: [],
  note: "",
};

const MINTED = {
  ok: true, code_id: "shc_1", code: "KXPT-4R9M",
  expires_at: Math.floor(Date.now() / 1000) + 1800, expires_in: 1800, note: "",
};

function stubApi(routes: Record<string, [number, any]>): Call[] {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: any, init: any) => {
    const u = String(url);
    const method = (init?.method || "GET").toUpperCase();
    calls.push({ url: u, method, body: init?.body ? JSON.parse(init.body) : null });
    const key = Object.keys(routes).find((k) => u.includes(k.split(" ")[1] ?? k)
                                                && (k.includes(" ") ? k.startsWith(method) : true));
    if (!key) throw new Error(`unrouted ${method} ${u}`);
    const [status, body] = routes[key];
    return { ok: status >= 200 && status < 300, status, json: async () => body } as unknown as Response;
  }));
  return calls;
}

function renderShare() {
  return render(<CareBridgeProvider><ShareWithDoctor /></CareBridgeProvider>);
}

beforeEach(() => {
  window.localStorage.clear();
  window.localStorage.setItem("dr_session_token", "tok");
});

describe("the patient's sharing panel", () => {
  it("says plainly that nobody has access until they share", async () => {
    stubApi({ "/v1/passport/sharing": [200, NOBODY] });
    renderShare();
    expect(await screen.findByText(en.sharing.nobody)).toBeTruthy();
  });

  it("lists the doctors who currently hold access", async () => {
    stubApi({ "/v1/passport/sharing": [200, SHARED] });
    renderShare();
    expect(await screen.findByText("Dr Rao")).toBeTruthy();
    expect(screen.getByText(/District Hospital/)).toBeTruthy();
    expect(screen.getByRole("button", { name: en.sharing.revoke })).toBeTruthy();
  });

  it("shows the minted code once, and says it will not be shown again", async () => {
    const calls = stubApi({
      "POST /v1/passport/sharing/codes": [200, MINTED],
      "/v1/passport/sharing": [200, NOBODY],
    });
    renderShare();
    await screen.findByText(en.sharing.nobody);
    fireEvent.click(screen.getByRole("button", { name: en.sharing.createCode }));

    expect(await screen.findByText("KXPT-4R9M")).toBeTruthy();
    expect(screen.getByText(en.sharing.codeOnce)).toBeTruthy();
    // Minting carries no body at all — there is nowhere to name a patient or a doctor.
    const mint = calls.find((c) => c.method === "POST");
    expect(mint?.body).toBeNull();
  });

  it("asks the server to revoke, and never decides access itself", async () => {
    const calls = stubApi({
      "POST /v1/passport/sharing/acc_doc1/revoke": [200, { ok: true }],
      "/v1/passport/sharing": [200, SHARED],
    });
    renderShare();
    await screen.findByText("Dr Rao");
    fireEvent.click(screen.getByRole("button", { name: en.sharing.revoke }));

    await waitFor(() => {
      const revoke = calls.find((c) => c.url.includes("/revoke"));
      expect(revoke?.method).toBe("POST");
      // The doctor id is in the PATH the server gave us; the body names nobody.
      expect(revoke?.body).toBeNull();
    });
  });

  it("surfaces a server refusal rather than pretending it worked", async () => {
    stubApi({
      "POST /v1/passport/sharing/codes":
        [429, { detail: { error: { code: "too_many_share_codes",
                                   message: "You already have the maximum number of unused sharing codes." } } }],
      "/v1/passport/sharing": [200, NOBODY],
    });
    renderShare();
    await screen.findByText(en.sharing.nobody);
    fireEvent.click(screen.getByRole("button", { name: en.sharing.createCode }));
    expect(await screen.findByText(/maximum number of unused sharing codes/i)).toBeTruthy();
    expect(screen.queryByText("KXPT-4R9M")).toBeNull();
  });

  it("carries the session token and no other credential", async () => {
    const seen: any[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: any, init: any) => {
      seen.push(Object.fromEntries(new Headers(init?.headers).entries()));
      return { ok: true, status: 200, json: async () => NOBODY } as unknown as Response;
    }));
    renderShare();
    await waitFor(() => expect(seen.length).toBeGreaterThan(0));
    expect(seen[0].authorization).toBe("Bearer tok");
    expect(JSON.stringify(seen)).not.toMatch(/api[-_]?key/i);
  });

  it("is written in the patient's chosen language", async () => {
    stubApi({ "/v1/passport/sharing": [200, NOBODY] });
    window.localStorage.setItem("carebridge_prefs",
      JSON.stringify({ lang: "te", voice: true, level: "simple", chosen: true }));
    renderShare();
    expect(await screen.findByText(DICTIONARIES.te.sharing.nobody)).toBeTruthy();
    expect(screen.getByRole("button",
      { name: DICTIONARIES.te.sharing.createCode })).toBeTruthy();
  });
});

describe("the doctor's add-patient control", () => {
  function renderAdd() {
    return render(<CareBridgeProvider><AddPatient /></CareBridgeProvider>);
  }

  it("sends only the code — there is nowhere to name a patient", async () => {
    const calls = stubApi({ "/v1/passport/sharing/redeem": [200, { ok: true, patient_id: "acc_p1" }] });
    renderAdd();
    fireEvent.change(screen.getByPlaceholderText("ABCD-2345"),
                     { target: { value: "kxpt-4r9m" } });
    fireEvent.click(screen.getByRole("button", { name: en.sharing.doctorAdd }));

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(Object.keys(calls[0].body)).toEqual(["code"]);
    expect(calls[0].body.code).toBe("kxpt-4r9m");
  });

  it("confirms only after the server said yes", async () => {
    stubApi({ "/v1/passport/sharing/redeem": [200, { ok: true, patient_id: "acc_p1" }] });
    renderAdd();
    expect(screen.queryByText(new RegExp(en.sharing.doctorAdded))).toBeNull();
    fireEvent.change(screen.getByPlaceholderText("ABCD-2345"),
                     { target: { value: "KXPT-4R9M" } });
    fireEvent.click(screen.getByRole("button", { name: en.sharing.doctorAdd }));
    expect(await screen.findByText(new RegExp(en.sharing.doctorAdded))).toBeTruthy();
  });

  it("shows the refusal for a bad code and claims nothing", async () => {
    stubApi({
      "/v1/passport/sharing/redeem":
        [400, { detail: { error: { code: "invalid_share_code",
                                   message: "That sharing code is not valid. Ask the patient for a new one." } } }],
    });
    renderAdd();
    fireEvent.change(screen.getByPlaceholderText("ABCD-2345"),
                     { target: { value: "AAAA-2222" } });
    fireEvent.click(screen.getByRole("button", { name: en.sharing.doctorAdd }));
    expect(await screen.findByText(/sharing code is not valid/i)).toBeTruthy();
    expect(screen.queryByText(new RegExp(en.sharing.doctorAdded))).toBeNull();
  });

  it("will not submit an obviously empty code", () => {
    stubApi({ "/v1/passport/sharing/redeem": [200, {}] });
    renderAdd();
    expect(screen.getByRole("button",
      { name: en.sharing.doctorAdd }).hasAttribute("disabled")).toBe(true);
  });
});
