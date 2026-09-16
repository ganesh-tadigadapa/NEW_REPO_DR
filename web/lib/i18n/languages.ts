/**
 * The languages CareBridge ships with.
 *
 * Adding a language is: add the code to `LanguageCode`, add a dictionary under
 * `translations/`, register both here and in `index.ts`. No React component changes.
 */
import type { LanguageCode, LanguageMeta } from "./types";

export const DEFAULT_LANGUAGE: LanguageCode = "en";

export const LANGUAGES: LanguageMeta[] = [
  {
    code: "en",
    nativeName: "English",
    englishName: "English",
    locale: "en-IN",
    speechLocales: ["en-IN", "en-GB", "en-US", "en"],
  },
  {
    code: "hi",
    nativeName: "हिन्दी",
    englishName: "Hindi",
    locale: "hi-IN",
    speechLocales: ["hi-IN", "hi"],
  },
  {
    code: "te",
    nativeName: "తెలుగు",
    englishName: "Telugu",
    locale: "te-IN",
    speechLocales: ["te-IN", "te"],
  },
  {
    code: "pa",
    nativeName: "ਪੰਜਾਬੀ",
    englishName: "Punjabi",
    locale: "pa-IN",
    speechLocales: ["pa-IN", "pa-Guru-IN", "pa"],
  },
];

export const LANGUAGE_CODES: LanguageCode[] = LANGUAGES.map((l) => l.code);

export function isLanguageCode(v: unknown): v is LanguageCode {
  return typeof v === "string" && (LANGUAGE_CODES as string[]).includes(v);
}

export function languageMeta(code: LanguageCode): LanguageMeta {
  return LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
}
