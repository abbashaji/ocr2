"""Scoring helpers (port of ``legacy/bench.py``: ``base``, ``words``, ``score``)."""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz.distance import Levenshtein as Lev

__all__ = ["base", "letters", "words", "word_accuracy", "strip_markers"]

_DIGITS_FROM = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
_DIGITS_TO = "01234567890123456789"
_DIGIT_TABLE = str.maketrans(_DIGITS_FROM, _DIGITS_TO)
_BIDI_MARKS = re.compile("[\u200e\u200f]")
_CITATION = re.compile(r"\[[0-9۰-۹٠-٩]+\]")


def base(s: str) -> str:
    """Normalise Arabic/Persian variants, drop diacritics, map digits to ASCII.

    ZWNJ (U+200C) becomes a plain space; LRM/RLM are removed.
    """
    s = (
        s.replace("ي", "ی").replace("ى", "ی").replace("ك", "ک")
        .replace("ة", "ه").replace("ۀ", "ه").replace("\u200c", " ")
    )
    s = "".join(c for c in s if not (0x064B <= ord(c) <= 0x065F))
    s = s.translate(_DIGIT_TABLE)
    return _BIDI_MARKS.sub("", s)


def letters(s: str) -> str:
    return "".join(c for c in base(s) if unicodedata.category(c)[0] == "L")


def words(s: str) -> list[str]:
    """Word list used for scoring: letters and digits only, everything else splits."""
    return "".join(
        c if unicodedata.category(c)[0] in "LN" else " " for c in base(s)
    ).split()


def strip_markers(s: str) -> str:
    """Remove citation markers such as ``[۱۱]`` (digits in square brackets)."""
    return _CITATION.sub("", s)


def word_accuracy(ref: str, hyp: str) -> float:
    """1 - word-level Levenshtein distance / number of reference words."""
    wr, wh = words(ref), words(hyp)
    return 1 - Lev.distance(wr, wh) / max(1, len(wr))
