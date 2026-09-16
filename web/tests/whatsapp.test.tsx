/**
 * WhatsApp report delivery — the states a screenshot cannot prove.
 *
 * The happy path is the easy part. What has to be trusted is what the card does when
 * Twilio is not configured, when the send fails, when the patient taps twice, and when
 * the person reading it does not read English. None of those appear in a rehearsed demo,
 * and one of them — showing "sent" when nothing was sent — would be the single worst
 * bug this feature could have.
 *
 * No test here reaches the network. `fetch` is stubbed, so no Twilio call is possible.
 */
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CareBridgeProvider from "@/components/carebridge/CareBridgeProvider";
import LanguageControl from "@/components/carebridge/LanguageControl";
import CareResult from "@/components/carebridge/CareResult";
import WhatsAppDelivery from "@/components/carebridge/WhatsAppDelivery";
import { DICTIONARIES } from "@/lib/i18n";
import { en } from "@/lib/i18n/translations/en";
import { errorKey, isConfigurationProblem } from "@/lib/whatsapp";
import { makeResult, makeUngradeable } from "./fixtures";

const MASKED = "+91 ***** 40001";
const FULL = "+919812340001";

// The session, mocked at the module boundary. The component reads `mobile_masked` and
// nothing else about the account — the full number never exists on this side.
const session = { authenticated: true, account: { mobile_masked: MASKED } as any };
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => session,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

function Wrap({ children }: { children: React.ReactNode }) {
  return <CareBridgeProvider>{children}</CareBridgeProvider>;
}

/** Stub the one call the card makes, and hand back the recorded requests. */
function stubSend(response: any, status = 200) {
  const calls: { url: string; body: any }[] = [];
  const fetchMock = vi.fn(async (url: string, init: any) => {
    calls.push({ url: String(url), body: JSON.parse(init?.body || "{}") });
    return {
      ok: status >= 200 && status < 300,
      status,
      json: async () => response,
    } as unknown as Response;
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

/** A send that does not resolve until the test lets it, so the sending state is real. */
function stubPendingSend() {
  let release!: (v: any) => void;
  const pending = new Promise((res) => { release = res; });
  vi.stubGlobal("fetch", vi.fn(async () => {
    await pending;
    return { ok: true, status: 200, json: async () => OK } as unknown as Response;
  }));
  return () => act(async () => { release(null); await Promise.resolve(); });
}

const OK = {
  success: true, channel: "whatsapp", message: "Report sent successfully",
  to_masked: MASKED, sent_at: "2026-09-16T09:05:00Z", duplicate: false,
};

/** The button by the words written on it — which, per WCAG 2.5.3, are also its
 *  accessible name. Finding it any other way would not prove that. */
const sendButton = () => screen.getByRole("button", {
  name: new RegExp(`${en.whatsapp.send}|${en.whatsapp.sending}|${en.whatsapp.retry}`),
});
const sendButtonIn = (dict: typeof en) => screen.getByRole("button", {
  name: new RegExp(`${dict.whatsapp.send}|${dict.whatsapp.sending}|${dict.whatsapp.retry}`),
});

function chooseLanguage(native: string) {
  fireEvent.click(screen.getByRole("button", { name: en.a11y.openLanguageMenu }));
  fireEvent.click(screen.getByRole("radio", { name: new RegExp(native) }));
}

// ---------------------------------------------------------------- 1. the offer
describe("the delivery card", () => {
  it("offers delivery to the registered number, masked", () => {
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    expect(screen.getByRole("heading", { name: en.whatsapp.readyTitle })).toBeInTheDocument();
    expect(screen.getAllByText(MASKED).length).toBeGreaterThan(0);
    expect(sendButton()).toBeEnabled();
  });

  it("never shows the patient's full number, and never asks them to type one", () => {
    const { container } = render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    expect(container.textContent).not.toContain(FULL);
    expect(container.querySelectorAll("input")).toHaveLength(0);
  });

  it("does not appear when no report was generated", () => {
    render(<Wrap><WhatsAppDelivery r={makeUngradeable()} /></Wrap>);
    expect(screen.queryByText(en.whatsapp.readyTitle)).not.toBeInTheDocument();
  });

  it("does not appear to someone who is not signed in", () => {
    session.authenticated = false;
    try {
      render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
      expect(screen.queryByText(en.whatsapp.readyTitle)).not.toBeInTheDocument();
    } finally {
      session.authenticated = true;
    }
  });

  it("sits inside the result page, after the result and the next steps", () => {
    render(<Wrap><CareResult r={makeResult()} /></Wrap>);
    const { textContent } = document.body;
    expect(textContent).toContain(en.result.whatItMeans);
    expect(textContent).toContain(en.whatsapp.readyTitle);
    expect(textContent!.indexOf(en.actions.title))
      .toBeLessThan(textContent!.indexOf(en.whatsapp.readyTitle));
  });
});

// ------------------------------------------------------------- 2. button states
describe("button states", () => {
  it("shows a sending state and refuses further presses while it is in flight", async () => {
    const finish = stubPendingSend();
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    fireEvent.click(sendButton());

    await waitFor(() => expect(sendButton()).toBeDisabled());
    expect(sendButton()).toHaveAttribute("aria-busy", "true");
    expect(screen.getAllByText(en.whatsapp.sending).length).toBeGreaterThan(0);

    await finish();
    await waitFor(() => expect(screen.getByText(en.whatsapp.successTitle)).toBeInTheDocument());
  });

  it("confirms success only after the backend says the message was accepted", async () => {
    stubSend(OK);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    // Before the click there is no claim of any kind.
    expect(screen.queryByText(en.whatsapp.successTitle)).not.toBeInTheDocument();
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.successTitle)).toBeInTheDocument();
    expect(screen.getByText(en.whatsapp.successHint)).toBeInTheDocument();
    expect(screen.getAllByText(MASKED).length).toBeGreaterThan(0);
  });

  it("shows a failure, not a success, when the backend refuses", async () => {
    stubSend({ success: false, code: "recipient_not_reachable", message: "" }, 400);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.errors.notReachable)).toBeInTheDocument();
    expect(screen.queryByText(en.whatsapp.successTitle)).not.toBeInTheDocument();
  });

  it("offers Try again after a failure, and can succeed on the retry", async () => {
    stubSend({ success: false, code: "provider_unreachable" }, 502);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(sendButton()).toHaveTextContent(en.whatsapp.retry);

    stubSend(OK);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.successTitle)).toBeInTheDocument();
  });

  it("says delivery is not configured rather than pretending it worked", async () => {
    stubSend({ success: false, code: "not_configured",
               message: "WhatsApp delivery is not configured." }, 503);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.errors.notConfigured)).toBeInTheDocument();
    // …and points out that the report itself is still available.
    expect(screen.getByText(en.whatsapp.errors.notConfiguredHint)).toBeInTheDocument();
    expect(screen.queryByText(en.whatsapp.successTitle)).not.toBeInTheDocument();
  });

  it("stops offering a retry that cannot possibly succeed", async () => {
    // A trial-tier refusal answers identically every time, so inviting "Try again"
    // just walks the patient into the same wall. The report hint stays.
    stubSend({ success: false, code: "provider_trial_limited" }, 503);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.errors.trialLimited)).toBeInTheDocument();
    // The button is deliberately no longer named "Try again", so it is found by its
    // new label rather than by the send/retry helper.
    const btn = screen.getByRole("button", {
      name: new RegExp(en.whatsapp.failedShort),
    });
    expect(btn).toBeDisabled();
    expect(screen.queryByRole("button", {
      name: new RegExp(en.whatsapp.retry),
    })).not.toBeInTheDocument();
    expect(screen.getByText(en.whatsapp.errors.notConfiguredHint)).toBeInTheDocument();
  });

  it("explains a Meta test-list refusal without offering a pointless retry", async () => {
    // The Meta equivalent of the trial wall: the WhatsApp app is still in test mode and
    // this number was never added to its allow-list. Only an operator can change that,
    // so the patient gets the reason and the download, not a "Try again" treadmill.
    stubSend({ success: false, code: "recipient_not_allowed" }, 503);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.errors.recipientNotAllowed)).toBeInTheDocument();
    expect(screen.queryByRole("button", {
      name: new RegExp(en.whatsapp.retry),
    })).not.toBeInTheDocument();
    expect(screen.getByText(en.whatsapp.errors.notConfiguredHint)).toBeInTheDocument();
    expect(screen.queryByText(en.whatsapp.successTitle)).not.toBeInTheDocument();
  });

  it("names the verified destination number before anything is sent", async () => {
    // The patient should know WHERE the report is going before they tap, not after.
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    expect(screen.getByText(en.whatsapp.verifiedNumberIntro)).toBeInTheDocument();
  });

  it("reports a queued message as queued, not as delivered", async () => {
    // Twilio answers "queued"; claiming anything stronger would be a delivery promise
    // we have not been given.
    stubSend({ ...OK, status: "queued", message_sid: "SM_x" });
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.queuedShort)).toBeInTheDocument();
  });

  it("treats a network failure as a failure", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network"); }));
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.whatsapp.errors.generic)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------- 3. duplicates
describe("duplicate protection", () => {
  it("a double tap makes one request, not two", async () => {
    const finish = stubPendingSend();
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    const button = sendButton();
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);
    await finish();
    expect((globalThis.fetch as any).mock.calls).toHaveLength(1);
  });

  it("there is no button left to press once the report has been sent", async () => {
    stubSend(OK);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.queryByRole("button", { name: new RegExp(en.whatsapp.send) })).not.toBeInTheDocument();
  });
});

// ------------------------------------------------------------- 4. the request
describe("what is actually sent", () => {
  it("names the scan and the language, and nothing else", async () => {
    const calls = stubSend(OK);
    render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(calls).toHaveLength(1);
    expect(calls[0].url).toContain("/v1/reports/scan_test_0001/whatsapp");
    // The recipient is NOT in the request. The backend derives it from the session.
    expect(Object.keys(calls[0].body)).toEqual(["language"]);
    expect(JSON.stringify(calls[0].body)).not.toContain(FULL);
  });

  it("carries the CareBridge language the person is actually reading in", async () => {
    const calls = stubSend(OK);
    render(<Wrap><LanguageControl /><WhatsAppDelivery r={makeResult()} /></Wrap>);
    chooseLanguage("తెలుగు");
    await act(async () => { fireEvent.click(sendButtonIn(DICTIONARIES.te)); });
    expect(calls[0].body.language).toBe("te");
  });
});

// ------------------------------------------------------------------- 5. i18n
describe("language", () => {
  it.each([
    ["hi", "हिन्दी", /[ऀ-ॿ]/],
    ["te", "తెలుగు", /[ఀ-౿]/],
    ["pa", "ਪੰਜਾਬੀ", /[਀-੿]/],
  ] as const)("renders the whole card in %s", (code, native, script) => {
    render(<Wrap><LanguageControl /><WhatsAppDelivery r={makeResult()} /></Wrap>);
    chooseLanguage(native);
    const dict = DICTIONARIES[code].whatsapp;
    expect(screen.getByRole("heading", { name: dict.readyTitle })).toBeInTheDocument();
    expect(sendButtonIn(DICTIONARIES[code])).toHaveTextContent(dict.send);
    expect(script.test(dict.send)).toBe(true);
    expect(script.test(dict.explain)).toBe(true);
  });

  it("reports a failure in the reader's language too", async () => {
    stubSend({ success: false, code: "recipient_not_reachable" }, 400);
    render(<Wrap><LanguageControl /><WhatsAppDelivery r={makeResult()} /></Wrap>);
    chooseLanguage("हिन्दी");
    await act(async () => { fireEvent.click(sendButtonIn(DICTIONARIES.hi)); });
    expect(screen.getByText(DICTIONARIES.hi.whatsapp.errors.notReachable)).toBeInTheDocument();
  });

  it("every language carries every delivery key, in its own words", () => {
    const keys = Object.keys(en.whatsapp.errors) as (keyof typeof en.whatsapp.errors)[];
    for (const code of ["hi", "te", "pa"] as const) {
      const dict = DICTIONARIES[code].whatsapp;
      for (const k of keys) {
        expect(dict.errors[k]?.trim(), `${code}.whatsapp.errors.${k}`).toBeTruthy();
        expect(dict.errors[k]).not.toBe(en.whatsapp.errors[k]);
      }
      for (const k of ["send", "sending", "sentShort", "failedShort", "retry",
                       "readyTitle", "readyBody", "explain", "successTitle"] as const) {
        expect(dict[k]?.trim(), `${code}.whatsapp.${k}`).toBeTruthy();
        expect(dict[k]).not.toBe(en.whatsapp[k]);
      }
    }
  });
});

// -------------------------------------------------------- 6. the error mapping
describe("error codes", () => {
  it("maps every backend code to a sentence, and unknown codes to the generic one", () => {
    expect(errorKey("session_window_closed")).toBe("whatsapp.errors.sessionClosed");
    expect(errorKey("something_new_from_twilio")).toBe("whatsapp.errors.generic");
    expect(errorKey(undefined)).toBe("whatsapp.errors.generic");
  });

  it("knows which failures a retry cannot fix", () => {
    expect(isConfigurationProblem("not_configured")).toBe(true);
    expect(isConfigurationProblem("sender_not_whatsapp")).toBe(true);
    expect(isConfigurationProblem("rate_limited")).toBe(false);
  });
});

// ----------------------------------------------------- 7. the medical guarantee
describe("delivery changes nothing clinical", () => {
  it("shows no grade, no referral and no confidence of its own", () => {
    const { container } = render(<Wrap><WhatsAppDelivery r={makeResult()} /></Wrap>);
    for (const clinical of ["Moderate NPDR", "Grade 2", "77%", "referable"]) {
      expect(container.textContent).not.toContain(clinical);
    }
  });

  it("leaves the result and the report on the page when delivery fails", async () => {
    stubSend({ success: false, code: "provider_error" }, 502);
    render(<Wrap><CareResult r={makeResult()} onDownload={() => {}} /></Wrap>);
    await act(async () => { fireEvent.click(sendButton()); });
    expect(screen.getByText(en.result.whatItMeans)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en.actions.download })).toBeInTheDocument();
    expect(document.body.textContent).toContain(en.whatsapp.alsoDownload);
  });
});
