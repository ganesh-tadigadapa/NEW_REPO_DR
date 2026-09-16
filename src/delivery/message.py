"""The words that travel with the PDF, in the patient's CareBridge language.

READ THIS BEFORE EDITING. This module performs no analysis. Every clinical value it
prints — the grade, the ICDR label, whether a referral is indicated — is read verbatim
from the metadata copied off the screening result at the time that result was produced.
There is no threshold here, no comparison, no rounding and no "if grade >= 2". The one
piece of branching is which pre-written sentence to print for a grade the model already
decided, which is exactly what the result page on the website already does.

The disclaimer is part of the message, not a footnote: it is the last thing the patient
reads, in their own language, on every send.

Languages match CareBridge's own list (en, hi, te, pa) and the patient's current choice
is used. There is no separate WhatsApp language preference, and there must not be one.
"""
from __future__ import annotations

from src.common.config import ICDR_LABELS

LANGUAGES = ("en", "hi", "te", "pa")
DEFAULT_LANGUAGE = "en"


def normalise_language(code: str | None) -> str:
    """A presentation preference arriving from a client, allow-listed. Anything
    unrecognised falls back to English rather than being trusted."""
    c = (code or "").strip().lower()
    return c if c in LANGUAGES else DEFAULT_LANGUAGE


# One pre-written sentence per ICDR grade, per language. Indexed by the grade the model
# reported — never by anything computed here. These mirror the copy the patient has
# already read on the result page (web/lib/i18n/translations/*.ts, `result.meaning`),
# shortened for a phone message.
_MEANING: dict[str, list[str]] = {
    "en": [
        "Today's photograph did not show signs of diabetes affecting the back of your eye.",
        "Very early changes were seen in the small blood vessels at the back of your eye. This is common and usually does not affect sight now.",
        "Clear changes were seen in the blood vessels at the back of your eye. Your sight may still feel normal — this is the point at which an eye doctor should look at your eyes.",
        "Many changes were seen in the blood vessels at the back of your eye. An eye specialist should examine you soon, because treatment works best before symptoms start.",
        "Advanced changes were seen, including fragile new blood vessels. This stage can affect sight, and it is treatable. Please see an eye specialist as quickly as you can.",
    ],
    "hi": [
        "आज की तस्वीर में आपकी आँख के पीछे मधुमेह का कोई असर नहीं दिखा।",
        "आपकी आँख के पीछे की छोटी रक्त नलिकाओं में बहुत शुरुआती बदलाव दिखे हैं। यह आम बात है और आमतौर पर अभी दृष्टि पर असर नहीं डालता।",
        "आपकी आँख के पीछे की रक्त नलिकाओं में स्पष्ट बदलाव दिखे हैं। हो सकता है आपकी दृष्टि अभी सामान्य लगे — यही वह अवस्था है जब आँखों के डॉक्टर को आपकी जाँच करनी चाहिए।",
        "आपकी आँख के पीछे की रक्त नलिकाओं में कई बदलाव दिखे हैं। किसी नेत्र विशेषज्ञ को जल्द ही आपकी जाँच करनी चाहिए, क्योंकि लक्षण शुरू होने से पहले इलाज सबसे अच्छा काम करता है।",
        "उन्नत बदलाव दिखे हैं, जिनमें कमज़ोर नई रक्त नलिकाएँ भी शामिल हैं। इस अवस्था में दृष्टि प्रभावित हो सकती है, और इसका इलाज संभव है। कृपया जितनी जल्दी हो सके नेत्र विशेषज्ञ से मिलें।",
    ],
    "te": [
        "ఈ రోజు తీసిన ఫోటోలో మీ కంటి వెనుక భాగంపై మధుమేహం ప్రభావం కనిపించలేదు.",
        "మీ కంటి వెనుక ఉన్న సన్నని రక్తనాళాలలో చాలా ప్రారంభ దశ మార్పులు కనిపించాయి. ఇది సాధారణమే, సాధారణంగా ఇప్పుడు చూపుపై ప్రభావం ఉండదు.",
        "మీ కంటి వెనుక ఉన్న రక్తనాళాలలో స్పష్టమైన మార్పులు కనిపించాయి. మీ చూపు ఇప్పటికీ మామూలుగానే అనిపించవచ్చు — ఇదే కంటి వైద్యుడు మీ కళ్ళను పరీక్షించవలసిన దశ.",
        "మీ కంటి వెనుక ఉన్న రక్తనాళాలలో అనేక మార్పులు కనిపించాయి. కంటి నిపుణుడు త్వరలోనే మిమ్మల్ని పరీక్షించాలి, ఎందుకంటే లక్షణాలు మొదలయ్యే ముందే చికిత్స బాగా పనిచేస్తుంది.",
        "పెళుసైన కొత్త రక్తనాళాలతో సహా ముదిరిన మార్పులు కనిపించాయి. ఈ దశలో చూపు దెబ్బతినే అవకాశం ఉంది, దీనికి చికిత్స ఉంది. దయచేసి వీలైనంత త్వరగా కంటి నిపుణుడిని కలవండి.",
    ],
    "pa": [
        "ਅੱਜ ਦੀ ਤਸਵੀਰ ਵਿੱਚ ਤੁਹਾਡੀ ਅੱਖ ਦੇ ਪਿੱਛਲੇ ਹਿੱਸੇ ਉੱਤੇ ਸ਼ੂਗਰ ਦਾ ਕੋਈ ਅਸਰ ਨਹੀਂ ਦਿਖਿਆ।",
        "ਤੁਹਾਡੀ ਅੱਖ ਦੇ ਪਿੱਛੇ ਦੀਆਂ ਛੋਟੀਆਂ ਖ਼ੂਨ ਨਾੜੀਆਂ ਵਿੱਚ ਬਹੁਤ ਸ਼ੁਰੂਆਤੀ ਤਬਦੀਲੀਆਂ ਦਿਖੀਆਂ ਹਨ। ਇਹ ਆਮ ਗੱਲ ਹੈ ਅਤੇ ਆਮ ਤੌਰ ਉੱਤੇ ਹੁਣ ਨਜ਼ਰ ਉੱਤੇ ਅਸਰ ਨਹੀਂ ਪਾਉਂਦੀ।",
        "ਤੁਹਾਡੀ ਅੱਖ ਦੇ ਪਿੱਛੇ ਦੀਆਂ ਖ਼ੂਨ ਨਾੜੀਆਂ ਵਿੱਚ ਸਾਫ਼ ਤਬਦੀਲੀਆਂ ਦਿਖੀਆਂ ਹਨ। ਹੋ ਸਕਦਾ ਹੈ ਤੁਹਾਡੀ ਨਜ਼ਰ ਹਾਲੇ ਵੀ ਠੀਕ ਲੱਗੇ — ਇਹੀ ਉਹ ਪੜਾਅ ਹੈ ਜਦੋਂ ਅੱਖਾਂ ਦੇ ਡਾਕਟਰ ਨੂੰ ਤੁਹਾਡੀ ਜਾਂਚ ਕਰਨੀ ਚਾਹੀਦੀ ਹੈ।",
        "ਤੁਹਾਡੀ ਅੱਖ ਦੇ ਪਿੱਛੇ ਦੀਆਂ ਖ਼ੂਨ ਨਾੜੀਆਂ ਵਿੱਚ ਕਈ ਤਬਦੀਲੀਆਂ ਦਿਖੀਆਂ ਹਨ। ਅੱਖਾਂ ਦੇ ਮਾਹਿਰ ਨੂੰ ਛੇਤੀ ਹੀ ਤੁਹਾਡੀ ਜਾਂਚ ਕਰਨੀ ਚਾਹੀਦੀ ਹੈ, ਕਿਉਂਕਿ ਲੱਛਣ ਸ਼ੁਰੂ ਹੋਣ ਤੋਂ ਪਹਿਲਾਂ ਇਲਾਜ ਸਭ ਤੋਂ ਵਧੀਆ ਕੰਮ ਕਰਦਾ ਹੈ।",
        "ਕਮਜ਼ੋਰ ਨਵੀਆਂ ਖ਼ੂਨ ਨਾੜੀਆਂ ਸਮੇਤ ਵਧੀਆਂ ਹੋਈਆਂ ਤਬਦੀਲੀਆਂ ਦਿਖੀਆਂ ਹਨ। ਇਸ ਪੜਾਅ ਉੱਤੇ ਨਜ਼ਰ ਉੱਤੇ ਅਸਰ ਪੈ ਸਕਦਾ ਹੈ, ਅਤੇ ਇਸ ਦਾ ਇਲਾਜ ਹੋ ਸਕਦਾ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਜਿੰਨੀ ਛੇਤੀ ਹੋ ਸਕੇ ਅੱਖਾਂ ਦੇ ਮਾਹਿਰ ਨੂੰ ਮਿਲੋ।",
    ],
}

_COPY: dict[str, dict[str, str]] = {
    "en": {
        "title": "CareBridge Screening Report",
        "intro": "Your retinal screening has been completed.",
        "resultHeading": "Screening result",
        "grade": "DR grade",
        "gradeValue": "Grade {grade} of 4",
        "classification": "Classification",
        "referral": "Referral status",
        "referable": "Referral recommended",
        "notReferable": "No referral indicated today",
        "meansHeading": "What this means",
        "attached": "Your detailed screening report is attached.",
        "noGradeHeading": "A grade could not be produced",
        "noGradeBody": ("The photograph was clear enough, but the grading model did not "
                        "run. The lesion findings and the clinical-rule cross-check in "
                        "the attached report are still valid."),
        "disclaimer": ("This is an AI-assisted screening result, not a medical diagnosis. "
                       "Please show this report to an eye-care professional."),
    },
    "hi": {
        "title": "केयरब्रिज स्क्रीनिंग रिपोर्ट",
        "intro": "आपकी आँखों की स्क्रीनिंग पूरी हो गई है।",
        "resultHeading": "स्क्रीनिंग परिणाम",
        "grade": "डीआर ग्रेड",
        "gradeValue": "4 में से ग्रेड {grade}",
        "classification": "वर्गीकरण",
        "referral": "रेफरल स्थिति",
        "referable": "रेफरल की सलाह दी जाती है",
        "notReferable": "आज रेफरल की आवश्यकता नहीं",
        "meansHeading": "इसका क्या अर्थ है",
        "attached": "आपकी विस्तृत स्क्रीनिंग रिपोर्ट संलग्न है।",
        "noGradeHeading": "ग्रेड तैयार नहीं किया जा सका",
        "noGradeBody": ("तस्वीर पर्याप्त स्पष्ट थी, लेकिन ग्रेडिंग मॉडल नहीं चला। संलग्न "
                        "रिपोर्ट में दिए गए घाव के निष्कर्ष और नैदानिक-नियम जाँच अब भी मान्य हैं।"),
        "disclaimer": ("यह एआई-सहायित स्क्रीनिंग परिणाम है, कोई चिकित्सीय निदान नहीं। कृपया यह "
                       "रिपोर्ट किसी नेत्र विशेषज्ञ को दिखाएँ।"),
    },
    "te": {
        "title": "కేర్‌బ్రిడ్జ్ స్క్రీనింగ్ రిపోర్ట్",
        "intro": "మీ కంటి స్క్రీనింగ్ పూర్తయింది.",
        "resultHeading": "స్క్రీనింగ్ ఫలితం",
        "grade": "డీఆర్ గ్రేడ్",
        "gradeValue": "4లో గ్రేడ్ {grade}",
        "classification": "వర్గీకరణ",
        "referral": "రెఫరల్ స్థితి",
        "referable": "రెఫరల్ సిఫార్సు చేయబడింది",
        "notReferable": "ఈ రోజు రెఫరల్ అవసరం లేదు",
        "meansHeading": "దీని అర్థం ఏమిటి",
        "attached": "మీ వివరమైన స్క్రీనింగ్ రిపోర్ట్ జతచేయబడింది.",
        "noGradeHeading": "గ్రేడ్ తయారు చేయలేకపోయాము",
        "noGradeBody": ("ఫోటో తగినంత స్పష్టంగా ఉంది, కానీ గ్రేడింగ్ మోడల్ నడవలేదు. జతచేసిన "
                        "రిపోర్ట్‌లోని గాయాల ఆధారాలు మరియు క్లినికల్-రూల్ తనిఖీ ఇప్పటికీ చెల్లుతాయి."),
        "disclaimer": ("ఇది ఏఐ-సహాయక స్క్రీనింగ్ ఫలితం, వైద్య నిర్ధారణ కాదు. దయచేసి ఈ రిపోర్ట్‌ను "
                       "కంటి వైద్య నిపుణుడికి చూపించండి."),
    },
    "pa": {
        "title": "ਕੇਅਰਬ੍ਰਿਜ ਸਕ੍ਰੀਨਿੰਗ ਰਿਪੋਰਟ",
        "intro": "ਤੁਹਾਡੀ ਅੱਖਾਂ ਦੀ ਸਕ੍ਰੀਨਿੰਗ ਪੂਰੀ ਹੋ ਗਈ ਹੈ।",
        "resultHeading": "ਸਕ੍ਰੀਨਿੰਗ ਨਤੀਜਾ",
        "grade": "ਡੀਆਰ ਗ੍ਰੇਡ",
        "gradeValue": "4 ਵਿੱਚੋਂ ਗ੍ਰੇਡ {grade}",
        "classification": "ਵਰਗੀਕਰਨ",
        "referral": "ਰੈਫ਼ਰਲ ਸਥਿਤੀ",
        "referable": "ਰੈਫ਼ਰਲ ਦੀ ਸਲਾਹ ਦਿੱਤੀ ਜਾਂਦੀ ਹੈ",
        "notReferable": "ਅੱਜ ਰੈਫ਼ਰਲ ਦੀ ਲੋੜ ਨਹੀਂ",
        "meansHeading": "ਇਸ ਦਾ ਕੀ ਮਤਲਬ ਹੈ",
        "attached": "ਤੁਹਾਡੀ ਵਿਸਥਾਰਤ ਸਕ੍ਰੀਨਿੰਗ ਰਿਪੋਰਟ ਨੱਥੀ ਹੈ।",
        "noGradeHeading": "ਗ੍ਰੇਡ ਤਿਆਰ ਨਹੀਂ ਕੀਤਾ ਜਾ ਸਕਿਆ",
        "noGradeBody": ("ਤਸਵੀਰ ਕਾਫ਼ੀ ਸਾਫ਼ ਸੀ, ਪਰ ਗ੍ਰੇਡਿੰਗ ਮਾਡਲ ਨਹੀਂ ਚੱਲਿਆ। ਨੱਥੀ ਰਿਪੋਰਟ ਵਿੱਚ ਦਿੱਤੇ "
                        "ਜ਼ਖ਼ਮਾਂ ਦੇ ਸਬੂਤ ਅਤੇ ਕਲੀਨਿਕਲ-ਨਿਯਮ ਜਾਂਚ ਹਾਲੇ ਵੀ ਸਹੀ ਹਨ।"),
        "disclaimer": ("ਇਹ ਏਆਈ-ਸਹਾਇਤ ਸਕ੍ਰੀਨਿੰਗ ਨਤੀਜਾ ਹੈ, ਕੋਈ ਮੈਡੀਕਲ ਨਿਦਾਨ ਨਹੀਂ। ਕਿਰਪਾ ਕਰਕੇ ਇਹ "
                       "ਰਿਪੋਰਟ ਅੱਖਾਂ ਦੇ ਮਾਹਿਰ ਨੂੰ ਦਿਖਾਓ।"),
    },
}


def _clamp_grade(grade: int) -> int:
    return min(max(int(grade), 0), 4)


def build_message(meta: dict, language: str = DEFAULT_LANGUAGE) -> str:
    """The WhatsApp body for one already-completed screening.

    `meta` is what `ReportMediaStore` copied off the analyse result. Nothing is looked
    up, recalculated or inferred; an absent grade prints as an absent grade.
    """
    lang = normalise_language(language)
    c = _COPY[lang]
    grade = meta.get("icdr_grade")
    lines = [f"🩺 *{c['title']}*", "", c["intro"], ""]

    if grade is None:
        # The model did not run. We say so instead of printing a grade we do not have.
        lines += [f"*{c['noGradeHeading']}*", c["noGradeBody"], ""]
    else:
        g = _clamp_grade(grade)
        # The clinical label as the API reported it, with the frozen ICDR name as the
        # only fallback. Never re-derived from a probability.
        label = meta.get("icdr_label") or ICDR_LABELS.get(g, "")
        referable = meta.get("referable")
        lines += [
            f"*{c['resultHeading']}*",
            f"• {c['grade']}: {c['gradeValue'].format(grade=g)}",
            f"• {c['classification']}: {label}",
            f"• {c['referral']}: {c['referable'] if referable else c['notReferable']}",
            "",
            f"*{c['meansHeading']}*",
            _MEANING[lang][g],
            "",
        ]

    lines += [f"📄 {c['attached']}", "", f"⚠️ {c['disclaimer']}"]
    return "\n".join(lines)


__all__ = ["LANGUAGES", "DEFAULT_LANGUAGE", "build_message", "normalise_language"]
