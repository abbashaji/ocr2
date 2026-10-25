"""Parser for Tesseract hOCR output with character boxes (``legacy/lib.py:tess_chars``)."""

from __future__ import annotations

import html
import re

from .markers import Char, HWord

__all__ = ["parse_hocr"]

_WORD = re.compile(r"<span class='ocrx_word'.*?(?=<span class='ocrx_word'|</p>)", re.S)
_CINFO = re.compile(
    r"<span class='ocrx_cinfo' title='x_bboxes (\d+) (\d+) (\d+) (\d+); x_conf ([\d.]+)'>(.*?)</span>",
    re.S,
)
_WCONF = re.compile(r"x_wconf (\d+)")
_BBOX = re.compile(r"bbox (\d+) (\d+) (\d+) (\d+)")


def parse_hocr(out: str) -> list[HWord]:
    """Words in reading (logical) order; words without character boxes are skipped."""
    words: list[HWord] = []
    for m in _WORD.finditer(out):
        chunk = m.group(0)
        head = chunk.split(">", 1)[0]
        wc = _WCONF.search(head)
        wconf = float(wc.group(1)) if wc else 0.0
        bb = _BBOX.search(head)
        box = (int(bb.group(1)), int(bb.group(2)), int(bb.group(3)), int(bb.group(4))) if bb else None
        chars = tuple(
            Char(html.unescape(c[5]), int(c[0]), int(c[1]), int(c[2]), int(c[3]), float(c[4]), wconf)
            for c in _CINFO.findall(chunk)
        )
        if chars:
            words.append(HWord(chars, wconf, box))
    return words
