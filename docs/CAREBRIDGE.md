# CareBridge — the patient accessibility layer

A screening service whose result only exists in English is not usable by most of the
people it was built for. CareBridge is the layer that fixes that, and it is deliberately
a *layer*: one language choice, applied to the whole patient journey, reusable by every
module added later.

```
          ONE LANGUAGE SELECTION
                    ↓
         ENTIRE PATIENT EXPERIENCE
                    ↓
       LANGUAGE + VOICE + SIMPLICITY
```

It changes **how existing information is presented**. It does not produce information.
No grade, probability, threshold, referral decision, Grad-CAM or lesion count is computed,
altered or re-requested anywhere in this feature. The model is not called a second time.

## What it provides

| | |
|---|---|
| 🌐 Language | English, हिन्दी, తెలుగు, ਪੰਜਾਬੀ — chosen once, remembered |
| 🔊 Voice | Browser speech synthesis, in the chosen language, or an honest refusal |
| 🧑‍🌾 Simple | Plain-language explanation of the result, written for the patient |
| 👨‍⚕️ Clinical | ICDR grade, calibrated confidence, evidence, Grad-CAM method |
| 🧭 Guidance | Follow-up interval, lifestyle support, the report to carry to a doctor |

## Where it lives

```
web/lib/i18n/
  types.ts                 StringKey / ListKey — dotted paths, checked by the compiler
  languages.ts             the registry: code, native name, locale, speech locales
  index.ts                 translate() / translateList() / translatorFor()
  coverage.ts              coverage report used by the dev panel
  translations/en.ts       the CONTRACT — `Translations` is derived from this object
  translations/{hi,te,pa}.ts

web/lib/carebridge.ts      preference parsing/persistence and voice matching (pure)

web/components/carebridge/
  CareBridgeProvider.tsx   language + voice + level + the single speech queue
  LanguageControl.tsx      the header control and its popover
  LanguagePicker.tsx       the first-use welcome card, and the reusable choice list
  SpeakButton.tsx          🔊 Listen / ⏹ Stop, with a graceful no-voice state
  WhyThis.tsx              ⓘ Why am I seeing this?
  CareResult.tsx           the patient presentation of an existing AnalyzeResult
  Nutrition.tsx            food and lifestyle support, grade-gated
  CareBridgeBand.tsx       the landing-page band
  CoveragePanel.tsx        development-only translation coverage readout
  Disclaimer.tsx           the project-wide disclaimer, translated

web/app/carebridge/page.tsx   the CareBridge page (public — no sign-in required)
```

## Adding a language

1. Add the code to `LanguageCode` in `lib/i18n/types.ts`.
2. Add an entry to `LANGUAGES` in `lib/i18n/languages.ts`, including `speechLocales`.
3. Copy `translations/en.ts` to `translations/xx.ts`, declare it `const xx: Translations`,
   and translate it.
4. Register it in `DICTIONARIES` in `lib/i18n/index.ts`.

No React component changes. `tsc` will name every key you have not translated yet.

## Adding a feature

Add your keys to `en.ts` and the other dictionaries, then:

```tsx
const { t, tList, tIndexed, level, lang } = useCareBridge();
return <h3>{t("appointments.title")}</h3>;
```

The feature is now multilingual, has voice available via `<SpeakButton />`, and responds
to the simple/clinical switch. It does not need a language selector, a settings screen or
a storage key of its own.

## The rules this feature keeps

**Every patient-facing string comes from the translation layer.** A literal English
sentence inside a component is a sentence only English speakers will ever read.

**English is the fallback, and a missing key is never `undefined`.** Resolution is
selected language → English → the key itself. A key rendered raw is visible to a
developer and inert to a patient.

**Simple mode hides detail; it never deletes evidence.** The clinical stack is collapsed
behind one control, not removed. Clinical mode keeps the plain explanation.

**An ungradeable image gets no grade.** No severity, no follow-up interval and no
nutrition guidance are shown for a photograph the quality gate refused — the existing
recapture instruction is translated and shown instead.

**Voice is local and honest.** `speechSynthesis` only; nothing is sent anywhere. A device
with no Telugu voice keeps the Telugu text and says why it cannot speak it, rather than
reading Telugu aloud in an English voice.

**Storage holds interface preferences and nothing else.** `carebridge_prefs` contains
exactly `lang`, `voice`, `level`, `chosen`. No grade, scan id or patient reference. The
session token is untouched: changing language does not sign anyone out.

**The translations are written, not generated.** This is a curated multilingual interface.
Nothing in the product claims that a machine translates anyone's medical result.

## Keeping it honest

Three independent guards, because a language nobody on the team reads rots silently.

| Guard | Catches |
|---|---|
| `make web-typecheck` | a missing key, or a `t()` call with a key that does not exist |
| `make test` → `tests/test_carebridge_i18n.py` | a blank leaf, a list that lost an entry, a dropped `{placeholder}`, an ICDR label that got translated, and a "translation" that is the English text copied across |
| `make web-test` → `web/tests/carebridge.test.tsx` | fallback, persistence, simple/clinical, the voice states, the ungradeable path, and that the presented `AnalyzeResult` is never mutated |

`/carebridge` also shows a live coverage table in development builds.

## Demo path

`/carebridge` → pick తెలుగు → `/screen` → upload the grade-2 sample → the result,
explanation, Grad-CAM caption, follow-up and nutrition are all Telugu → 🔊 Listen →
switch to Clinical → switch to हिन्दी, same grade → back to English → refresh, the choice
persists → upload the out-of-focus sample → the translated recapture flow, with no grade
and no nutrition guidance.
