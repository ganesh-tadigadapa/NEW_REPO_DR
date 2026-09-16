/**
 * CareBridge — the translation layer.
 *
 * One entry point for every feature in the app, present and future. A module that needs
 * words adds keys to `translations/`; it does not build a language mechanism of its own.
 *
 * Resolution order for any key:
 *   1. the selected language
 *   2. English
 *   3. the key itself
 *
 * Step 3 exists so that a key added to en.ts but not yet wired up renders something
 * inert rather than the word "undefined" on a patient's result page.
 */
import { en } from "./translations/en";
import { hi } from "./translations/hi";
import { te } from "./translations/te";
import { pa } from "./translations/pa";
import { DEFAULT_LANGUAGE, languageMeta } from "./languages";
import type {
  LanguageCode, ListKey, StringKey, Translations, Vars,
} from "./types";

export const DICTIONARIES: Record<LanguageCode, Translations> = { en, hi, te, pa };

export { DEFAULT_LANGUAGE, LANGUAGES, LANGUAGE_CODES, isLanguageCode, languageMeta }
  from "./languages";
export type {
  ExplanationLevel, LanguageCode, LanguageMeta, ListKey, StringKey, Translations, Vars,
} from "./types";

/** Walk a dotted path. Returns undefined rather than throwing on a bad path. */
function lookup(dict: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, part) => {
    if (node && typeof node === "object" && part in (node as object)) {
      return (node as Record<string, unknown>)[part];
    }
    return undefined;
  }, dict);
}

/** "Grade {grade} of 4" + {grade: 2} -> "Grade 2 of 4". Unknown vars are left alone. */
export function interpolate(template: string, vars?: Vars): string {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in vars ? String(vars[name]) : whole);
}

/** Resolve a single string. Falls back to English, then to the key. */
export function translate(lang: LanguageCode, key: string, vars?: Vars): string {
  const primary = lookup(DICTIONARIES[lang] ?? DICTIONARIES[DEFAULT_LANGUAGE], key);
  if (typeof primary === "string" && primary.trim() !== "") {
    return interpolate(primary, vars);
  }
  const fallback = lookup(DICTIONARIES[DEFAULT_LANGUAGE], key);
  if (typeof fallback === "string" && fallback.trim() !== "") {
    return interpolate(fallback, vars);
  }
  // Nothing anywhere. Render the key: visible to a developer, harmless to a patient,
  // and never the string "undefined".
  return key;
}

/** Resolve a list. Same fallback chain; an empty array if the key is not a list. */
export function translateList(lang: LanguageCode, key: string): string[] {
  const primary = lookup(DICTIONARIES[lang] ?? DICTIONARIES[DEFAULT_LANGUAGE], key);
  if (Array.isArray(primary) && primary.length > 0) return primary as string[];
  const fallback = lookup(DICTIONARIES[DEFAULT_LANGUAGE], key);
  if (Array.isArray(fallback)) return fallback as string[];
  return [];
}

/**
 * Pick item `index` out of a translated list, clamped.
 *
 * Used for grade-indexed copy. Clamping is deliberate: an out-of-range grade must not
 * produce a blank explanation on a result page.
 */
export function translateIndexed(lang: LanguageCode, key: ListKey, index: number): string {
  const list = translateList(lang, key);
  if (list.length === 0) return key;
  const i = Math.min(Math.max(Math.trunc(index), 0), list.length - 1);
  return list[i];
}

/** The bound translator a component receives. */
export type Translator = {
  lang: LanguageCode;
  t: (key: StringKey, vars?: Vars) => string;
  tList: (key: ListKey) => string[];
  tIndexed: (key: ListKey, index: number) => string;
  /** BCP-47 tag for <html lang>, Intl and speech synthesis. */
  locale: string;
};

export function translatorFor(lang: LanguageCode): Translator {
  return {
    lang,
    t: (key, vars) => translate(lang, key, vars),
    tList: (key) => translateList(lang, key),
    tIndexed: (key, index) => translateIndexed(lang, key, index),
    locale: languageMeta(lang).locale,
  };
}
