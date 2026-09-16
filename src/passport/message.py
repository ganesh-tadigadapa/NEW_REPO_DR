"""The words that travel with the comparison PDF, in the patient's CareBridge language.

READ THIS BEFORE EDITING. This module performs no analysis and no comparison. It is
handed a comparison object that `comparison.py` already built by subtracting two grades
the model already decided, and it chooses a pre-written sentence for the direction of
that difference. There is no threshold here, no `if grade >= 2`, and no sentence that
says anything stronger than the English one in `comparison.statement()`.

The language list, the normaliser and the default are imported from
`src/delivery/message.py` — CareBridge has one language mechanism and this is not a
second one. The disclaimer is the last thing the patient reads, in their own language,
on every send.
"""
from __future__ import annotations

from src.common.config import ICDR_LABELS
from src.delivery.message import DEFAULT_LANGUAGE, LANGUAGES, normalise_language
from src.passport.store import parse_iso

# Magnitude words, indexed by the absolute ICDR category difference. The scale is 0-4,
# so four is the largest difference that can exist.
_MAGNITUDE = {
    "en": ["", "one", "two", "three", "four"],
    "hi": ["", "एक", "दो", "तीन", "चार"],
    "te": ["", "ఒక", "రెండు", "మూడు", "నాలుగు"],
    "pa": ["", "ਇੱਕ", "ਦੋ", "ਤਿੰਨ", "ਚਾਰ"],
}

_COPY: dict[str, dict[str, str]] = {
    "en": {
        "title": "CareBridge Eye Health Passport",
        "intro": "Your new screening has been compared with your previous one.",
        "previousHeading": "Previous screening",
        "currentHeading": "This screening",
        "grade": "Grade {grade} of 4",
        "changeHeading": "What changed",
        "unitOne": "ICDR category",
        "unitMany": "ICDR categories",
        "changeSame": "The current screening result is in the same ICDR category as the previous screening.",
        "changeHigher": "The current screening result is {n} {unit} higher than the previous screening.",
        "changeLower": "The current screening result is {n} {unit} lower than the previous screening.",
        "notProgression": ("This compares two screening results. It is not a diagnosis, "
                           "and it is not by itself evidence that the disease has changed."),
        "followUpHeading": "Suggested follow-up",
        "clinicianHeading": "Clinician review",
        "clinicianGrade": "Clinician's grade: {grade}",
        "attached": "Your comparison report is attached.",
        "disclaimer": ("This is an AI-assisted screening comparison, not a medical "
                       "diagnosis. Please show this report to an eye-care professional."),
    },
    "hi": {
        "title": "केयरब्रिज आई हेल्थ पासपोर्ट",
        "intro": "आपकी नई स्क्रीनिंग की तुलना आपकी पिछली स्क्रीनिंग से की गई है।",
        "previousHeading": "पिछली स्क्रीनिंग",
        "currentHeading": "यह स्क्रीनिंग",
        "grade": "4 में से ग्रेड {grade}",
        "changeHeading": "क्या बदला",
        "unitOne": "आईसीडीआर श्रेणी",
        "unitMany": "आईसीडीआर श्रेणियाँ",
        "changeSame": "वर्तमान स्क्रीनिंग परिणाम पिछली स्क्रीनिंग की तरह उसी आईसीडीआर श्रेणी में है।",
        "changeHigher": "वर्तमान स्क्रीनिंग परिणाम पिछली स्क्रीनिंग से {n} {unit} ऊपर है।",
        "changeLower": "वर्तमान स्क्रीनिंग परिणाम पिछली स्क्रीनिंग से {n} {unit} नीचे है।",
        "notProgression": ("यह दो स्क्रीनिंग परिणामों की तुलना है। यह कोई निदान नहीं है, और "
                           "अकेले यह इस बात का प्रमाण नहीं है कि बीमारी बदल गई है।"),
        "followUpHeading": "सुझाई गई अगली जाँच",
        "clinicianHeading": "डॉक्टर की समीक्षा",
        "clinicianGrade": "डॉक्टर का ग्रेड: {grade}",
        "attached": "आपकी तुलना रिपोर्ट संलग्न है।",
        "disclaimer": ("यह एआई-सहायित स्क्रीनिंग तुलना है, कोई चिकित्सीय निदान नहीं। कृपया यह "
                       "रिपोर्ट किसी नेत्र विशेषज्ञ को दिखाएँ।"),
    },
    "te": {
        "title": "కేర్‌బ్రిడ్జ్ ఐ హెల్త్ పాస్‌పోర్ట్",
        "intro": "మీ కొత్త స్క్రీనింగ్‌ను మీ మునుపటి స్క్రీనింగ్‌తో పోల్చాము.",
        "previousHeading": "మునుపటి స్క్రీనింగ్",
        "currentHeading": "ఈ స్క్రీనింగ్",
        "grade": "4లో గ్రేడ్ {grade}",
        "changeHeading": "ఏమి మారింది",
        "unitOne": "ఐసీడీఆర్ వర్గం",
        "unitMany": "ఐసీడీఆర్ వర్గాలు",
        "changeSame": "ప్రస్తుత స్క్రీనింగ్ ఫలితం మునుపటి స్క్రీనింగ్ ఉన్న అదే ఐసీడీఆర్ వర్గంలోనే ఉంది.",
        "changeHigher": "ప్రస్తుత స్క్రీనింగ్ ఫలితం మునుపటి స్క్రీనింగ్ కంటే {n} {unit} పైన ఉంది.",
        "changeLower": "ప్రస్తుత స్క్రీనింగ్ ఫలితం మునుపటి స్క్రీనింగ్ కంటే {n} {unit} కింద ఉంది.",
        "notProgression": ("ఇది రెండు స్క్రీనింగ్ ఫలితాల పోలిక. ఇది వ్యాధి నిర్ధారణ కాదు, మరియు "
                           "వ్యాధి మారిందనడానికి ఇది ఒక్కటే ఆధారం కాదు."),
        "followUpHeading": "సూచించిన తదుపరి పరీక్ష",
        "clinicianHeading": "వైద్యుని సమీక్ష",
        "clinicianGrade": "వైద్యుని గ్రేడ్: {grade}",
        "attached": "మీ పోలిక రిపోర్ట్ జతచేయబడింది.",
        "disclaimer": ("ఇది ఏఐ-సహాయక స్క్రీనింగ్ పోలిక, వైద్య నిర్ధారణ కాదు. దయచేసి ఈ రిపోర్ట్‌ను "
                       "కంటి వైద్య నిపుణుడికి చూపించండి."),
    },
    "pa": {
        "title": "ਕੇਅਰਬ੍ਰਿਜ ਆਈ ਹੈਲਥ ਪਾਸਪੋਰਟ",
        "intro": "ਤੁਹਾਡੀ ਨਵੀਂ ਸਕ੍ਰੀਨਿੰਗ ਦੀ ਤੁਲਨਾ ਤੁਹਾਡੀ ਪਿਛਲੀ ਸਕ੍ਰੀਨਿੰਗ ਨਾਲ ਕੀਤੀ ਗਈ ਹੈ।",
        "previousHeading": "ਪਿਛਲੀ ਸਕ੍ਰੀਨਿੰਗ",
        "currentHeading": "ਇਹ ਸਕ੍ਰੀਨਿੰਗ",
        "grade": "4 ਵਿੱਚੋਂ ਗ੍ਰੇਡ {grade}",
        "changeHeading": "ਕੀ ਬਦਲਿਆ",
        "unitOne": "ਆਈਸੀਡੀਆਰ ਸ਼੍ਰੇਣੀ",
        "unitMany": "ਆਈਸੀਡੀਆਰ ਸ਼੍ਰੇਣੀਆਂ",
        "changeSame": "ਮੌਜੂਦਾ ਸਕ੍ਰੀਨਿੰਗ ਨਤੀਜਾ ਪਿਛਲੀ ਸਕ੍ਰੀਨਿੰਗ ਵਾਲੀ ਹੀ ਆਈਸੀਡੀਆਰ ਸ਼੍ਰੇਣੀ ਵਿੱਚ ਹੈ।",
        "changeHigher": "ਮੌਜੂਦਾ ਸਕ੍ਰੀਨਿੰਗ ਨਤੀਜਾ ਪਿਛਲੀ ਸਕ੍ਰੀਨਿੰਗ ਨਾਲੋਂ {n} {unit} ਉੱਤੇ ਹੈ।",
        "changeLower": "ਮੌਜੂਦਾ ਸਕ੍ਰੀਨਿੰਗ ਨਤੀਜਾ ਪਿਛਲੀ ਸਕ੍ਰੀਨਿੰਗ ਨਾਲੋਂ {n} {unit} ਹੇਠਾਂ ਹੈ।",
        "notProgression": ("ਇਹ ਦੋ ਸਕ੍ਰੀਨਿੰਗ ਨਤੀਜਿਆਂ ਦੀ ਤੁਲਨਾ ਹੈ। ਇਹ ਕੋਈ ਨਿਦਾਨ ਨਹੀਂ ਹੈ, ਅਤੇ ਇਕੱਲਾ "
                           "ਇਹ ਇਸ ਗੱਲ ਦਾ ਸਬੂਤ ਨਹੀਂ ਕਿ ਬਿਮਾਰੀ ਬਦਲ ਗਈ ਹੈ।"),
        "followUpHeading": "ਸੁਝਾਈ ਗਈ ਅਗਲੀ ਜਾਂਚ",
        "clinicianHeading": "ਡਾਕਟਰ ਦੀ ਸਮੀਖਿਆ",
        "clinicianGrade": "ਡਾਕਟਰ ਦਾ ਗ੍ਰੇਡ: {grade}",
        "attached": "ਤੁਹਾਡੀ ਤੁਲਨਾ ਰਿਪੋਰਟ ਨੱਥੀ ਹੈ।",
        "disclaimer": ("ਇਹ ਏਆਈ-ਸਹਾਇਤ ਸਕ੍ਰੀਨਿੰਗ ਤੁਲਨਾ ਹੈ, ਕੋਈ ਮੈਡੀਕਲ ਨਿਦਾਨ ਨਹੀਂ। ਕਿਰਪਾ ਕਰਕੇ ਇਹ "
                       "ਰਿਪੋਰਟ ਅੱਖਾਂ ਦੇ ਮਾਹਿਰ ਨੂੰ ਦਿਖਾਓ।"),
    },
}

# The follow-up window, written out per priority. The NUMBERS come from the plan; only
# the sentence around them is chosen here, and the priority was decided by
# `followup.plan()` from the configured guideline table.
_FOLLOW_UP: dict[str, dict[str, str]] = {
    "en": {
        "routine": "Routine screening again {window}.",
        "soon": "A follow-up screening is suggested {window}.",
        "prompt": "Assessment by an eye specialist is suggested {window}.",
        "urgent": "Please see an eye specialist as soon as you can.",
    },
    "hi": {
        "routine": "नियमित जाँच दोबारा {window} कराएँ।",
        "soon": "अगली जाँच {window} कराने का सुझाव है।",
        "prompt": "नेत्र विशेषज्ञ से जाँच {window} कराने का सुझाव है।",
        "urgent": "कृपया जितनी जल्दी हो सके नेत्र विशेषज्ञ से मिलें।",
    },
    "te": {
        "routine": "సాధారణ పరీక్ష మళ్ళీ {window} చేయించుకోండి.",
        "soon": "తదుపరి స్క్రీనింగ్ {window} చేయించుకోవాలని సూచన.",
        "prompt": "కంటి నిపుణుడి పరీక్ష {window} చేయించుకోవాలని సూచన.",
        "urgent": "దయచేసి వీలైనంత త్వరగా కంటి నిపుణుడిని కలవండి.",
    },
    "pa": {
        "routine": "ਨਿਯਮਿਤ ਜਾਂਚ ਦੁਬਾਰਾ {window} ਕਰਾਓ।",
        "soon": "ਅਗਲੀ ਜਾਂਚ {window} ਕਰਾਉਣ ਦਾ ਸੁਝਾਅ ਹੈ।",
        "prompt": "ਅੱਖਾਂ ਦੇ ਮਾਹਿਰ ਤੋਂ ਜਾਂਚ {window} ਕਰਾਉਣ ਦਾ ਸੁਝਾਅ ਹੈ।",
        "urgent": "ਕਿਰਪਾ ਕਰਕੇ ਜਿੰਨੀ ਛੇਤੀ ਹੋ ਸਕੇ ਅੱਖਾਂ ਦੇ ਮਾਹਿਰ ਨੂੰ ਮਿਲੋ।",
    },
}

# The window phrase itself. The months come from the plan; these are the frames.
_WINDOW: dict[str, dict[str, str]] = {
    "en": {"about": "in about {n} months", "aboutOne": "in about 1 month",
           "range": "in {lo}–{hi} months", "within": "within {n} months",
           "withinOne": "within 1 month", "asap": "as soon as possible"},
    "hi": {"about": "लगभग {n} महीने में", "aboutOne": "लगभग 1 महीने में",
           "range": "{lo}–{hi} महीने में", "within": "{n} महीने के भीतर",
           "withinOne": "1 महीने के भीतर", "asap": "जितनी जल्दी हो सके"},
    "te": {"about": "సుమారు {n} నెలల్లో", "aboutOne": "సుమారు 1 నెలలో",
           "range": "{lo}–{hi} నెలల్లో", "within": "{n} నెలల లోపు",
           "withinOne": "1 నెల లోపు", "asap": "వీలైనంత త్వరగా"},
    "pa": {"about": "ਲਗਭਗ {n} ਮਹੀਨਿਆਂ ਵਿੱਚ", "aboutOne": "ਲਗਭਗ 1 ਮਹੀਨੇ ਵਿੱਚ",
           "range": "{lo}–{hi} ਮਹੀਨਿਆਂ ਵਿੱਚ", "within": "{n} ਮਹੀਨਿਆਂ ਦੇ ਅੰਦਰ",
           "withinOne": "1 ਮਹੀਨੇ ਦੇ ਅੰਦਰ", "asap": "ਜਿੰਨੀ ਛੇਤੀ ਹੋ ਸਕੇ"},
}


def _date(iso: str | None) -> str:
    dt = parse_iso(iso)
    return dt.strftime("%d %b %Y") if dt else "—"


def window_phrase(window: dict, lang: str) -> str:
    """The follow-up interval as a phrase. Reads the plan's numbers; invents none."""
    w = _WINDOW[lang]
    lo = int(window.get("min_months") or 0)
    hi = int(window.get("max_months") or 0)
    if lo == hi == 0:
        return w["asap"]
    if lo == 0:
        return w["withinOne"] if hi == 1 else w["within"].format(n=hi)
    if lo == hi:
        return w["aboutOne"] if lo == 1 else w["about"].format(n=lo)
    return w["range"].format(lo=lo, hi=hi)


def change_sentence(comparison: dict, lang: str) -> str:
    """The one sentence about the difference, in the reader's language.

    Chosen from the SIGN of a subtraction that has already happened. This function does
    not compare anything itself, and there is no phrasing available to it that says the
    disease has progressed — see the module docstring.
    """
    c = _COPY[lang]
    change = int(comparison.get("grade_change", 0))
    if change == 0:
        return c["changeSame"]
    magnitude = abs(change)
    words = _MAGNITUDE[lang]
    n = words[magnitude] if magnitude < len(words) else str(magnitude)
    unit = c["unitOne"] if magnitude == 1 else c["unitMany"]
    key = "changeHigher" if change > 0 else "changeLower"
    return c[key].format(n=n, unit=unit)


# The follow-up reminder. Deliberately short: it names no grade, no severity and no
# referral status, because a reminder is read on a lock screen and by whoever is holding
# the phone. It says that a screening is due and nothing clinical at all.
_REMINDER: dict[str, dict[str, str]] = {
    "en": {
        "title": "CareBridge follow-up reminder",
        "body": "It is time for your next eye screening.",
        "window": "Suggested: {window}.",
        "how": "Visit your health centre for a retinal photograph, or open CareBridge to screen again.",
        "attached": "Your previous report is attached for reference.",
        "disclaimer": "This is a screening reminder, not a medical diagnosis.",
    },
    "hi": {
        "title": "केयरब्रिज अनुवर्ती अनुस्मारक",
        "body": "आपकी अगली आँखों की जाँच का समय आ गया है।",
        "window": "सुझाव: {window}।",
        "how": "रेटिना की तस्वीर के लिए अपने स्वास्थ्य केंद्र जाएँ, या दोबारा जाँच के लिए केयरब्रिज खोलें।",
        "attached": "संदर्भ के लिए आपकी पिछली रिपोर्ट संलग्न है।",
        "disclaimer": "यह एक जाँच अनुस्मारक है, कोई चिकित्सीय निदान नहीं।",
    },
    "te": {
        "title": "కేర్‌బ్రిడ్జ్ తదుపరి పరీక్ష గుర్తుచేత",
        "body": "మీ తదుపరి కంటి పరీక్షకు సమయం వచ్చింది.",
        "window": "సూచన: {window}.",
        "how": "రెటీనా ఫోటో కోసం మీ ఆరోగ్య కేంద్రానికి వెళ్ళండి, లేదా మళ్ళీ పరీక్ష కోసం కేర్‌బ్రిడ్జ్ తెరవండి.",
        "attached": "సూచన కోసం మీ మునుపటి రిపోర్ట్ జతచేయబడింది.",
        "disclaimer": "ఇది పరీక్ష గుర్తుచేత మాత్రమే, వైద్య నిర్ధారణ కాదు.",
    },
    "pa": {
        "title": "ਕੇਅਰਬ੍ਰਿਜ ਅਗਲੀ ਜਾਂਚ ਯਾਦ-ਪੱਤਰ",
        "body": "ਤੁਹਾਡੀ ਅਗਲੀ ਅੱਖਾਂ ਦੀ ਜਾਂਚ ਦਾ ਸਮਾਂ ਆ ਗਿਆ ਹੈ।",
        "window": "ਸੁਝਾਅ: {window}।",
        "how": "ਰੈਟਿਨਾ ਦੀ ਤਸਵੀਰ ਲਈ ਆਪਣੇ ਸਿਹਤ ਕੇਂਦਰ ਜਾਓ, ਜਾਂ ਦੁਬਾਰਾ ਜਾਂਚ ਲਈ ਕੇਅਰਬ੍ਰਿਜ ਖੋਲ੍ਹੋ।",
        "attached": "ਹਵਾਲੇ ਲਈ ਤੁਹਾਡੀ ਪਿਛਲੀ ਰਿਪੋਰਟ ਨੱਥੀ ਹੈ।",
        "disclaimer": "ਇਹ ਇੱਕ ਜਾਂਚ ਯਾਦ-ਪੱਤਰ ਹੈ, ਕੋਈ ਮੈਡੀਕਲ ਨਿਦਾਨ ਨਹੀਂ।",
    },
}


def build_reminder_message(follow_up: dict, language: str = DEFAULT_LANGUAGE) -> str:
    """The reminder that brings the same account back for another screening.

    Reads the window off the plan and prints nothing else about the patient. See the
    comment above `_REMINDER` for why that restraint is deliberate.
    """
    lang = normalise_language(language)
    c = _REMINDER[lang]
    window = follow_up.get("recommended_window") or {}
    lines = [f"\U0001F441 *{c['title']}*", "", c["body"]]
    if window:
        lines.append(c["window"].format(window=window_phrase(window, lang)))
    lines += ["", c["how"], "", f"\U0001F4C4 {c['attached']}", "",
              f"\u26A0\uFE0F {c['disclaimer']}"]
    return "\n".join(lines)


def build_comparison_message(comparison: dict, follow_up: dict | None = None,
                             language: str = DEFAULT_LANGUAGE) -> str:
    """The WhatsApp body for one comparison.

    `comparison` is the object from `comparison.py`; `follow_up` is the plan from
    `followup.py`. Nothing is looked up, recalculated or inferred, and an absent value
    prints as an absent value.
    """
    lang = normalise_language(language)
    c = _COPY[lang]
    prev = comparison.get("previous") or {}
    curr = comparison.get("current") or {}

    def grade_line(side: dict) -> str:
        g = side.get("icdr_grade")
        if g is None:
            return "—"
        label = side.get("severity_label") or ICDR_LABELS.get(int(g), "")
        return f"{c['grade'].format(grade=int(g))} · {label}"

    lines = [f"👁 *{c['title']}*", "", c["intro"], ""]
    lines += [
        f"*{c['previousHeading']}* — {_date(prev.get('date'))}",
        f"• {grade_line(prev)}",
        "",
        f"*{c['currentHeading']}* — {_date(curr.get('date'))}",
        f"• {grade_line(curr)}",
        "",
        f"*{c['changeHeading']}*",
        f"{prev.get('icdr_grade')} → {curr.get('icdr_grade')}",
        change_sentence(comparison, lang),
        c["notProgression"],
        "",
    ]

    if follow_up:
        window = follow_up.get("recommended_window") or {}
        priority = window.get("priority", "routine")
        sentence = _FOLLOW_UP[lang].get(priority, _FOLLOW_UP[lang]["routine"])
        lines += [
            f"*{c['followUpHeading']}*",
            sentence.format(window=window_phrase(window, lang)),
            "",
        ]

    review = curr.get("clinician_review_status")
    if review and review != "pending":
        lines += [f"*{c['clinicianHeading']}*", f"• {review}"]
        if curr.get("clinician_grade") is not None:
            lines.append(f"• {c['clinicianGrade'].format(grade=curr['clinician_grade'])}")
        lines.append("")

    lines += [f"📄 {c['attached']}", "", f"⚠️ {c['disclaimer']}"]
    return "\n".join(lines)


__all__ = ["build_comparison_message", "build_reminder_message", "change_sentence",
           "window_phrase", "LANGUAGES",
           "DEFAULT_LANGUAGE", "normalise_language"]
