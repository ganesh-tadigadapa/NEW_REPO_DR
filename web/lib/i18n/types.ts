/**
 * CareBridge — shared types for the translation layer.
 *
 * The English dictionary in `translations/en.ts` is the SHAPE. Every other language is
 * declared as `Translations`, so a missing key is a TypeScript error at build time, not
 * a blank space on a patient's screen. `tests/test_carebridge_i18n.py` enforces the same
 * rule outside the compiler, for the languages a future contributor might add by hand.
 */
import type { Translations } from "./translations/en";

export type { Translations };

/** A dictionary leaf is either one sentence or an ordered list of them. */
export type Leaf = string | string[];

/**
 * Dotted paths that resolve to a single string, e.g. "result.whatItMeans".
 * Typing t() against this means a typo fails `tsc`, which is the cheapest place to
 * catch it.
 */
export type StringKey<T = Translations> = {
  [K in keyof T & string]: T[K] extends string
    ? K
    : T[K] extends string[]
      ? never
      : `${K}.${StringKey<T[K]>}`;
}[keyof T & string];

/** Dotted paths that resolve to a list, e.g. "result.meaning". */
export type ListKey<T = Translations> = {
  [K in keyof T & string]: T[K] extends string[]
    ? K
    : T[K] extends string
      ? never
      : `${K}.${ListKey<T[K]>}`;
}[keyof T & string];

/** Values substituted into {placeholders}. Numbers are formatted by the caller. */
export type Vars = Record<string, string | number>;

export type LanguageCode = "en" | "hi" | "te" | "pa";

export type LanguageMeta = {
  code: LanguageCode;
  /** The name of the language, written in that language. Never translated. */
  nativeName: string;
  /** The name in English, for screen readers and for the English UI. */
  englishName: string;
  /** BCP-47 tag for <html lang> and for Intl. */
  locale: string;
  /**
   * Speech-synthesis voices to look for, best first. A device that has none of these
   * gets text only — CareBridge never reads Telugu out with an English voice.
   */
  speechLocales: string[];
};

/** How much detail the reader wants. A presentation choice, never a medical one. */
export type ExplanationLevel = "simple" | "clinical";
