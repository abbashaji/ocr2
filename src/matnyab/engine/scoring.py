"""Scoring helpers (port of ``legacy/bench.py``: ``base``, ``words``, ``score``)."""

from __future__ import annotations

import re
import unicodedata

from typing import Optional

from rapidfuzz.distance import LCSseq, Levenshtein as Lev

__all__ = [
    "base", "letters", "words", "word_accuracy", "strip_markers",
    "numbers", "puncts", "f1", "numbers_f1", "punct_f1",
]

_DIGITS_FROM = "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩"
_DIGITS_TO = "01234567890123456789"
_DIGIT_TABLE = str.maketrans(_DIGITS_FROM, _DIGITS_TO)
_BIDI_MARKS = re.compile("[\u200e\u200f]")
_CITATION = re.compile(r"\[[0-9۰-۹٠-٩]+\]")
_NUM = re.compile(r"\d+(?:[.,٫٬،]\d+)*")


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


def numbers(s: str) -> list[str]:
    """Numbers as written, digits folded to ASCII.

    ``٫`` and ``٬`` are folded to ``.`` and ``,`` so that only a WRONG separator (``۱٫۶۴`` read as ``۱،۶۴``
    or ``،۶۴``) counts as a mismatch. Mirrors ``numbers()`` of ``ocr/ft/evaluate.py``.
    """
    return [m.replace("٫", ".").replace("٬", ",") for m in _NUM.findall(base(s))]


def puncts(s: str) -> str:
    """The sequence of punctuation marks (letters, digits and spaces dropped). Mirrors ``ocr/ft/evaluate.py``."""
    return "".join(c for c in base(s) if unicodedata.category(c).startswith("P") or c in "٪٫٬")


def f1(lcs: int, n_ref: int, n_hyp: int) -> Optional[float]:
    """``2 * LCS / (len(ref) + len(hyp))`` in 0..1; ``None`` when both sides are empty."""
    return 2 * lcs / (n_ref + n_hyp) if n_ref + n_hyp else None


def numbers_f1(ref: str, hyp: str) -> Optional[float]:
    """F1 of the number sequences (extra or missing numbers and wrong separators all cost)."""
    r, h = numbers(ref), numbers(hyp)
    return f1(LCSseq.similarity(r, h), len(r), len(h))


def punct_f1(ref: str, hyp: str) -> Optional[float]:
    """F1 of the punctuation-mark sequences (a ``،`` read as ``.`` or a lost mark costs)."""
    r, h = puncts(ref), puncts(hyp)
    return f1(LCSseq.similarity(r, h), len(r), len(h))
