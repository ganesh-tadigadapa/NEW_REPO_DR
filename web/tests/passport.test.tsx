/**
 * CareBridge Eye Health Passport — the front-end states a screenshot cannot prove.
 *
 * The happy path (grade 1 -> grade 2, "+1 ICDR category") is the easy part. What has to
 * be trusted is what these components render when there is NO previous screening, when
 * the current photograph could not be graded, when the reader does not read English,
 * and when WhatsApp refuses — because none of those appear in a rehearsed demo, and one
 * of them (claiming the disease has worsened from two screening results) would be the
 * single worst bug this feature could have.
 *
 * No test here reaches the network. `fetch` is stubbed throughout.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CareBridgeProvider from "@/components/carebridge/CareBridgeProvider";
import ComparisonCard from "@/components/passport/ComparisonCard";
import ComparisonDelivery from "@/components/passport/ComparisonDelivery";
import EyeHealthJourney from "@/components/passport/EyeHealthJourney";
import FollowUpCard from "@/components/passport/FollowUpCard";
import GradeTimeline from "@/components/passport/GradeTimeline";
import ReturningBanner from "@/components/passport/ReturningBanner";
import { DICTIONARIES } from "@/lib/i18n";
import { gradeTone } from "@/lib/passport";
import type { Comparison, FollowUp, TimelinePoint } from "@/lib/passport";

const MASKED = "+91 ***** 40001";
const session = { authenticated: true, account: { mobile_masked: MASKED } as any };
vi.mock("@/components/AuthProvider", () => ({
  useAuth: () => session,
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

function Wrap({ children }: { children: React.ReactNode }) {
  return <CareBridgeProvider>{children}</CareBridgeProvider>;
}

function point(over: Partial<TimelinePoint> = {}): TimelinePoint {
  return {
    screening_id: "sc_1",
    date: "2026-09-16T09:00:00Z",
    icdr_grade: 1,
    severity_label: "Mild NPDR",
    quality_status: "pass",
    gradeable: true,
    referable: false,
    confidence: 0.8,
    report_available: true,
    clinician_review_status: "pending",
    clinician_grade: null,
    ...over,
  };
}

/** The shape `src/passport/comparison.py::compare` returns, verbatim. */
function comparison(over: Partial<Extract<Comparison, { available: true }>> = {}) {
  return {
    available: true as const,
    previous: {
      screening_id: "sc_1", date: "2026-09-16T09:00:00Z", icdr_grade: 1,
      severity_label: "Mild NPDR", referable: false, confidence: 0.8,
      quality_status: "pass", report_available: true,
      clinician_review_status: "pending", clinician_grade: null,
      clinician_reviewed_at: null,
    },
    current: {
      screening_id: "sc_2", date: "2027-03-16T09:00:00Z", icdr_grade: 2,
      severity_label: "Moderate NPDR", referable: true, confidence: 0.77,
      quality_status: "pass", report_available: true,
      clinician_review_status: "pending", clinician_grade: null,
      clinician_reviewed_at: null,
    },
    previous_grade: 1,
    current_grade: 2,
    grade_change: 1,
    change_direction: "higher" as const,
    change_label: "One ICDR category higher",
    statement: "The current screening result is one ICDR category higher than the previous screening.",
    quality_change: { previous: "pass", current: "pass", changed: false },
    referral_change: {
      previous: false, current: true, newly_referable: true, no_longer_referable: false,
    },
    clinician_review_change: { previous: "pending", current: "pending" },
    interval_days: 181,
    disclaimer: "This compares two screening results. It is not a diagnosis, and it is not by itself evidence that the disease has changed. Only an eye-care professional can say that.",
    ...over,
  };
}

function followUp(over: Partial<FollowUp> = {}): FollowUp {
  return {
    follow_up_id: "fu_1",
    account_id: "acc_1",
    screening_id: "sc_2",
    created_at: "2027-03-16T09:00:00Z",
    recommended_window: {
      min_months: 3, max_months: 3, label: "in about 3 months",
      priority: "prompt", headline: "Prompt specialist assessment suggested",
    },
    due_at: "2027-06-14T09:00:00Z",
    basis: "guideline_escalated",
    basis_label: "Guideline-informed follow-up window, brought forward",
    basis_note: "Guideline-informed suggestion.",
    reason: "Suggested from the configured follow-up window for ICDR grade 2.",
    clinician_override: false,
    status: "scheduled",
    reminder_status: "pending",
    channel: "whatsapp",
    priority: "prompt",
    referral_indicated: true,
    specialist_referral: true,
    ...over,
  };
}

function stubFetch(response: any, ok = true, status = 200) {
  const calls: { url: string; body: any }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, init: any) => {
    calls.push({ url: String(url), body: init?.body ? JSON.parse(init.body) : null });
    return { ok, status, json: async () => response,
             blob: async () => new Blob(["%PDF"]) } as unknown as Response;
  }));
  return calls;
}

// =============================================================== the comparison
describe("the comparison card", () => {
  it("shows both results and the category change", () => {
    render(<Wrap><ComparisonCard comparison={comparison()} /></Wrap>);
    expect(screen.getByText("Screening comparison")).toBeInTheDocument();
    expect(screen.getByText("Mild NPDR")).toBeInTheDocument();
    expect(screen.getByText("Moderate NPDR")).toBeInTheDocument();
    expect(screen.getByText("1 → 2")).toBeInTheDocument();
    expect(screen.getByText("+1")).toBeInTheDocument();
    // The compact chip is the translated template; the sentence below it is the
    // backend's own wording. Both are on the card, and they say the same thing.
    expect(screen.getByText("1 ICDR category higher")).toBeInTheDocument();
    expect(screen.getByText(/one ICDR category higher than the previous screening/))
      .toBeInTheDocument();
  });

  it("renders the backend's sentence verbatim and claims nothing more", () => {
    render(<Wrap><ComparisonCard comparison={comparison()} /></Wrap>);
    const statement = comparison().statement;
    expect(screen.getByText(statement)).toBeInTheDocument();
    const body = document.body.textContent!.toLowerCase();
    for (const claim of ["worsened", "progressed", "deteriorated", "definitely"]) {
      expect(body).not.toContain(claim);
    }
  });

  it("carries the not-a-diagnosis caveat on the card itself", () => {
    render(<Wrap><ComparisonCard comparison={comparison()} /></Wrap>);
    expect(screen.getByText(/It is not a diagnosis/i)).toBeInTheDocument();
  });

  it("says so when the grade is unchanged", () => {
    render(<Wrap><ComparisonCard comparison={comparison({
      previous_grade: 2, current_grade: 2, grade_change: 0,
      change_direction: "same", change_label: "Same ICDR category",
      statement: "The current screening result is in the same ICDR category as the previous screening.",
      referral_change: { previous: true, current: true, newly_referable: false, no_longer_referable: false },
    })} /></Wrap>);
    expect(screen.getByText("Same ICDR category")).toBeInTheDocument();
    expect(screen.getByText("2 → 2")).toBeInTheDocument();
    expect(screen.getByText("0")).toBeInTheDocument();
  });

  it("says so when the grade is lower, without claiming an improvement", () => {
    render(<Wrap><ComparisonCard comparison={comparison({
      previous_grade: 3, current_grade: 2, grade_change: -1,
      change_direction: "lower", change_label: "One ICDR category lower",
      statement: "The current screening result is one ICDR category lower than the previous screening.",
      referral_change: { previous: true, current: true, newly_referable: false, no_longer_referable: false },
    })} /></Wrap>);
    expect(screen.getByText("3 → 2")).toBeInTheDocument();
    expect(screen.getByText("-1")).toBeInTheDocument();
    expect(screen.getByText("1 ICDR category lower")).toBeInTheDocument();
    expect(document.body.textContent!.toLowerCase()).not.toContain("improved");
  });

  it("explains a first screening rather than rendering a blank card", () => {
    render(<Wrap><ComparisonCard comparison={{
      available: false, reason: "no_previous_screening", disclaimer: "…",
    }} /></Wrap>);
    expect(screen.getByText("This is your first screening")).toBeInTheDocument();
    expect(screen.queryByText(/ICDR category/)).not.toBeInTheDocument();
  });

  it("refuses to compare an ungradeable screening and says why", () => {
    render(<Wrap><ComparisonCard comparison={{
      available: false, reason: "current_screening_ungradeable", disclaimer: "…",
    }} /></Wrap>);
    expect(screen.getByText("This photograph could not be graded")).toBeInTheDocument();
    expect(screen.getByText(/not a result, so it is not compared/i)).toBeInTheDocument();
  });

  it("flags a newly referable result", () => {
    render(<Wrap><ComparisonCard comparison={comparison()} /></Wrap>);
    expect(screen.getByText(/Clinical follow-up is recommended/)).toBeInTheDocument();
  });
});

// ================================================================= the timeline
describe("the ICDR grade timeline", () => {
  const points = [
    point({ screening_id: "sc_1", icdr_grade: 1 }),
    point({ screening_id: "sc_2", date: "2027-03-16T09:00:00Z", icdr_grade: 2,
            severity_label: "Moderate NPDR", referable: true }),
  ];

  it("draws one marker per screening, each labelled with its grade", () => {
    const { container } = render(<Wrap><GradeTimeline points={points} /></Wrap>);
    expect(container.querySelectorAll(".pp-point")).toHaveLength(2);
    expect(container.querySelector("text.pp-plabel")?.textContent).toBe("G1");
  });

  it("labels the y axis with every ICDR category, 0 to 4", () => {
    const { container } = render(<Wrap><GradeTimeline points={points} /></Wrap>);
    const axis = Array.from(container.querySelectorAll("text.pp-axis"))
      .map((n) => n.textContent);
    for (const g of ["G0", "G1", "G2", "G3", "G4"]) expect(axis).toContain(g);
  });

  it("draws a STEP path, never a sloped one, because the grade is ordinal", () => {
    const { container } = render(<Wrap><GradeTimeline points={points} /></Wrap>);
    const d = container.querySelector("path.pp-line")?.getAttribute("d") || "";
    // A step is: move, hold at the OLD y across to the new x, then change y in place.
    const segments = d.match(/L [\d.]+ [\d.]+/g) || [];
    expect(segments).toHaveLength(2);
    const [hold, change] = segments as [string, string];
    const [holdX, holdY] = hold.slice(2).split(" ").map(Number);
    const [changeX, changeY] = change.slice(2).split(" ").map(Number);
    expect(changeX).toBe(holdX);          // the category change is vertical
    expect(changeY).not.toBe(holdY);
  });

  it("does not run the line through an ungradeable visit", () => {
    const withRefusal = [
      points[0],
      point({ screening_id: "sc_bad", date: "2026-12-16T09:00:00Z",
              icdr_grade: null, gradeable: false, quality_status: "refused",
              severity_label: null }),
      points[1],
    ];
    const { container } = render(<Wrap><GradeTimeline points={withRefusal} /></Wrap>);
    // Three visits are drawn — the refusal is part of the history…
    expect(container.querySelectorAll(".pp-point")).toHaveLength(3);
    expect(container.querySelectorAll(".pp-dot.hollow")).toHaveLength(1);
    // …but only the two graded ones are on the line.
    const d = container.querySelector("path.pp-line")?.getAttribute("d") || "";
    expect((d.match(/L /g) || []).length).toBe(2);
  });

  it("gives every point an accessible name naming the date and the grade", () => {
    render(<Wrap><GradeTimeline points={points} /></Wrap>);
    expect(screen.getByLabelText(/16 Sep.*2026.*grade 1/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/16 Mar 2027.*grade 2/i)).toBeInTheDocument();
  });

  it("opens that screening when a point is clicked or activated by keyboard", () => {
    const picked: string[] = [];
    render(<Wrap>
      <GradeTimeline points={points} onSelect={(p) => picked.push(p.screening_id)} />
    </Wrap>);
    const marks = document.querySelectorAll(".pp-point");
    fireEvent.click(marks[1]);
    fireEvent.keyDown(marks[0], { key: "Enter" });
    expect(picked).toEqual(["sc_2", "sc_1"]);
  });

  it("renders nothing at all rather than an empty frame with no data", () => {
    const { container } = render(<Wrap><GradeTimeline points={[]} /></Wrap>);
    expect(container.querySelector("svg")).toBeNull();
  });
});

// ================================================================== the journey
describe("the eye health journey", () => {
  it("lists every screening oldest first, with its severity in words", () => {
    render(<Wrap><EyeHealthJourney points={[
      point({ screening_id: "sc_1", icdr_grade: 1 }),
      point({ screening_id: "sc_2", date: "2027-03-16T09:00:00Z", icdr_grade: 2,
              severity_label: "Moderate NPDR", referable: true }),
    ]} /></Wrap>);
    const dates = Array.from(document.querySelectorAll(".pp-stepdate"))
      .map((n) => n.textContent!);
    expect(dates).toHaveLength(2);
    expect(dates[0]).toMatch(/16 Sep.*2026/);
    expect(dates[1]).toMatch(/16 Mar 2027/);
    expect(screen.getByText(/Mild NPDR/)).toBeInTheDocument();
    expect(screen.getByText(/Moderate NPDR/)).toBeInTheDocument();
  });

  it("shows the change against the previous graded screening", () => {
    render(<Wrap><EyeHealthJourney points={[
      point({ screening_id: "sc_1", icdr_grade: 1 }),
      point({ screening_id: "sc_2", date: "2027-03-16T09:00:00Z", icdr_grade: 2 }),
    ]} /></Wrap>);
    expect(screen.getByText("1 ICDR category higher")).toBeInTheDocument();
  });

  it("skips an ungradeable visit when working out the change", () => {
    render(<Wrap><EyeHealthJourney points={[
      point({ screening_id: "sc_1", icdr_grade: 1 }),
      point({ screening_id: "sc_bad", date: "2026-12-16T09:00:00Z", icdr_grade: null,
              gradeable: false, quality_status: "refused", severity_label: null }),
      point({ screening_id: "sc_3", date: "2027-03-16T09:00:00Z", icdr_grade: 2 }),
    ]} /></Wrap>);
    // Grade 2 is compared with grade 1, not with the refusal between them.
    expect(screen.getByText("1 ICDR category higher")).toBeInTheDocument();
    expect(screen.getAllByText(/could not be graded/i).length).toBeGreaterThan(0);
  });

  it("shows the follow-up reminder as the connector between two visits", () => {
    render(<Wrap><EyeHealthJourney
      points={[
        point({ screening_id: "sc_1", icdr_grade: 1 }),
        point({ screening_id: "sc_2", date: "2027-03-16T09:00:00Z", icdr_grade: 2 }),
      ]}
      followUps={[followUp({ screening_id: "sc_1" })]}
    /></Wrap>);
    expect(screen.getByText(/Follow-up reminder/)).toBeInTheDocument();
  });
});

// ================================================================ the follow-up
describe("the follow-up card", () => {
  it("presents the window as a SUGGESTION, never as an instruction", () => {
    render(<Wrap><FollowUpCard followUp={followUp()} /></Wrap>);
    expect(screen.getByText(/Prompt specialist assessment suggested: in about 3 months/))
      .toBeInTheDocument();
    const body = document.body.textContent!.toLowerCase();
    expect(body).not.toContain("you must");
    expect(body).toContain("not a prescription");
  });

  it("does not hard-code one interval — it renders the plan it is given", () => {
    const { unmount } = render(<Wrap><FollowUpCard followUp={followUp({
      recommended_window: { min_months: 12, max_months: 12, label: "in about 12 months",
                            priority: "routine", headline: "Suggested follow-up screening" },
      priority: "routine",
    })} /></Wrap>);
    expect(screen.getByText(/in about 12 months/)).toBeInTheDocument();
    unmount();
    render(<Wrap><FollowUpCard followUp={followUp()} /></Wrap>);
    expect(screen.getByText(/in about 3 months/)).toBeInTheDocument();
  });

  it("names the clinician when they set the follow-up outright", () => {
    render(<Wrap><FollowUpCard followUp={followUp({
      basis: "clinician_override", clinician_override: true,
      basis_label: "Follow-up recommended by the reviewing clinician",
    })} /></Wrap>);
    // The basis label already says it; the card must not say it twice.
    expect(screen.getByText(/Follow-up recommended by the reviewing clinician/))
      .toBeInTheDocument();
    expect(screen.queryByText(/Set by the reviewing clinician/)).not.toBeInTheDocument();
  });

  it("names the clinician when their GRADE drove the window", () => {
    render(<Wrap><FollowUpCard followUp={followUp({
      basis: "clinician_grade", clinician_override: true,
      basis_label: "Guideline-informed window, using the clinician's grade",
    })} /></Wrap>);
    expect(screen.getByText(/Set by the reviewing clinician/)).toBeInTheDocument();
  });

  it("reports a reminder as sent only after the provider accepted it", async () => {
    stubFetch({ success: true, channel: "whatsapp", status: "queued" });
    render(<Wrap><FollowUpCard followUp={followUp()} /></Wrap>);
    expect(screen.getByText("Reminder not sent yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Send me this reminder/i }));
    await waitFor(() =>
      expect(screen.getByText("Reminder sent to WhatsApp")).toBeInTheDocument());
  });

  it("never claims a reminder was sent when the provider refused", async () => {
    stubFetch({ success: false, code: "recipient_not_reachable" }, false, 400);
    render(<Wrap><FollowUpCard followUp={followUp()} /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: /Send me this reminder/i }));
    await waitFor(() =>
      expect(screen.getByText(/has not joined WhatsApp/i)).toBeInTheDocument());
    expect(screen.queryByText("Reminder sent to WhatsApp")).not.toBeInTheDocument();
  });

  it("offers no reminder button on a page that cannot send one", () => {
    render(<Wrap><FollowUpCard followUp={followUp()} canRemind={false} /></Wrap>);
    expect(screen.queryByRole("button", { name: /reminder/i })).not.toBeInTheDocument();
  });
});

// ================================================== the comparison on WhatsApp
describe("comparison delivery", () => {
  it("names the verified number and never asks the patient to type one", () => {
    stubFetch({});
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    expect(screen.getAllByText(MASKED).length).toBeGreaterThan(0);
    expect(document.querySelectorAll("input[type=tel]")).toHaveLength(0);
    expect(document.querySelectorAll("input")).toHaveLength(0);
  });

  it("sends only the language, and to the comparison endpoint", async () => {
    const calls = stubFetch({ success: true, channel: "whatsapp", status: "queued",
                              to_masked: MASKED });
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: /Send comparison/i }));
    await waitFor(() => expect(calls.length).toBe(1));
    expect(calls[0].url).toContain("/v1/passport/screenings/sc_2/comparison/whatsapp");
    expect(Object.keys(calls[0].body)).toEqual(["language"]);
  });

  it("claims success only once the provider accepted the message", async () => {
    stubFetch({ success: true, channel: "whatsapp", status: "queued", to_masked: MASKED });
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: /Send comparison/i }));
    await waitFor(() =>
      expect(screen.getByText("Comparison sent successfully")).toBeInTheDocument());
    // "queued" is acceptance, not receipt, and the status line says exactly that.
    expect(screen.getByText(/queued for delivery/i)).toBeInTheDocument();
  });

  it("does not claim success when the provider refused", async () => {
    stubFetch({ success: false, code: "recipient_not_reachable" }, false, 400);
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: /Send comparison/i }));
    await waitFor(() =>
      expect(screen.getByText(/has not joined WhatsApp/i)).toBeInTheDocument());
    expect(screen.queryByText("Comparison sent successfully")).not.toBeInTheDocument();
  });

  it("keeps the download available in every state, not only after a failure", () => {
    stubFetch({});
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    expect(screen.getByRole("button", { name: /Download comparison report/i }))
      .toBeInTheDocument();
  });

  it("still offers the download after WhatsApp has failed", async () => {
    stubFetch({ success: false, code: "not_configured" }, false, 503);
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: /Send comparison/i }));
    await waitFor(() =>
      expect(screen.getByText(/not configured/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: /Download comparison report/i }))
      .toBeEnabled();
  });

  it("does not send twice when the button is tapped twice", async () => {
    let release!: (v: any) => void;
    const pending = new Promise((res) => { release = res; });
    const calls: string[] = [];
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      calls.push(String(url));
      await pending;
      return { ok: true, status: 200,
               json: async () => ({ success: true, status: "queued" }) } as unknown as Response;
    }));
    render(<Wrap><ComparisonDelivery screeningId="sc_2" /></Wrap>);
    const button = screen.getByRole("button", { name: /Send comparison/i });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(calls.length).toBe(1);
    release(null);
  });
});

// ======================================================= the returning patient
describe("the returning-patient banner", () => {
  it("tells a returning patient their previous screening is available", async () => {
    stubFetch({
      has_history: true, history_count: 1,
      last_screening: point(), follow_up: followUp(),
    });
    render(<Wrap><ReturningBanner /></Wrap>);
    await waitFor(() =>
      expect(screen.getByText("Your previous screening is available")).toBeInTheDocument());
    expect(screen.getByText(/16 Sep.*2026/)).toBeInTheDocument();
    expect(screen.getByText(/Last result: Grade 1 of 4/)).toBeInTheDocument();
  });

  it("shows nothing at all to a first-time patient", async () => {
    stubFetch({ has_history: false, history_count: 0, last_screening: null,
                follow_up: null });
    const { container } = render(<Wrap><ReturningBanner /></Wrap>);
    await waitFor(() => expect(container.querySelector(".pp-returning")).toBeNull());
  });

  it("stays silent rather than breaking the page when the passport is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("Failed to fetch"); }));
    const { container } = render(<Wrap><ReturningBanner /></Wrap>);
    await waitFor(() => expect(container.querySelector(".pp-returning")).toBeNull());
  });
});

// ============================================================== the language layer
describe("the passport in every CareBridge language", () => {
  it("has every passport key in all four dictionaries", () => {
    const keys = Object.keys((DICTIONARIES.en as any).passport);
    expect(keys.length).toBeGreaterThan(50);
    for (const code of ["hi", "te", "pa"] as const) {
      const other = (DICTIONARIES[code] as any).passport;
      expect(Object.keys(other).sort()).toEqual(keys.sort());
      for (const key of keys) {
        expect(String(other[key]).trim()).not.toBe("");
        // A dictionary copy-pasted from English would pass a "present" check.
        expect(other[key]).not.toBe((DICTIONARIES.en as any).passport[key]);
      }
    }
  });

  it("keeps the not-a-diagnosis caveat in every language", () => {
    for (const code of ["en", "hi", "te", "pa"] as const) {
      expect(String((DICTIONARIES[code] as any).passport.comparisonNotDiagnosis).trim())
        .not.toBe("");
    }
  });
});

// ================================================================ pure helpers
describe("gradeTone", () => {
  it("maps a grade to the product's existing verdict vocabulary", () => {
    expect(gradeTone(0)).toBe("clear");
    expect(gradeTone(1)).toBe("clear");
    expect(gradeTone(2)).toBe("warn");
    expect(gradeTone(3)).toBe("refer");
    expect(gradeTone(4)).toBe("refer");
    // An ungradeable visit has no grade and therefore no tone.
    expect(gradeTone(null)).toBe("none");
  });
});
