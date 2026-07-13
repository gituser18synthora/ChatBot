"""Reply-language detection for chat responses.

The chatbot mirrors the language and style of the user's LATEST message:
English → English, Hindi (Devanagari) → Hindi, Hinglish (romanized Hindi in
Latin script) → Hinglish, Marathi → Marathi. An explicit request in the query
("answer in English", "hindi me batao") always wins over detection.

Pure script/marker heuristics — no LLM call, no external dependency. Known
limits: romanized Marathi is detected as Hinglish, and code-mixed queries
resolve to whichever script dominates.
"""
from __future__ import annotations

import re

ENGLISH = "English"
HINDI = "Hindi"
HINGLISH = "Hinglish"
MARATHI = "Marathi"

_DEVANAGARI_WORD_RE = re.compile(r"[ऀ-ॿ]+")
_LATIN_WORD_RE = re.compile(r"[a-z']+")

# Explicit "answer in <language>" requests: "in english", "hindi me batao",
# mixed-script "english में", and native forms ("हिंदी में", "मराठीत").
_POSTPOSITION = r"(?:\s+(?:me|mein|mai)\b|\s*(?:में|मध्ये))"
_EXPLICIT_PATTERNS = (
    (re.compile(rf"\b(?:in|into|to)\s+english\b|\benglish{_POSTPOSITION}|अंग्रेज़?ी में|इंग्लिश में|इंग्रजीत", re.I), ENGLISH),
    (re.compile(rf"\b(?:in|into|to)\s+hindi\b|\bhindi{_POSTPOSITION}|हिन्?दी में", re.I), HINDI),
    (re.compile(rf"\b(?:in|into|to)\s+marathi\b|\bmarathi{_POSTPOSITION}|मराठीत|मराठी\s*(?:में|मध्ये)", re.I), MARATHI),
    (re.compile(rf"\b(?:in|into|to)\s+hinglish\b|\bhinglish{_POSTPOSITION}", re.I), HINGLISH),
)

# Devanagari function words that separate Marathi from Hindi. Both use the
# same script, so the vote over these decides.
_MARATHI_MARKERS = {
    "आहे", "आहेत", "नाही", "आणि", "मध्ये", "काय", "कसे", "कशी", "किती", "मला",
    "तुम्ही", "तुमचे", "तुमच्या", "माझे", "माझी", "माझा", "माझ्या", "च्या", "चा",
    "ची", "चे", "होते", "होता", "आता", "पाहिजे", "द्या", "सांगा", "करा", "झाले", "असेल",
}
_HINDI_MARKERS = {
    "है", "हैं", "नहीं", "और", "में", "क्या", "कैसे", "कैसी", "कितना", "कितनी",
    "कितने", "मुझे", "आप", "आपका", "आपकी", "मेरा", "मेरी", "मेरे", "का", "की",
    "के", "था", "थी", "थे", "अब", "चाहिए", "दो", "बताओ", "बताइए", "करो", "करें",
    "हुआ", "होगा", "इसका", "उसका", "यह", "वह",
}

# Romanized-Hindi words that mark Hinglish. Deliberately excludes tokens that
# collide with English ("me", "to", "ka", "se", "ho", "na"); detection needs
# at least two distinct hits so one loanword never flips the language.
_HINGLISH_MARKERS = {
    "hai", "hain", "hoon", "nahi", "nahin", "nhi", "kya", "kyu", "kyun", "kaise",
    "kaisa", "kaisi", "kab", "kaun", "kahan", "kidhar", "mera", "meri", "mere",
    "tera", "teri", "tere", "apna", "apni", "apne", "aap", "aapka", "aapki",
    "aapke", "mujhe", "muje", "tumhe", "hum", "tum", "karo", "karna", "karke",
    "krna", "kro", "karega", "karegi", "karenge", "hoga", "hogi", "honge",
    "milega", "milegi", "chahiye", "chahie", "batao", "bata", "bataiye", "btao",
    "bolo", "dedo", "dijiye", "acha", "accha", "achha", "theek", "thik", "haan",
    "matlab", "kyunki", "lekin", "magar", "aur", "bhi", "toh", "abhi", "phir",
    "fir", "kuch", "kucch", "sab", "sabhi", "bahut", "bohot", "bhut", "zyada",
    "jyada", "thoda", "kitna", "kitni", "kitne", "paisa", "paise", "rupaye",
    "rupay", "wala", "wali", "wale", "yaar", "bhai", "namaste", "dhanyavad",
    "shukriya", "samajh", "samjha", "pata", "malum", "dikhao", "dikha", "chalo",
    "raha", "rahi", "rahe", "gaya", "gayi", "gaye", "liya", "diya", "kiya",
    "hua", "hui", "hue",
}

_STYLE_INSTRUCTIONS = {
    ENGLISH: "English",
    HINDI: "Hindi, written in Devanagari script",
    MARATHI: "Marathi, written in Devanagari script",
    HINGLISH: (
        "Hinglish — Hindi phrasing written in Latin/Roman script, casual "
        "conversational tone, keeping common English technical words as-is"
    ),
}


def detect_reply_language(text: str) -> str:
    """Language the reply should be written in, from the user's latest message."""
    t = text or ""
    for pattern, lang in _EXPLICIT_PATTERNS:
        if pattern.search(t):
            return lang

    deva_words = _DEVANAGARI_WORD_RE.findall(t)
    if deva_words:
        marathi = sum(1 for w in deva_words if w in _MARATHI_MARKERS)
        hindi = sum(1 for w in deva_words if w in _HINDI_MARKERS)
        return MARATHI if marathi > hindi else HINDI

    tokens = _LATIN_WORD_RE.findall(t.lower())
    hits = {tok for tok in tokens if tok in _HINGLISH_MARKERS}
    if len(hits) >= 2:
        return HINGLISH
    return ENGLISH


def language_style_instruction(language: str) -> str:
    return _STYLE_INSTRUCTIONS.get(language, _STYLE_INSTRUCTIONS[ENGLISH])


def _devanagari_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    deva = sum(1 for c in letters if "ऀ" <= c <= "ॿ")
    return deva / len(letters)


def needs_language_alignment(answer: str, language: str) -> bool:
    """True when `answer` is visibly NOT in the target language and should be
    re-rendered. Conservative: when the script already matches, the answer is
    left untouched (no LLM cost) even if the style could be improved."""
    if not answer:
        return False
    ratio = _devanagari_ratio(answer)
    if language == ENGLISH:
        return ratio > 0.2
    if language == HINDI:
        return ratio < 0.5
    if language == MARATHI:
        if ratio < 0.5:
            return True
        # Devanagari answer, but is it Hindi? Vote over function words.
        words = _DEVANAGARI_WORD_RE.findall(answer)
        marathi = sum(1 for w in words if w in _MARATHI_MARKERS)
        hindi = sum(1 for w in words if w in _HINDI_MARKERS)
        return hindi > marathi
    if language == HINGLISH:
        if ratio > 0.2:
            return True  # Devanagari answer for a Latin-script user
        tokens = set(_LATIN_WORD_RE.findall(answer.lower()))
        return len(tokens & _HINGLISH_MARKERS) < 2  # plain-English answer
    return False
