"""CareBridge translation dictionaries must stay complete, real, and in their own script.

Why this lives in the Python suite, next to the ICDR rule tests, when the thing it checks
is TypeScript:

  * `tsc` already refuses a dictionary that is MISSING a key, because every language is
    declared as `Translations`. It cannot see a key that is present but blank, a list that
    quietly lost an entry, or a "translation" that is the English sentence copied across.
  * `make test` is what this project runs. A guard nobody runs is not a guard.

So this reads the dictionary files off disk and checks the things that would otherwise
reach a patient: a blank explanation, a Telugu result page written in English, a missing
placeholder, a follow-up list with four entries instead of five.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import pytest

from src.common.config import REPO_ROOT

I18N = REPO_ROOT / "web" / "lib" / "i18n"
TRANSLATIONS = I18N / "translations"
ENGLISH = "en"

# Scripts a real translation must actually be written in.
SCRIPT_RANGES = {
    "hi": (0x0900, 0x097F),  # Devanagari
    "te": (0x0C00, 0x0C7F),  # Telugu
    "pa": (0x0A00, 0x0A7F),  # Gurmukhi
}

# Leaves that are SUPPOSED to be identical in every language: the product name, and the
# clinical identifiers a doctor has to be able to recognise on a translated screen.
SHARED_WITH_ENGLISH = {
    "common.appName",
    "onboarding.eyebrow",
    "nav.carebridge",
    "result.clinicalLabels",
}

# Identifiers that must survive translation, and where each has to remain visible.
TECHNICAL_TERMS = {
    "explainability.gradCamTitle": ["Grad-CAM"],
    "explainability.gradCamTech": ["EfficientNetV2-S", "CORAL"],
    "result.clinicalDetailsHint": ["ICDR"],
}

# The patient-facing copy this product does not work without. If a future edit drops one
# of these keys, the failure should name it rather than showing a blank card.
REQUIRED_PATIENT_KEYS = [
    "result.title", "result.labels", "result.meaning", "result.whatItMeans",
    "result.gradeOf", "result.verdictRefer", "result.verdictClear",
    "result.clinicalDetails", "result.modelUnavailableTitle",
    "quality.failTitle", "quality.whyBody", "quality.whatToDoBody", "quality.noGradeNote",
    "explainability.title", "explainability.gradCamPlain",
    "actions.title", "actions.eyeTitle", "actions.eyeBody", "actions.download",
    "nutrition.title", "nutrition.intro", "nutrition.focusMixed", "nutrition.limitItems",
    "nutrition.noGradeNote",
    "why.label", "why.body",
    # WhatsApp report delivery. A patient who cannot read the button cannot use the
    # channel, so these are required copy like every other patient-facing sentence.
    "whatsapp.readyTitle", "whatsapp.readyBody", "whatsapp.channelLabel",
    "whatsapp.send", "whatsapp.sending", "whatsapp.sentShort", "whatsapp.failedShort",
    "whatsapp.retry", "whatsapp.explain", "whatsapp.successTitle", "whatsapp.successBody",
    "whatsapp.errors.notConfigured", "whatsapp.errors.generic",
    # Smart Care Finder. A patient who cannot read the button cannot reach the care the
    # screening just told them they need, so these are required copy like every other
    # patient-facing sentence. The privacy line in particular: a person being asked for
    # their location must be able to read what it is used for.
    "careFinder.title", "careFinder.continueTitle", "careFinder.continueBody",
    "careFinder.find", "careFinder.gettingLocation", "careFinder.searching",
    "careFinder.resultsTitle", "careFinder.privacyNote", "careFinder.whyLabel",
    "careFinder.yourLocation", "careFinder.viewOnMap", "careFinder.directions",
    "careFinder.openNow", "careFinder.closed", "careFinder.distanceLabel",
    "careFinder.phone", "careFinder.website", "careFinder.manualTitle",
    "careFinder.manualSubmit", "careFinder.emptyTitle", "careFinder.expand",
    "careFinder.retry", "careFinder.notEndorsement", "careFinder.attribution",
    "careFinder.badgeNote", "careFinder.voiceIntro",
    "careFinder.view.map", "careFinder.view.list",
    "careFinder.badges.nearby", "careFinder.badges.eyeFocused",
    "careFinder.badges.openNow", "careFinder.badges.highlyRated",
    "careFinder.errors.denied", "careFinder.errors.notConfigured",
    "careFinder.errors.notSetUp", "careFinder.errors.generic",
    # "1.2 km away" is a different claim depending on where it is measured from, so the
    # label that says which must exist in every language, not just English.
    "careFinder.distanceFromYou", "careFinder.distanceFromArea",
    "common.listen", "common.stop", "common.simple", "common.clinical",
    "common.disclaimer", "common.yourCareLanguage",
    "errors.voiceUnsupported", "errors.voiceNoLanguage",
    "a11y.speak", "a11y.chooseLanguage", "a11y.openLanguageMenu",
]

# Grade-indexed lists. Five ICDR grades, so five entries, in every language.
GRADE_LISTS = ["result.labels", "result.clinicalLabels", "result.meaning", "actions.eyeBody"]


# --------------------------------------------------------------------- parsing
class TsParseError(AssertionError):
    pass


def _strip_comments(src: str) -> str:
    """Remove // and /* */ comments without touching anything inside a string."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == '"':
            j = i + 1
            while j < n:
                if src[j] == "\\":
                    j += 2
                    continue
                if src[j] == '"':
                    break
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
        elif src.startswith("//", i):
            i = src.find("\n", i)
            if i == -1:
                break
        elif src.startswith("/*", i):
            end = src.find("*/", i + 2)
            i = n if end == -1 else end + 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


class _Parser:
    """Just enough of a TypeScript object literal to read a dictionary of strings."""

    def __init__(self, src: str):
        self.s = src
        self.i = 0

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in " \t\r\n":
            self.i += 1

    def expect(self, ch: str):
        self.ws()
        if self.i >= len(self.s) or self.s[self.i] != ch:
            near = self.s[max(0, self.i - 40):self.i + 40]
            raise TsParseError(f"expected {ch!r} near: ...{near}...")
        self.i += 1

    def string(self) -> str:
        self.expect('"')
        out = []
        while True:
            if self.i >= len(self.s):
                raise TsParseError("unterminated string")
            c = self.s[self.i]
            if c == "\\":
                nxt = self.s[self.i + 1]
                out.append({"n": "\n", "t": "\t", '"': '"', "\\": "\\"}.get(nxt, nxt))
                self.i += 2
                continue
            if c == '"':
                self.i += 1
                return "".join(out)
            out.append(c)
            self.i += 1

    def key(self) -> str:
        self.ws()
        if self.s[self.i] == '"':
            return self.string()
        start = self.i
        while self.i < len(self.s) and (self.s[self.i].isalnum() or self.s[self.i] in "_$"):
            self.i += 1
        if start == self.i:
            raise TsParseError(f"expected a key near: ...{self.s[start:start + 40]}...")
        return self.s[start:self.i]

    def value(self):
        self.ws()
        c = self.s[self.i]
        if c == '"':
            return self.string()
        if c == "{":
            return self.obj()
        if c == "[":
            return self.arr()
        raise TsParseError(f"unsupported value near: ...{self.s[self.i:self.i + 40]}...")

    def arr(self) -> list:
        self.expect("[")
        items = []
        while True:
            self.ws()
            if self.s[self.i] == "]":
                self.i += 1
                return items
            items.append(self.value())
            self.ws()
            if self.s[self.i] == ",":
                self.i += 1

    def obj(self) -> dict:
        self.expect("{")
        out: dict = {}
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                return out
            k = self.key()
            self.expect(":")
            out[k] = self.value()
            self.ws()
            if self.s[self.i] == ",":
                self.i += 1


def load_dictionary(code: str) -> dict:
    path = TRANSLATIONS / f"{code}.ts"
    assert path.exists(), f"no dictionary file for '{code}' at {path}"
    src = _strip_comments(path.read_text(encoding="utf-8"))
    m = re.search(rf"export const {code}\s*(?::\s*Translations\s*)?=\s*", src)
    assert m, f"{path.name} does not export a `{code}` dictionary in the expected form"
    p = _Parser(src)
    p.i = m.end()
    return p.obj()


def flatten(node, prefix="") -> dict:
    """Dotted path -> leaf, where a leaf is a string or a list of strings."""
    if isinstance(node, (str, list)):
        return {prefix: node}
    out = {}
    for k, v in node.items():
        out.update(flatten(v, f"{prefix}.{k}" if prefix else k))
    return out


def registered_languages() -> list[str]:
    src = (I18N / "languages.ts").read_text(encoding="utf-8")
    return re.findall(r'code:\s*"([a-z-]+)"', src)


@pytest.fixture(scope="module")
def dicts() -> dict[str, dict]:
    return {code: flatten(load_dictionary(code)) for code in registered_languages()}


def other_languages() -> list[str]:
    return [c for c in registered_languages() if c != ENGLISH]


# ----------------------------------------------------------------------- tests
def test_the_registry_and_the_files_on_disk_agree():
    codes = registered_languages()
    assert codes, "no languages registered in languages.ts"
    assert codes[0] == ENGLISH, "English must be first — it is the fallback"
    for code in codes:
        assert (TRANSLATIONS / f"{code}.ts").exists(), f"{code} is registered but has no dictionary"
    on_disk = {p.stem for p in TRANSLATIONS.glob("*.ts")}
    assert on_disk == set(codes), (
        f"dictionaries on disk {sorted(on_disk)} do not match the registry {sorted(codes)}")
    index = (I18N / "index.ts").read_text(encoding="utf-8")
    for code in codes:
        assert re.search(rf"\b{code}\b", index), f"{code} is never imported in i18n/index.ts"


@pytest.mark.parametrize("code", other_languages())
def test_language_has_every_english_key(code, dicts):
    english, other = dicts[ENGLISH], dicts[code]
    missing = sorted(set(english) - set(other))
    assert not missing, f"{code} is missing {len(missing)} key(s): {missing}"


@pytest.mark.parametrize("code", other_languages())
def test_language_has_no_keys_english_does_not(code, dicts):
    extra = sorted(set(dicts[code]) - set(dicts[ENGLISH]))
    assert not extra, (
        f"{code} defines {extra} which English does not. English is the contract: add the "
        f"key to en.ts first.")


@pytest.mark.parametrize("code", registered_languages())
def test_no_leaf_is_blank(code, dicts):
    blank = sorted(k for k, v in dicts[code].items()
                   if (isinstance(v, str) and not v.strip())
                   or (isinstance(v, list) and (not v or any(not s.strip() for s in v))))
    assert not blank, f"{code} has blank entries at {blank} — they would render as nothing"


@pytest.mark.parametrize("code", other_languages())
def test_leaf_shapes_match_english(code, dicts):
    english, other = dicts[ENGLISH], dicts[code]
    for key, value in english.items():
        assert type(other[key]) is type(value), (
            f"{code}.{key} is a {type(other[key]).__name__}, English has a "
            f"{type(value).__name__}")
        if isinstance(value, list):
            assert len(other[key]) == len(value), (
                f"{code}.{key} has {len(other[key])} entries, English has {len(value)}")


@pytest.mark.parametrize("code", registered_languages())
def test_grade_indexed_lists_cover_all_five_icdr_grades(code, dicts):
    for key in GRADE_LISTS:
        value = dicts[code].get(key)
        assert isinstance(value, list) and len(value) == 5, (
            f"{code}.{key} must have one entry per ICDR grade 0-4, found "
            f"{len(value) if isinstance(value, list) else value!r}")


@pytest.mark.parametrize("code", registered_languages())
def test_required_patient_keys_are_present(code, dicts):
    missing = [k for k in REQUIRED_PATIENT_KEYS if k not in dicts[code]]
    assert not missing, (
        f"{code} is missing patient-facing copy the result page needs: {missing}")


@pytest.mark.parametrize("code", other_languages())
def test_placeholders_survive_translation(code, dicts):
    """{grade} and {language} must still be there, or the sentence renders a hole."""
    for key, english in dicts[ENGLISH].items():
        if not isinstance(english, str):
            continue
        wanted = set(re.findall(r"\{(\w+)\}", english))
        got = set(re.findall(r"\{(\w+)\}", dicts[code][key]))
        assert wanted == got, f"{code}.{key} has placeholders {got or '{}'}, expected {wanted}"


@pytest.mark.parametrize("code", ["hi", "te", "pa"])
def test_translation_is_actually_in_its_own_script(code, dicts):
    """The failure this catches is a dictionary copy-pasted from en.ts and left there."""
    lo, hi_ = SCRIPT_RANGES[code]
    english, other = dicts[ENGLISH], dicts[code]

    def in_script(text: str) -> bool:
        return any(lo <= ord(ch) <= hi_ for ch in text)

    prose = [k for k, v in other.items()
             if isinstance(v, str) and len(v) > 25 and k not in SHARED_WITH_ENGLISH]
    not_translated = [k for k in prose if not in_script(other[k])]
    assert not not_translated, (
        f"{code} has sentences with no {code} characters at all: {not_translated}")

    identical = sorted(k for k in english
                       if other[k] == english[k] and k not in SHARED_WITH_ENGLISH)
    assert not identical, (
        f"{code} repeats the English text verbatim at {identical}. Either translate it, "
        f"or add the key to SHARED_WITH_ENGLISH with a reason.")


@pytest.mark.parametrize("code", registered_languages())
def test_technical_identifiers_are_not_translated_away(code, dicts):
    """A clinician reading the Telugu clinical view still has to find 'Grad-CAM'."""
    for key, terms in TECHNICAL_TERMS.items():
        text = dicts[code][key]
        for term in terms:
            assert term in text, f"{code}.{key} no longer names {term}"
    for label in dicts[code]["result.clinicalLabels"]:
        assert label.isascii(), (
            f"{code} translated the ICDR label {label!r}; those stay as the scale defines them")


@pytest.mark.parametrize("code", other_languages())
def test_the_disclaimer_reaches_every_language(code, dicts):
    """Project rule: the disclaimer is on every UI surface. A surface someone cannot read
    does not carry it."""
    assert dicts[code]["common.disclaimer"].strip()
    assert dicts[code]["common.disclaimer"] != dicts[ENGLISH]["common.disclaimer"]


def test_coverage_summary_is_one_hundred_percent(dicts):
    """The report the brief asks for, as an assertion rather than a screenshot."""
    english = dicts[ENGLISH]
    summary = {}
    for code, leaves in dicts.items():
        done = sum(1 for k in english
                   if k in leaves and (leaves[k] if isinstance(leaves[k], str) else "".join(leaves[k])).strip())
        summary[code] = round(100 * done / len(english), 1)
    assert summary == {code: 100.0 for code in dicts}, json.dumps(summary, indent=2)


def test_no_patient_string_is_stored_alongside_a_medical_value():
    """CareBridge may persist interface preferences. Nothing else.

    A grade, a scan id or a patient reference in localStorage would outlive the session on
    a shared health-centre device. The allowed keys are named here so that widening them
    is a deliberate edit with a test to change.
    """
    src = (REPO_ROOT / "web" / "lib" / "carebridge.ts").read_text(encoding="utf-8")
    stored = re.search(r"JSON\.stringify\(\{([^}]*)\}\)", src)
    assert stored, "carebridge.ts no longer serialises its preferences in one place"
    fields = set(re.findall(r"(\w+)\s*:", stored.group(1)))
    assert fields == {"lang", "voice", "level", "chosen"}, (
        f"CareBridge now persists {sorted(fields)}. Only interface preferences may be stored.")
    for forbidden in ["icdr_grade", "scan_id", "patient_ref", "confidence", "referable"]:
        assert forbidden not in src, f"carebridge.ts references {forbidden}"


def test_the_analyze_contract_was_not_changed_for_a_ui_feature():
    """CareBridge presents the existing result. It does not ask the API for anything new."""
    src = (REPO_ROOT / "web" / "lib" / "api.ts").read_text(encoding="utf-8")
    body = src[src.index("export type AnalyzeResult"):]
    body = body[body.index("{") + 1:]

    # Top-level field names only: the inline object in `report` has fields of its own.
    depth, top = 0, []
    for token in re.finditer(r"[{}]|(\w+)\??\s*:", body):
        if token.group(0) == "{":
            depth += 1
        elif token.group(0) == "}":
            if depth == 0:
                break
            depth -= 1
        elif depth == 0 and token.group(1):
            top.append(token.group(1))

    assert set(top) == {
        "scan_id", "created_at", "model_id", "disclaimer", "synthetic_demo_model",
        "quality", "grading", "grading_unavailable_reason", "lesions", "rule_check",
        "explain", "report", "timing_ms",
    }, f"the AnalyzeResult contract changed: {sorted(top)}"


def test_every_dictionary_is_valid_unicode_without_replacement_characters():
    for code in registered_languages():
        text = (TRANSLATIONS / f"{code}.ts").read_text(encoding="utf-8")
        assert "�" not in text, f"{code}.ts contains a replacement character — mojibake"
        assert unicodedata.is_normalized("NFC", text), f"{code}.ts is not NFC-normalised"
