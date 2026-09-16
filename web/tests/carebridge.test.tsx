/**
 * CareBridge — the behaviour a demo cannot prove.
 *
 * A language layer looks fine in every screenshot; what it must be trusted about is what
 * happens at the edges. A missing key, a device with no Telugu voice, an image the
 * quality gate refused — these are exactly the moments when the wrong output would be
 * worst for the person reading it, and none of them appear in a rehearsed demo.
 */
import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import CareBridgeProvider, { useCareBridge } from "@/components/carebridge/CareBridgeProvider";
import LanguageControl from "@/components/carebridge/LanguageControl";
import CareResult from "@/components/carebridge/CareResult";
import SpeakButton from "@/components/carebridge/SpeakButton";
import { Confidence, Verdict } from "@/components/Result";
import {
  DICTIONARIES, LANGUAGES, translate, translateIndexed, translateList, translatorFor,
} from "@/lib/i18n";
import { coverageReport } from "@/lib/i18n/coverage";
import {
  DEFAULT_PREFS, PREFS_KEY, parsePrefs, pickVoice, serializePrefs, speechText,
} from "@/lib/carebridge";
import { en } from "@/lib/i18n/translations/en";
import { installSpeech, makeResult, makeUngradeable, removeSpeech } from "./fixtures";

function Wrap({ children }: { children: React.ReactNode }) {
  return <CareBridgeProvider>{children}</CareBridgeProvider>;
}

/** Switch language through the real control, the way a person does. */
function chooseLanguage(native: string) {
  fireEvent.click(screen.getByRole("button", { name: en.a11y.openLanguageMenu }));
  fireEvent.click(screen.getByRole("radio", { name: new RegExp(native) }));
}

// ---------------------------------------------------------------- 1. defaults
describe("language selection", () => {
  it("defaults to English before anything has been chosen", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    expect(screen.getByRole("button", { name: en.a11y.openLanguageMenu })).toHaveTextContent("English");
  });

  // ------------------------------------------------------------ 2. switching
  it("switches the interface when a language is picked", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    chooseLanguage("తెలుగు");
    expect(screen.getByRole("button", { name: DICTIONARIES.te.a11y.openLanguageMenu }))
      .toHaveTextContent("తెలుగు");
  });

  // -------------------------------------------------- 3-5. the three scripts
  it.each([
    ["hi", "हिन्दी", /[ऀ-ॿ]/],
    ["te", "తెలుగు", /[ఀ-౿]/],
    ["pa", "ਪੰਜਾਬੀ", /[਀-੿]/],
  ] as const)("renders %s in its own script", (code, native, script) => {
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    chooseLanguage(native);
    const explanation = translateIndexed(code, "result.meaning", 2);
    expect(script.test(explanation)).toBe(true);
    expect(screen.getByText(explanation)).toBeTruthy();
  });

  it("offers every registered language, written in its own script", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: en.a11y.openLanguageMenu }));
    for (const l of LANGUAGES) {
      expect(screen.getByRole("radio", { name: new RegExp(l.nativeName) })).toBeTruthy();
    }
  });
});

// ------------------------------------------------------------- 6. persistence
describe("persistence", () => {
  it("writes the choice to localStorage and restores it on the next visit", () => {
    const { unmount } = render(<Wrap><LanguageControl /></Wrap>);
    chooseLanguage("हिन्दी");
    expect(parsePrefs(window.localStorage.getItem(PREFS_KEY)).lang).toBe("hi");
    unmount();

    render(<Wrap><LanguageControl /></Wrap>);
    expect(screen.getByRole("button", { name: DICTIONARIES.hi.a11y.openLanguageMenu }))
      .toHaveTextContent("हिन्दी");
  });

  it("stores the three interface preferences and nothing else", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    chooseLanguage("తెలుగు");
    const stored = JSON.parse(window.localStorage.getItem(PREFS_KEY) as string);
    expect(Object.keys(stored).sort()).toEqual(["chosen", "lang", "level", "voice"]);
  });

  it("leaves the session token alone — changing language must not sign anyone out", () => {
    window.localStorage.setItem("dr_session_token", "tok_abc");
    render(<Wrap><LanguageControl /></Wrap>);
    chooseLanguage("ਪੰਜਾਬੀ");
    expect(window.localStorage.getItem("dr_session_token")).toBe("tok_abc");
  });

  it("survives a corrupt or hand-edited preference without throwing", () => {
    for (const bad of [null, "", "{", "[]", '"te"', '{"lang":"xx","level":"loud"}']) {
      expect(parsePrefs(bad)).toEqual(DEFAULT_PREFS);
    }
    expect(parsePrefs(serializePrefs({ ...DEFAULT_PREFS, lang: "te", chosen: true })))
      .toEqual({ ...DEFAULT_PREFS, lang: "te", chosen: true });
  });
});

// -------------------------------------------------- 7-8. fallback and gaps
describe("fallback", () => {
  it("falls back to English when a translation is blank", () => {
    const saved = DICTIONARIES.te.result.whatItMeans;
    try {
      (DICTIONARIES.te.result as { whatItMeans: string }).whatItMeans = "";
      expect(translate("te", "result.whatItMeans")).toBe(en.result.whatItMeans);
    } finally {
      (DICTIONARIES.te.result as { whatItMeans: string }).whatItMeans = saved;
    }
  });

  it("falls back to English for a language that is not registered", () => {
    // @ts-expect-error deliberately out of range, as a stale stored preference would be
    expect(translate("zz", "result.whatItMeans")).toBe(en.result.whatItMeans);
  });

  it("never renders 'undefined' for a key that does not exist", () => {
    expect(translate("hi", "nope.not.here")).toBe("nope.not.here");
    expect(translate("hi", "")).toBe("");
    expect(translateList("hi", "nope.not.here")).toEqual([]);
    expect(translate("hi", "result.meaning")).toBe("result.meaning"); // a list, not a string
  });

  it("clamps a grade-indexed lookup instead of returning nothing", () => {
    const list = translateList("te", "result.meaning");
    expect(translateIndexed("te", "result.meaning", -3)).toBe(list[0]);
    expect(translateIndexed("te", "result.meaning", 99)).toBe(list[list.length - 1]);
  });

  it("interpolates placeholders and leaves unknown ones visible", () => {
    expect(translatorFor("en").t("result.gradeOf", { grade: 2 })).toBe("Grade 2 of 4");
    expect(translatorFor("en").t("result.gradeOf")).toContain("{grade}");
  });
});

// ----------------------------------------------------- 9-10. simple/clinical
describe("explanation level", () => {
  it("simple mode leads with the plain explanation and keeps the evidence reachable", () => {
    render(<Wrap><CareResult r={makeResult()} /></Wrap>);
    expect(screen.getByText(en.result.meaning[2])).toBeTruthy();
    // Collapsed, but present: simple mode hides detail, it never deletes evidence.
    const details = document.querySelector(".cb-clinicaldetails") as HTMLDetailsElement;
    expect(details).toBeTruthy();
    expect(details.open).toBe(false);
    expect(within(details).getByText("ICDR clinical rule cross-check")).toBeTruthy();
    expect(within(details).getByText("Grade probability")).toBeTruthy();
  });

  it("clinical mode shows the ICDR label, confidence and the Grad-CAM method", () => {
    render(<Wrap><CareResult r={makeResult()} /></Wrap>);
    fireEvent.click(screen.getAllByRole("radio", { name: en.common.clinical })[0]);
    expect(screen.getByText(/ICDR · Moderate NPDR · 77% Confidence \(calibrated\)/)).toBeTruthy();
    expect(screen.getByText(en.explainability.gradCamTech)).toBeTruthy();
    // The plain explanation does not disappear when a clinician is reading.
    expect(screen.getByText(en.result.meaning[2])).toBeTruthy();
    // Clinical mode uses the original Images component, with its colour-coding caption.
    expect(screen.getByText(/Red microaneurysms, blue haemorrhages/)).toBeTruthy();
  });

  it("captions the evidence images in the reader's language in simple mode", () => {
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    chooseLanguage("తెలుగు");
    // The images are there, captioned in Telugu, and shown exactly once.
    const figures = Array.from(document.querySelectorAll(".cb-section figure"));
    expect(figures).toHaveLength(2);
    expect(screen.getByAltText(DICTIONARIES.te.explainability.gradCamTitle)).toBeTruthy();
    expect(screen.getByAltText(DICTIONARIES.te.explainability.lesionsTitle)).toBeTruthy();
    // ...and the English clinical caption is not sitting inside the Telugu section.
    expect(screen.queryByText(/Red microaneurysms, blue haemorrhages/)).toBeNull();
  });

  it("carries the level across languages without changing the underlying grade", () => {
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    fireEvent.click(screen.getAllByRole("radio", { name: en.common.clinical })[0]);
    chooseLanguage("తెలుగు");
    expect(screen.getByText(DICTIONARIES.te.result.meaning[2])).toBeTruthy();
    // Once in the CareBridge header, once in the untouched clinical Verdict below it.
    expect(screen.getAllByText(/ICDR · Moderate NPDR/).length).toBeGreaterThan(0);
  });
});

// ------------------------------------------------------------- 11-13. voice
describe("voice guidance", () => {
  it("offers Listen when a voice for the language exists", () => {
    installSpeech(["en-IN", "hi-IN"]);
    render(<Wrap><SpeakButton id="x" parts={["Hello"]} /></Wrap>);
    expect(screen.getByRole("button", { name: en.a11y.speak })).toHaveTextContent(en.common.listen);
  });

  it("speaks, shows a speaking state, and stops on a second press", () => {
    const calls = installSpeech(["en-IN"]);
    render(<Wrap><SpeakButton id="x" parts={["Your result", "Grade 2 of 4"]} /></Wrap>);
    const btn = () => screen.getByRole("button", { name: new RegExp(`${en.a11y.speak}|${en.a11y.stopSpeaking}`) });

    fireEvent.click(btn());
    expect(calls.speak).toBe(1);
    expect(calls.lastText).toBe("Your result. Grade 2 of 4.");
    expect(btn()).toHaveTextContent(en.common.stop);
    expect(btn().getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(btn());
    expect(btn()).toHaveTextContent(en.common.listen);
    expect(calls.cancel).toBeGreaterThan(0);
  });

  it("stops the previous passage before starting a new one — one queue, one voice", () => {
    const calls = installSpeech(["en-IN"]);
    render(
      <Wrap>
        <SpeakButton id="a" parts={["First"]} />
        <SpeakButton id="b" parts={["Second"]} />
      </Wrap>,
    );
    const [a, b] = screen.getAllByRole("button");
    fireEvent.click(a);
    const cancelsBefore = calls.cancel;
    fireEvent.click(b);
    expect(calls.cancel).toBeGreaterThan(cancelsBefore);
    expect(calls.speak).toBe(2);
    expect(calls.lastText).toBe("Second.");
    // Only the second button is speaking.
    expect(a.getAttribute("aria-pressed")).toBe("false");
    expect(b.getAttribute("aria-pressed")).toBe("true");
  });

  it("cancels playback when the page unmounts", () => {
    const calls = installSpeech(["en-IN"]);
    const { unmount } = render(<Wrap><SpeakButton id="x" parts={["Hello"]} /></Wrap>);
    fireEvent.click(screen.getByRole("button"));
    const before = calls.cancel;
    unmount();
    expect(calls.cancel).toBeGreaterThan(before);
  });

  it("stops reading when the language changes mid-sentence", () => {
    const calls = installSpeech(["en-IN", "te-IN"]);
    render(<Wrap><LanguageControl /><SpeakButton id="x" parts={["Hello"]} /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: en.a11y.speak }));
    const before = calls.cancel;
    chooseLanguage("తెలుగు");
    expect(calls.cancel).toBeGreaterThan(before);
  });

  it("says so, and keeps the text, when the device has no voice for this language", () => {
    installSpeech(["en-US"]); // no Telugu voice installed
    render(<Wrap><LanguageControl /><SpeakButton id="x" parts={["హలో"]} /></Wrap>);
    chooseLanguage("తెలుగు");
    expect(screen.queryByRole("button", { name: DICTIONARIES.te.a11y.speak })).toBeNull();
    expect(screen.getByRole("note")).toHaveTextContent(
      DICTIONARIES.te.errors.voiceNoLanguage.replace("{language}", "తెలుగు"));
  });

  it("degrades to text on a browser with no speech synthesis at all", () => {
    removeSpeech();
    render(<Wrap><CareResult r={makeResult()} /></Wrap>);
    expect(screen.getAllByRole("note")[0]).toHaveTextContent(en.errors.voiceUnsupported);
    // The thing the voice would have read is still on the page.
    expect(screen.getByText(en.result.meaning[2])).toBeTruthy();
  });

  it("disappears entirely when voice guidance is switched off", () => {
    installSpeech(["en-IN"]);
    render(<Wrap><LanguageControl /><SpeakButton id="x" parts={["Hello"]} /></Wrap>);
    expect(screen.queryByRole("button", { name: en.a11y.speak })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: en.a11y.openLanguageMenu }));
    fireEvent.click(screen.getByRole("switch", { name: en.a11y.voiceToggle }));
    expect(screen.queryByRole("button", { name: en.a11y.speak })).toBeNull();
  });

  it("never lends an English voice to another language", () => {
    const meta = (code: string) => LANGUAGES.find((l) => l.code === code)!;
    expect(pickVoice([{ lang: "en-US", name: "Alex" }], meta("te"))).toBeNull();
    expect(pickVoice([], meta("en"))).toBeNull();
    expect(pickVoice([{ lang: "te-IN", name: "T" }], meta("te"))?.lang).toBe("te-IN");
    // Base-subtag match, and case/underscore tolerance in the platform's tag.
    expect(pickVoice([{ lang: "te_IN", name: "T" }], meta("te"))?.lang).toBe("te_IN");
    expect(pickVoice([{ lang: "hi", name: "H" }], meta("hi"))?.lang).toBe("hi");
    // en-IN is preferred over en-US when both exist.
    expect(pickVoice([{ lang: "en-US", name: "A" }, { lang: "en-IN", name: "B" }], meta("en"))?.lang)
      .toBe("en-IN");
  });

  it("builds a readable passage and drops the gaps", () => {
    expect(speechText(["A", null, "  ", "B."])).toBe("A. B.");
    expect(speechText([])).toBe("");
    expect(speechText(["यह ठीक है।"])).toBe("यह ठीक है।");
  });
});

// ------------------------------------------------ 14. the ungradeable path
describe("ungradeable photograph", () => {
  it("translates the recapture flow and invents no grade", () => {
    render(<Wrap><LanguageControl /><CareResult r={makeUngradeable()} /></Wrap>);
    chooseLanguage("తెలుగు");

    expect(screen.getByText(DICTIONARIES.te.quality.failTitle)).toBeTruthy();
    expect(screen.getByText(DICTIONARIES.te.quality.whyBody)).toBeTruthy();
    expect(screen.getByText(DICTIONARIES.te.quality.whatToDoBody)).toBeTruthy();
    // The gate's own instruction is passed through as the API returned it — CareBridge
    // does not translate a sentence the backend generated, it quotes it.
    expect(screen.getAllByText(/Image is out of focus/).length).toBeGreaterThan(0);
  });

  it("shows no grade, no follow-up interval and no nutrition guidance", () => {
    render(<Wrap><CareResult r={makeUngradeable()} /></Wrap>);
    expect(document.querySelector(".gradebig")).toBeNull();
    expect(screen.queryByText(en.actions.title)).toBeNull();
    expect(screen.queryByText(en.nutrition.title)).toBeNull();
    expect(screen.queryByText(en.nutrition.focusTitle)).toBeNull();
    for (const meaning of en.result.meaning) {
      expect(screen.queryByText(meaning)).toBeNull();
    }
    expect(screen.getByText(en.nutrition.noGradeNote)).toBeTruthy();
  });

  it("shows no nutrition guidance when the image passed but no grade was produced", () => {
    const r = makeResult({ grading: null, grading_unavailable_reason: "model not loaded" });
    render(<Wrap><CareResult r={r} /></Wrap>);
    expect(screen.getByText(en.result.modelUnavailableTitle)).toBeTruthy();
    expect(screen.queryByText(en.nutrition.title)).toBeNull();
    expect(document.querySelector(".gradebig")).toBeNull();
  });
});

// ---------------------------------------------------- 15. nutrition module
describe("nutrition", () => {
  it("follows the global language with no selector of its own", () => {
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    expect(screen.getByText(en.nutrition.title)).toBeTruthy();
    chooseLanguage("తెలుగు");
    expect(screen.getByText(DICTIONARIES.te.nutrition.title)).toBeTruthy();
    expect(screen.getByText(DICTIONARIES.te.nutrition.intro)).toBeTruthy();
    for (const item of DICTIONARIES.te.nutrition.limitItems) {
      expect(screen.getByText(item)).toBeTruthy();
    }
    // Exactly one language control on the page: the global one in the header. The
    // nutrition module contributes no language radio of its own.
    const nutrition = document.querySelector("[aria-labelledby='cb-nutrition-h']") as HTMLElement;
    expect(within(nutrition).queryAllByRole("radio", { name: /తెలుగు/ })).toHaveLength(0);
    expect(screen.queryAllByRole("radio", { name: /తెలుగు/ })).toHaveLength(1);
  });

  it("swaps the examples for a diet preference, in the chosen language", () => {
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    chooseLanguage("हिन्दी");
    expect(screen.getByText(DICTIONARIES.hi.nutrition.focusMixed[1])).toBeTruthy();
    fireEvent.click(screen.getByRole("radio", { name: DICTIONARIES.hi.nutrition.dietMillet }));
    expect(screen.getByText(DICTIONARIES.hi.nutrition.focusMillet[0])).toBeTruthy();
    expect(screen.queryByText(DICTIONARIES.hi.nutrition.focusMixed[1])).toBeNull();
  });

  it("keeps the diet preference out of storage — it is not a UI setting", () => {
    render(<Wrap><CareResult r={makeResult()} /></Wrap>);
    fireEvent.click(screen.getByRole("radio", { name: en.nutrition.dietVegetarian }));
    const stored = window.localStorage.getItem(PREFS_KEY);
    expect(stored === null || !stored.includes("vegetarian")).toBe(true);
  });
});

// ------------------------------- 16-17. the existing product, still intact
describe("the existing application is untouched", () => {
  it("renders the original clinical Verdict exactly as before", () => {
    render(<Verdict r={makeResult()} />);
    expect(screen.getByText("Refer to ophthalmologist")).toBeTruthy();
    expect(screen.getByText("Referable diabetic retinopathy (ICDR grade 2 or above).")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("ICDR · Moderate NPDR")).toBeTruthy();
    expect(screen.getByText(/77% confidence/)).toBeTruthy();
  });

  it("renders the original Confidence panel exactly as before", () => {
    render(<Confidence r={makeResult()} />);
    expect(screen.getByText("Grade probability")).toBeTruthy();
    expect(screen.getByText("62.0%")).toBeTruthy();
    expect(screen.getByText(/P\(referable\) = 81\.0%/)).toBeTruthy();
  });

  it("presents the result without altering a single value in it", () => {
    const r = makeResult();
    const before = JSON.stringify(r);
    render(<Wrap><LanguageControl /><CareResult r={r} /></Wrap>);
    fireEvent.click(screen.getAllByRole("radio", { name: en.common.clinical })[0]);
    chooseLanguage("ਪੰਜਾਬੀ");
    expect(JSON.stringify(r)).toBe(before);
    // The grade a Punjabi reader sees is the grade the API returned.
    expect(screen.getByText(DICTIONARIES.pa.result.gradeOf.replace("{grade}", "2"))).toBeTruthy();
    expect(screen.getAllByText("2").length).toBeGreaterThan(0);
  });

  it("sends nothing about the result, the reader or the language anywhere", async () => {
    // This used to assert "no network call at all". Smart Care Finder now asks the API
    // ONE question on mount — "could you search for eye care?" — so the guarantee is
    // stated as what it always actually meant: rendering a result must not put the
    // result, the grade, the scan id or the reader's language on the network, and
    // switching language or pressing Listen must send nothing at all.
    const fetchSpy = vi.fn(async () => ({
      ok: false, status: 503, json: async () => ({}),
    } as unknown as Response));
    vi.stubGlobal("fetch", fetchSpy);
    installSpeech(["en-IN", "te-IN"]);
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    chooseLanguage("తెలుగు");
    fireEvent.click(screen.getAllByRole("button", { name: DICTIONARIES.te.a11y.speak })[0]);
    await act(async () => { await Promise.resolve(); });

    const calls = fetchSpy.mock.calls as unknown as [string, RequestInit?][];
    // The capability probe, and nothing else. It is a GET and it has no body.
    for (const [url, init] of calls) {
      expect(String(url)).toContain("/v1/care-finder/status");
      expect(init?.method ?? "GET").toBe("GET");
      expect(init?.body).toBeUndefined();
    }
    // Not one byte of the screening result, or of who is reading it, leaves the page.
    const blob = JSON.stringify(calls).toLowerCase();
    for (const secret of ["scan_test_0001", "icdr", "referable", "moderate npdr",
                          "grade", "confidence", "0.77", "pdf", "te-in", "telugu"]) {
      expect(blob).not.toContain(secret);
    }
  });
});

// ------------------------------------------------------- coverage and a11y
describe("coverage", () => {
  it("reports every registered language as complete", () => {
    for (const c of coverageReport()) {
      expect({ code: c.code, missing: c.missing }).toEqual({ code: c.code, missing: [] });
      expect(c.percent).toBe(100);
      expect(c.total).toBeGreaterThan(100);
    }
  });
});

describe("accessibility", () => {
  it("labels every CareBridge control with text, not only an icon", () => {
    installSpeech(["en-IN"]);
    render(<Wrap><LanguageControl /><CareResult r={makeResult()} /></Wrap>);
    for (const el of Array.from(document.querySelectorAll("button"))) {
      const name = (el.getAttribute("aria-label") || el.textContent || "").replace(/[^\p{L}\p{N}]/gu, "");
      expect(name.length, `unlabelled control: ${el.outerHTML.slice(0, 80)}`).toBeGreaterThan(0);
    }
  });

  it("exposes the language list and the level switch as real radio groups", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    fireEvent.click(screen.getByRole("button", { name: en.a11y.openLanguageMenu }));
    const groups = screen.getAllByRole("radiogroup");
    expect(groups.length).toBeGreaterThanOrEqual(2);
    const selected = screen.getAllByRole("radio").filter((r) => r.getAttribute("aria-checked") === "true");
    expect(selected.length).toBe(2); // one language, one explanation level
  });

  it("closes the panel on Escape", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    const trigger = screen.getByRole("button", { name: en.a11y.openLanguageMenu });
    fireEvent.click(trigger);
    expect(screen.getByRole("dialog")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  it("does not rely on colour alone to say what the grade is", () => {
    render(<Wrap><CareResult r={makeResult()} /></Wrap>);
    expect(screen.getByText("Grade 2 of 4")).toBeTruthy();
    expect(screen.getByText(en.result.labels[2])).toBeTruthy();
  });

  it("sets <html lang> to the chosen language for screen readers", () => {
    render(<Wrap><LanguageControl /></Wrap>);
    chooseLanguage("ਪੰਜਾਬੀ");
    expect(document.documentElement.lang).toBe("pa-IN");
  });
});

// ------------------------------------------------- the reusability promise
describe("future modules", () => {
  it("gives any component the whole layer from one hook", () => {
    function FutureModule() {
      const { t, lang, level, voice, tIndexed } = useCareBridge();
      return (
        <div>
          <span data-testid="lang">{lang}</span>
          <span data-testid="level">{level}</span>
          <span data-testid="voice">{String(voice)}</span>
          <span data-testid="copy">{t("future.telemedicineBody")}</span>
          <span data-testid="indexed">{tIndexed("actions.eyeBody", 4)}</span>
        </div>
      );
    }
    render(<Wrap><LanguageControl /><FutureModule /></Wrap>);
    chooseLanguage("తెలుగు");
    expect(screen.getByTestId("lang").textContent).toBe("te");
    expect(screen.getByTestId("copy").textContent).toBe(DICTIONARIES.te.future.telemedicineBody);
    expect(screen.getByTestId("indexed").textContent).toBe(DICTIONARIES.te.actions.eyeBody[4]);
    expect(screen.getByTestId("level").textContent).toBe("simple");
    expect(screen.getByTestId("voice").textContent).toBe("true");
  });
});
