/**
 * Translation coverage — the check that stops a language silently rotting.
 *
 * The compiler already refuses a dictionary that is missing a key, because every
 * language is declared as `Translations`. This module exists for the two cases the
 * compiler cannot see: a key present but left EMPTY, and a report a human can read.
 * `tests/test_carebridge_i18n.py` asserts the same thing against the files on disk, so
 * the rule holds even for a contributor who never runs `tsc`.
 */
import { DICTIONARIES } from "./index";
import { LANGUAGES, DEFAULT_LANGUAGE } from "./languages";
import type { LanguageCode } from "./types";

export type LanguageCoverage = {
  code: LanguageCode;
  nativeName: string;
  englishName: string;
  total: number;
  translated: number;
  /** 0-100, rounded to one decimal. */
  percent: number;
  missing: string[];
};

/** Every dotted leaf path in a dictionary, in declaration order. */
export function flattenKeys(node: unknown, prefix = ""): string[] {
  if (typeof node === "string" || Array.isArray(node)) return prefix ? [prefix] : [];
  if (!node || typeof node !== "object") return [];
  return Object.entries(node as Record<string, unknown>).flatMap(([k, v]) =>
    flattenKeys(v, prefix ? `${prefix}.${k}` : k));
}

function leafAt(dict: unknown, path: string): unknown {
  return path.split(".").reduce<unknown>((node, part) => {
    if (node && typeof node === "object" && part in (node as object)) {
      return (node as Record<string, unknown>)[part];
    }
    return undefined;
  }, dict);
}

/** A leaf counts as translated when it is a non-blank string, or a non-empty list of them. */
export function isTranslated(value: unknown): boolean {
  if (typeof value === "string") return value.trim() !== "";
  if (Array.isArray(value)) {
    return value.length > 0 && value.every((v) => typeof v === "string" && v.trim() !== "");
  }
  return false;
}

export function coverageFor(code: LanguageCode): LanguageCoverage {
  const meta = LANGUAGES.find((l) => l.code === code) ?? LANGUAGES[0];
  const keys = flattenKeys(DICTIONARIES[DEFAULT_LANGUAGE]);
  const dict = DICTIONARIES[code];
  const missing = keys.filter((k) => !isTranslated(leafAt(dict, k)));
  const translated = keys.length - missing.length;
  return {
    code,
    nativeName: meta.nativeName,
    englishName: meta.englishName,
    total: keys.length,
    translated,
    percent: keys.length === 0 ? 100 : Math.round((translated / keys.length) * 1000) / 10,
    missing,
  };
}

export function coverageReport(): LanguageCoverage[] {
  return LANGUAGES.map((l) => coverageFor(l.code));
}

export function allLanguagesComplete(): boolean {
  return coverageReport().every((c) => c.missing.length === 0);
}
