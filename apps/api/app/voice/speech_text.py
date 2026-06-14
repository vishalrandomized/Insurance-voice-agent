"""Normalize agent text for TTS (spoken form only — the on-screen transcript
keeps its original formatting).

A US-English TTS voice mangles Indian number formats (₹, lakh/crore, the
1,50,000-style grouping) and reads citation markers aloud. This converts those
into plain spoken words before the text is sent to the TTS provider.
"""
from __future__ import annotations

import re

_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight",
    "nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen",
    "sixteen", "seventeen", "eighteen", "nineteen",
]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy",
         "eighty", "ninety"]


def _two(n: int) -> str:
    if n < 20:
        return _ONES[n]
    tens, ones = divmod(n, 10)
    return _TENS[tens] + ((" " + _ONES[ones]) if ones else "")


def _under_thousand(n: int) -> str:
    if n < 100:
        return _two(n)
    hundreds, rest = divmod(n, 100)
    return _two(hundreds) + " hundred" + ((" " + _two(rest)) if rest else "")


def indian_words(n: int) -> str:
    """Whole number -> Indian-style words (crore/lakh/thousand)."""
    if n == 0:
        return "zero"
    crore, n = divmod(n, 10_000_000)
    lakh, n = divmod(n, 100_000)
    thousand, n = divmod(n, 1_000)
    rest = n
    parts: list[str] = []
    if crore:
        parts.append(_under_thousand(crore) + (" crore" if crore == 1 else " crores"))
    if lakh:
        parts.append(_under_thousand(lakh) + (" lakh" if lakh == 1 else " lakhs"))
    if thousand:
        parts.append(_under_thousand(thousand) + " thousand")
    if rest:
        parts.append(_under_thousand(rest))
    return " ".join(parts)


_CITATION_RE = re.compile(r"\s*\[C\d+\]")
# "₹10 Lakh", "10 Lakh", "₹1 Crore", "1.5 lakh" (₹ optional). The number here is
# the COUNT of lakhs/crores, said in Indian style (rupees implied).
_LAKH_CRORE_RE = re.compile(
    r"₹?\s*(\d+(?:\.\d+)?)\s*(lakh|crore)s?\b", re.IGNORECASE
)
# "₹5,00,000", "₹25,000", "₹5000" — grouped rupee amounts (run AFTER lakh/crore).
# Commas must sit between digits (grouping) so a trailing list comma isn't eaten.
_RUPEE_NUM_RE = re.compile(r"₹\s*(\d+(?:,\d+)*)")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_ACRONYMS = [
    (re.compile(r"\bSI\b"), "Sum Insured"),
    (re.compile(r"\bPED\b"), "pre-existing disease"),
    (re.compile(r"\bOPD\b"), "O P D"),
    (re.compile(r"\bAYUSH\b", re.IGNORECASE), "Ayush"),
]


def _decimal_words(num: str) -> str:
    if "." not in num:
        return indian_words(int(num))
    whole, frac = num.split(".", 1)
    digits = " ".join(_ONES[int(d)] for d in frac if d.isdigit())
    return indian_words(int(whole or "0")) + " point " + digits


def _lakh_crore_sub(m: re.Match[str]) -> str:
    num, unit = m.group(1), m.group(2).lower()
    words = _decimal_words(num)
    plural = "" if num in ("1", "1.0") else "s"
    return f"{words} {unit}{plural}"


def _rupee_num_sub(m: re.Match[str]) -> str:
    digits = m.group(1).replace(",", "")
    if not digits.isdigit():
        return m.group(0)
    return indian_words(int(digits))


def _percent_sub(m: re.Match[str]) -> str:
    return f"{_decimal_words(m.group(1))} percent"


def normalize_for_speech(text: str) -> str:
    text = _CITATION_RE.sub("", text)
    text = _LAKH_CRORE_RE.sub(_lakh_crore_sub, text)
    text = _RUPEE_NUM_RE.sub(_rupee_num_sub, text)
    text = _PERCENT_RE.sub(_percent_sub, text)
    for pattern, replacement in _ACRONYMS:
        text = pattern.sub(replacement, text)
    return re.sub(r"\s{2,}", " ", text).strip()
