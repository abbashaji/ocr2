"""Lexicon correction (port of ``legacy/postproc.py`` + the guarded corrector of ``legacy/pipeline2.py``).

The wordfreq table is loaded lazily, once per process; candidate generation is memoised.
"""

from __future__ import annotations

import functools
import itertools
import re
import threading
from typing import Optional

from .scoring import base

__all__ = [
    "ALPHA", "TOKEN", "CFG", "LEX_CONFIG", "RAW_CONFIG", "load", "zipf", "candidates", "fix_final_kaf",
    "is_known", "corr_word", "correct_tok",
]

ALPHA = "ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیءآأؤئ"
GROUPS = [
    "نتبپثی", "جچحخ", "دذ", "رزژو", "سش", "صض", "طظ", "عغ", "فق", "کگ", "اآأ", "هة",
    "یئ", "لا", "کی", "مه", "ه ح", "وؤ", "خح",
]
CONF: frozenset[tuple[str, str]] = frozenset(
    pair for g in GROUPS for pair in itertools.permutations(g.replace(" ", ""), 2)
)
TOKEN = re.compile("[ء-يٱ-ۓ]+")
_ALPHA_ONLY = re.compile("[" + ALPHA + "]+")

# Settings of the legacy CLI (legacy/ocr_cli.py); raw mode = same with conf_skip=0.
CFG = dict(alpha=1.5, margin=0.3, floor=2.5, guard=2, conf_skip=90, sub_other=2.0,
           indel=2.0, max_cost=2.0, target=2.5)
LEX_CONFIG = dict(CFG)
RAW_CONFIG = dict(CFG, conf_skip=0)

SUF_LIGHT = ["ها", "های", "هایی", "ترین", "تر", "ان", "ات"]
PRE_LIGHT = ["می", "نمی"]
SUF = ["ها", "های", "هایی", "ی", "ایی", "ان", "ات", "ین", "تر", "ترین", "ک", "م", "ت", "ش",
       "ام", "اش", "مان", "تان", "شان", "ند", "ید", "یم", "ه", "ای"]
PRE = ["می", "نمی", "بی", "نا"]

_zipf: Optional[dict[str, float]] = None
_lock = threading.Lock()


def load() -> dict[str, float]:
    """Load the Persian frequency table (idempotent, thread-safe)."""
    global _zipf
    if _zipf is not None:
        return _zipf
    with _lock:
        if _zipf is None:
            from wordfreq import top_n_list, zipf_frequency

            table: dict[str, float] = {}
            for w in top_n_list("fa", 60000, wordlist="small"):
                w = base(w).strip()
                if w and " " not in w:
                    table[w] = max(table.get(w, 0), zipf_frequency(w, "fa"))
            _zipf = table
    return _zipf


def zipf(w: str) -> float:
    return load().get(w, 0.0)


def _gen1(w: str, sub_conf: float = 1.0, sub_other: float = 2.0, indel: float = 1.5) -> dict[str, float]:
    out: dict[str, float] = {}

    def put(c: str, cost: float) -> None:
        if c and (c not in out or out[c] > cost):
            out[c] = cost

    for i in range(len(w)):
        put(w[:i] + w[i + 1:], indel)  # deletion
        for ch in ALPHA:
            if ch != w[i]:
                put(w[:i] + ch + w[i + 1:], sub_conf if (w[i], ch) in CONF else sub_other)
    for i in range(len(w) + 1):
        for ch in ALPHA:
            put(w[:i] + ch + w[i:], indel)  # insertion
    return out


def candidates(w: str, max_cost: float, sub_other: float = 2.0, indel: float = 1.5) -> dict[str, float]:
    c1 = _gen1(w, sub_other=sub_other, indel=indel)
    res = {k: v for k, v in c1.items() if v <= max_cost}
    for k, v in c1.items():
        if v > max_cost - 1.0:
            continue
        for k2, v2 in _gen1(k, sub_other=sub_other, indel=indel).items():
            t = v + v2
            if t <= max_cost and (k2 not in res or res[k2] > t):
                res[k2] = t
    res.pop(w, None)
    return res


def is_known(w: str, target: float, mode: int = 1) -> bool:
    if zipf(w) >= target:
        return True
    pres, sufs, minstem = (PRE, SUF, 3) if mode == 1 else (PRE_LIGHT, SUF_LIGHT, 4)
    for pre in [""] + pres:
        if pre and not w.startswith(pre):
            continue
        for suf in [""] + sufs:
            if suf and not w.endswith(suf):
                continue
            stem = w[len(pre):len(w) - len(suf)] if suf else w[len(pre):]
            if len(stem) >= minstem and (pre or suf) and zipf(stem) >= target + 0.5:
                return True
    return False


@functools.lru_cache(maxsize=None)
def corr_word(
    w: str, alpha: float, margin: float, floor: float, max_cost: float, target: float,
    guard: int, sub_other: float, indel: float,
) -> str:
    if len(w) < 3:
        return w
    if guard and is_known(w, target, guard):
        return w
    if not guard and zipf(w) >= target:
        return w
    best, bs = w, zipf(w)
    for c, cost in candidates(w, max_cost, sub_other, indel).items():
        zc = zipf(c)
        if zc < floor:
            continue
        s = zc - alpha * cost
        if s > bs + margin:
            best, bs = c, s
    return best


_ZWNJ_HAK = re.compile("(?<=\u200c)هاک(?![ء-يٱ-ۓ])")


def fix_final_kaf(tok: str, known: float = 2.5, target: float = 3.0) -> str:
    """Final ``ک`` read for final ``ی`` (e.g. ``کشورک`` -> ``کشوری``), whatever Tesseract's confidence.

    Tesseract is confidently wrong on this pair, so the confidence gate of ``correct_tok`` lets it through.
    A run is changed only when it is not a known word and its ``ی`` form is a common one. ``‌هاک`` after a
    half-space is the plural suffix ``‌های``.
    """
    def sub(m: "re.Match[str]") -> str:
        r = m.group(0)
        if len(r) >= 3 and r.endswith("ک") and _ALPHA_ONLY.fullmatch(r):
            alt = r[:-1] + "ی"
            if zipf(r) < known and zipf(alt) >= target:
                return alt
        return r

    return _ZWNJ_HAK.sub("های", TOKEN.sub(sub, tok))


def correct_tok(
    tok: str, conf: float, alpha: float = 1.5, margin: float = 0.3, floor: float = 2.5,
    max_cost: float = 2.0, target: float = 2.5, guard: int = 1, conf_skip: float = 101,
    sub_other: float = 2.0, indel: float = 1.5,
) -> str:
    """Correct the Persian-letter runs of ``tok`` unless ``conf >= conf_skip``."""
    if conf >= conf_skip:
        return tok

    def sub(m: "re.Match[str]") -> str:
        w = m.group(0)
        wn = base(w)
        if wn != w or not _ALPHA_ONLY.fullmatch(wn):
            return w
        return corr_word(wn, alpha, margin, floor, max_cost, target, guard, sub_other, indel)

    return TOKEN.sub(sub, tok)
