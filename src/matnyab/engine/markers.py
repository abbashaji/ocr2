"""Geometric removal of superscript citation markers (port of ``legacy/markers.py``).

Markers such as ``[۱۱]`` are small raised digits glued to the previous word. Tesseract
returns them inside the same word, so characters whose box bottom sits clearly above the
line's baseline are flagged and dropped.
"""

from __future__ import annotations

from typing import NamedTuple, Optional, Sequence

import numpy as np

__all__ = ["Char", "HWord", "Token", "marker_flags", "clean_words_conf"]

SUP_CHARS = frozenset("0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩[]()")
PUNCT = frozenset(".,،:؛;!؟?")
ZERO = frozenset("۰٠0")  # the Persian zero is a tiny dot: by size alone it looks like a superscript
SQUARE = frozenset("[]")
# A real marker sits ~0.6 line heights above the baseline; ordinary digits measure ~0.35 because the
# median character bottom is pulled down by letters with descenders. Used for digits outside brackets.
STRICT_UP = 0.5


class Char(NamedTuple):
    ch: str
    x0: int
    y0: int
    x1: int
    y1: int
    conf: float
    word_conf: float


class HWord(NamedTuple):
    """One hOCR word: its characters, Tesseract word confidence and word box."""

    chars: tuple[Char, ...]
    conf: float
    box: Optional[tuple[int, int, int, int]]


class Token(NamedTuple):
    """A cleaned word. ``box`` is in the coordinates of the recognised (scaled, padded) image."""

    text: str
    conf: float
    box: Optional[tuple[int, int, int, int]]


def marker_flags(
    words: Sequence[Sequence[Char]], frac_h: float = 0.8, frac_up: float = 0.3
) -> list[list[bool]]:
    """Parallel list of bool lists; True marks a marker character.

    Tier 1: a word with a square bracket (``[۱۱]``) is judged as before. Tier 2: a word without one only loses
    digits that are clearly raised (it used to lose ``۳۱`` and the leading ``۱`` of ``۱٫۶۴``).
    """
    chars = [c for w in words for c in w]
    base = [c for c in chars if c.ch not in SUP_CHARS and c.ch not in PUNCT]
    if len(base) < 4:  # too little text to estimate the baseline
        return [[False] * len(w) for w in words]
    height = float(np.median([c.y1 - c.y0 for c in base]))
    bottom = float(np.median([c.y1 for c in base]))

    def raised(c: Char) -> bool:
        return c.y1 <= bottom - frac_up * height

    out: list[list[bool]] = []
    for w in words:
        n = len(w)
        flag = [
            (
                c.ch in SUP_CHARS and c.ch not in ZERO and raised(c)
                and ((c.y1 - c.y0) <= frac_h * height or c.y1 <= bottom - 0.4 * height)
            )
            for c in w
        ]
        if not any(c.ch in SQUARE for c in w):
            # Without a square bracket a digit is a marker only when clearly raised. Ordinary numbers ("۳۱",
            # "۱٫۶۴", "و۳۱") measure ~0.35 raised and stay; a detached superscript fragment measures ~0.6.
            flag = [f and c.y1 <= bottom - STRICT_UP * height for f, c in zip(flag, w)]
        changed = True
        while changed:  # absorb brackets and zeros that touch a flagged run
            changed = False
            for i in range(n):
                if flag[i] or not (w[i].ch in "[]()" or w[i].ch in ZERO):
                    continue
                touches = (i > 0 and flag[i - 1]) or (i + 1 < n and flag[i + 1])
                if touches and (w[i].ch not in ZERO or raised(w[i])):
                    flag[i] = True
                    changed = True
        out.append(flag)
    return out


def _union(boxes: Sequence[tuple[int, int, int, int]]) -> tuple[int, int, int, int]:
    return (
        min(b[0] for b in boxes), min(b[1] for b in boxes),
        max(b[2] for b in boxes), max(b[3] for b in boxes),
    )


def clean_words_conf(words: Sequence[HWord], remove_markers: bool = True) -> list[Token]:
    """Tokens (text, Tesseract word confidence, box) with marker characters removed.

    Words that end up empty are dropped. When characters were removed, the word box is the
    union of the remaining character boxes, otherwise the hOCR word box.
    """
    flags = (
        marker_flags([w.chars for w in words])
        if remove_markers
        else [[False] * len(w.chars) for w in words]
    )
    out: list[Token] = []
    for w, flag in zip(words, flags):
        kept = [c for c, f in zip(w.chars, flag) if not f]
        if not kept:
            continue
        if len(kept) == len(w.chars) and w.box is not None:
            box: Optional[tuple[int, int, int, int]] = w.box
        else:
            box = _union([(c.x0, c.y0, c.x1, c.y1) for c in kept])
        out.append(Token("".join(c.ch for c in kept), float(kept[0].word_conf), box))
    return out
