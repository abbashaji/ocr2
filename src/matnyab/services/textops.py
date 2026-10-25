"""Digit conversion and Persian text normalisation."""

from __future__ import annotations

import re
from typing import Literal

_FA = "۰۱۲۳۴۵۶۷۸۹"
_AR = "٠١٢٣٤٥٦٧٨٩"
_ASCII = "0123456789"

_TO_FA = {ord(c): _FA[i] for i, c in enumerate(_ASCII)}
_TO_FA.update({ord(c): _FA[i] for i, c in enumerate(_AR)})
_TO_EN = {ord(c): _ASCII[i] for i, c in enumerate(_FA)}
_TO_EN.update({ord(c): _ASCII[i] for i, c in enumerate(_AR)})
_TO_EN.update({ord("٫"): ".", ord("٬"): ",", ord("٪"): "%"})

_ANY_DIGITS = _ASCII + _AR + _FA
# A Latin identifier-ish token: alphanumerics/underscore, optionally joined by . or ,
_TOKEN = re.compile(r"[A-Za-z0-9_]+(?:[.,](?=[A-Za-z0-9_])[A-Za-z0-9_]+)*")
_LATIN_LETTER = re.compile(r"[A-Za-z_]")


def _protected_mask(text: str) -> list[bool]:
    mask = [False] * len(text)
    for m in _TOKEN.finditer(text):
        if _LATIN_LETTER.search(m.group()):
            for i in range(m.start(), m.end()):
                mask[i] = True
    return mask


def _to_persian(text: str) -> str:
    n = len(text)
    mask = _protected_mask(text)

    def is_digit(i: int) -> bool:
        return 0 <= i < n and text[i] in _ANY_DIGITS and not mask[i]

    out: list[str] = []
    for i, ch in enumerate(text):
        if ch in _ANY_DIGITS:
            out.append(ch if mask[i] else _TO_FA.get(ord(ch), ch))
        elif ch == "." and is_digit(i - 1) and is_digit(i + 1):
            out.append("٫")
        elif (ch == "," and is_digit(i - 1) and is_digit(i + 1) and is_digit(i + 2)
              and is_digit(i + 3) and not is_digit(i + 4)):
            out.append("٬")
        elif ch == "%" and is_digit(i - 1):
            out.append("٪")
        else:
            out.append(ch)
    return "".join(out)


def convert_digits(text: str, style: Literal["keep", "fa", "en"]) -> str:
    if style == "keep":
        return text
    if style == "fa":
        return _to_persian(text)
    if style == "en":
        return text.translate(_TO_EN)
    raise ValueError(f"unknown digit style: {style!r}")


_NORMALIZE = {
    0x064A: "ی",  # Arabic yeh
    0x0649: "ی",  # alef maksura
    0x0643: "ک",  # Arabic kaf
    0x0640: None,  # tatweel
    0x00A0: " ",  # NBSP
}


def normalize_text(text: str) -> str:
    return text.translate(_NORMALIZE)
