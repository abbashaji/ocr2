"""Geometric removal of Wikipedia-style superscript citation markers ([۱۱]) using Tesseract character boxes.

Markers are small raised digits in brackets glued to the previous word, so the OCR engine returns them inside the same
word ("اصفهان[۲۴۶1]"). They are not in the ground truth, and regexes cannot remove them once the digits/brackets are
misread. Instead we flag characters whose box bottom sits clearly above the line's baseline.

Tuned on 36 Chromium screenshots (zoom 100/75/50%): final z100 word accuracy 92.6 -> 96.5 with this step alone.
Known limits: marker residue misread as letters (e.g. a leading "ا") is not removed; very low resolution boxes are noisy.
"""
import numpy as np

SUP_CHARS = set('0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩[]()')
PUNCT = set('.,،:؛;!؟?')
ZERO = set('۰٠0')          # the Persian zero is a tiny dot: by size alone it looks like a superscript


def _flags(words, frac_h=0.8, frac_up=0.3):
    """words: list of words, each a list of (ch, x0, y0, x1, y1, char_conf[, word_conf]). Returns a parallel list of bool lists (True = marker)."""
    chars = [c for w in words for c in w]
    base = [c for c in chars if c[0] not in SUP_CHARS and c[0] not in PUNCT]
    if len(base) < 4:                       # too little text to estimate the baseline
        return [[False] * len(w) for w in words]
    H = float(np.median([c[4] - c[2] for c in base]))
    bot = float(np.median([c[4] for c in base]))
    raised = lambda c: c[4] <= bot - frac_up * H
    out = []
    for w in words:
        n = len(w)
        flag = [(c[0] in SUP_CHARS and c[0] not in ZERO and raised(c)
                 and ((c[4] - c[2]) <= frac_h * H or c[4] <= bot - 0.4 * H)) for c in w]
        changed = True
        while changed:                      # absorb brackets and zeros that touch a flagged run
            changed = False
            for i in range(n):
                if flag[i] or not (w[i][0] in '[]()' or w[i][0] in ZERO):
                    continue
                touches = (i > 0 and flag[i - 1]) or (i + 1 < n and flag[i + 1])
                if touches and (w[i][0] not in ZERO or raised(w[i])):
                    flag[i] = True; changed = True
        out.append(flag)
    return out


def clean_words(words, frac_h=0.8, frac_up=0.3):
    """-> list of token strings with marker characters removed (empty words dropped)."""
    toks = []
    for w, flag in zip(words, _flags(words, frac_h, frac_up)):
        t = ''.join(c[0] for c, f in zip(w, flag) if not f)
        if t: toks.append(t)
    return toks


def clean_words_conf(words, frac_h=0.8, frac_up=0.3):
    """-> [(token, word_conf)] (Tesseract's word confidence) so the lexicon corrector can skip confident words."""
    out = []
    for w, flag in zip(words, _flags(words, frac_h, frac_up)):
        cs = [c for c, f in zip(w, flag) if not f]
        if cs:
            out.append((''.join(c[0] for c in cs), float(cs[0][6]) if len(cs[0]) > 6 else float(np.mean([c[5] for c in cs]))))
    return out
