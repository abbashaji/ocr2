"""v2: keeps per-word confidence; guarded lexicon correction."""
import re, functools
from rapidfuzz.distance import Levenshtein as Lev
from lines import *
import postproc as P
import markers as M

TARGETS = (28, 32, 36, 40, 44, 48, 56)
norm = lambda s: ' '.join(B.base(s).split())

def recognize_tok(im, targets=TARGETS, markers=True):
    """-> list of lines; each line = list of (token, conf) from the medoid scale.
    markers=True removes superscript citation markers like [۱۱] geometrically (markers.py, from Tesseract character boxes)
    BEFORE the medoid is chosen; markers=False keeps the old TSV path (no marker handling)."""
    g = to_gray(im, 'L'); out = []
    for c in crops(g, segment_lines(g)):
        if markers:
            cands = []
            for T in targets:
                words = tess_chars(pad_white(scale(c, T / c.height), 12), 7)
                toks = M.clean_words_conf(words)
                cands.append((' '.join(t for t, _ in toks), toks))
        else:
            cands = [tess_tsv(pad_white(scale(c, T / c.height), 12), 7) for T in targets]
        n = [norm(t) for t, _ in cands]
        best = min(range(len(n)), key=lambda i: sum(Lev.distance(n[i], n[j]) for j in range(len(n))))
        out.append(cands[best][1])
    return out

LET = r'ء-يٱ-ۓ'
def finalize_tok(t):
    t = re.sub(r'(?<=[' + LET + r'])ء(?=[^' + LET + r']*$)', '،', t)     # glued "ء" at word end -> comma
    t = re.sub(r'(?<=[' + LET + r']),', '،', t)
    return t.replace('?', '؟')

SUF_LIGHT = ['ها', 'های', 'هایی', 'ترین', 'تر', 'ان', 'ات']; PRE_LIGHT = ['می', 'نمی']
SUF = ['ها', 'های', 'هایی', 'ی', 'ایی', 'ان', 'ات', 'ین', 'تر', 'ترین', 'ک', 'م', 'ت', 'ش', 'ام', 'اش', 'مان', 'تان', 'شان', 'ند', 'ید', 'یم', 'ه', 'ای']
PRE = ['می', 'نمی', 'بی', 'نا']
def is_known(w, target, mode=1):
    if P.zipf(w) >= target: return True
    pres, sufs, minstem = (PRE, SUF, 3) if mode == 1 else (PRE_LIGHT, SUF_LIGHT, 4)
    for pre in [''] + pres:
        if pre and not w.startswith(pre): continue
        for suf in [''] + sufs:
            if suf and not w.endswith(suf): continue
            stem = w[len(pre):len(w) - len(suf)] if suf else w[len(pre):]
            if len(stem) >= minstem and (pre or suf) and P.zipf(stem) >= target + 0.5: return True
    return False

@functools.lru_cache(maxsize=None)
def corr_word(w, alpha, margin, floor, max_cost, target, guard, sub_other, indel):
    if len(w) < 3: return w
    if guard and is_known(w, target, guard): return w
    if not guard and P.zipf(w) >= target: return w
    best, bs = w, P.zipf(w)
    for c, cost in P.candidates(w, max_cost, sub_other, indel).items():
        zc = P.zipf(c)
        if zc < floor: continue
        s = zc - alpha * cost
        if s > bs + margin: best, bs = c, s
    return best

def correct_tok(tok, conf, alpha=1.5, margin=0.3, floor=2.5, max_cost=2.0, target=2.5, guard=1, conf_skip=101, sub_other=2.0, indel=1.5):
    if conf >= conf_skip: return tok
    def sub(m):
        w = m.group(0); wn = B.base(w)
        if wn != w or not re.fullmatch('[' + P.ALPHA + ']+', wn): return w
        return corr_word(wn, alpha, margin, floor, max_cost, target, guard, sub_other, indel)
    return P.TOKEN.sub(sub, tok)

D = '0-9۰-۹'
def restore_placeholders(t):
    """fine-tune trains ، ٬ ٫ ٪ onto the existing classes , , . # (see ft/common.py LABEL_MAP); restore by context."""
    t = re.sub(r'(?<=[' + D + r'])\.(?=[' + D + r'])', '٫', t)                 # 1.64 -> ۱٫۶۴
    t = re.sub(r'(?<=[' + D + r']),(?=[' + D + r']{3}(?![' + D + r']))', '٬', t)  # 12,345 -> thousands separator
    t = t.replace(',', '،')
    return t.replace('#', '٪')

AUTO_LOW_CONF, AUTO_LOWFRAC, AUTO_MIN_WORDS = 80, 0.10, 20
def choose_mode(lines):
    """'lex' or 'raw' from the image itself. Share of words Tesseract is unsure about (word conf < 80): about 0.06 on clean zoom-100 screenshots,
    0.08 at zoom 90, 0.12 at zoom 75 / JPEG, 0.18 for the client's low-quality sample, 0.20 at zoom 67. The lexicon step costs about 0.5 points on clean
    text and gains 0.3 to 4.5 points on low-quality text, so it is used from 0.10 up. Fewer than 20 words: too few to judge, use raw.
    Calibrated on a small local fixture (client samples + Chromium renderings at 4 zooms), NOT on the Actions test set."""
    cf = [c for ln in lines for _, c in ln]
    if len(cf) < AUTO_MIN_WORDS: return 'raw'
    return 'lex' if sum(c < AUTO_LOW_CONF for c in cf) / len(cf) >= AUTO_LOWFRAC else 'raw'

def render(lines, **cfg):
    out = []
    for ln in lines:
        out.append(restore_placeholders(' '.join(correct_tok(finalize_tok(t), c, **cfg) for t, c in ln)))
    return '\n'.join(out)
