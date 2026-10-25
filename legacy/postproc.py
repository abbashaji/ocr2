import re, itertools, difflib
from wordfreq import top_n_list, zipf_frequency
import bench as B

ALPHA = 'ابپتثجچحخدذرزژسشصضطظعغفقکگلمنوهیءآأؤئ'
GROUPS = ['نتبپثی', 'جچحخ', 'دذ', 'رزژو', 'سش', 'صض', 'طظ', 'عغ', 'فق', 'کگ', 'اآأ', 'هة', 'یئ', 'لا', 'کی', 'مه', 'ه ح', 'وؤ', 'خح']
CONF = set()
for g in GROUPS:
    for a, b in itertools.permutations(g.replace(' ', ''), 2): CONF.add((a, b))

_zipf = {}
for w in top_n_list('fa', 60000, wordlist='small'):
    w = B.base(w).strip()
    if w and ' ' not in w: _zipf[w] = max(_zipf.get(w, 0), zipf_frequency(w, 'fa'))
def zipf(w): return _zipf.get(w, 0.0)

def gen1(w, sub_conf=1.0, sub_other=2.0, indel=1.5):
    out = {}
    def put(c, cost):
        if c and (c not in out or out[c] > cost): out[c] = cost
    for i in range(len(w)):
        put(w[:i] + w[i+1:], indel)                                   # deletion
        for ch in ALPHA:
            if ch != w[i]: put(w[:i] + ch + w[i+1:], sub_conf if (w[i], ch) in CONF else sub_other)
    for i in range(len(w) + 1):
        for ch in ALPHA: put(w[:i] + ch + w[i:], indel)                 # insertion
    return out

def candidates(w, max_cost, sub_other=2.0, indel=1.5):
    c1 = gen1(w, sub_other=sub_other, indel=indel); res = {k: v for k, v in c1.items() if v <= max_cost}
    for k, v in c1.items():
        if v > max_cost - 1.0: continue
        for k2, v2 in gen1(k, sub_other=sub_other, indel=indel).items():
            t = v + v2
            if t <= max_cost and (k2 not in res or res[k2] > t): res[k2] = t
    res.pop(w, None); return res

def correct_word(w, alpha, margin, floor, max_cost, target_zipf):
    z = zipf(w)
    if z >= target_zipf or len(w) < 3: return w
    best, bs = w, z                      # score of keeping w
    for c, cost in candidates(w, max_cost).items():
        zc = zipf(c)
        if zc < floor: continue
        s = zc - alpha * cost
        if s > bs + margin: best, bs = c, s
    return best

TOKEN = re.compile(r'[ء-يٱ-ۓ]+')
def correct_text(text, alpha=1.0, margin=0.5, floor=3.0, max_cost=2.0, target_zipf=2.5):
    def sub(m):
        w = m.group(0); wn = B.base(w)
        if wn != w or not re.fullmatch('[' + ALPHA + ']+', wn): return w
        return correct_word(wn, alpha, margin, floor, max_cost, target_zipf)
    return TOKEN.sub(sub, text)

def para_errors(ref_paras, hyp):
    """errors attributed to the ref paragraph they fall in -> (errs_p1, errs_p2, n1, n2)"""
    rw = [B.words(p) for p in ref_paras]; flat = [w for p in rw for w in p]; hw = B.words(hyp)
    bounds = [len(rw[0])]
    sm = difflib.SequenceMatcher(None, flat, hw, autojunk=False); e = [0, 0]
    for t, i1, i2, j1, j2 in sm.get_opcodes():
        if t == 'equal': continue
        n = max(i2 - i1, j2 - j1)
        if t == 'insert': e[0 if i1 < bounds[0] else 1] += n
        else:
            for i in range(i1, i2): e[0 if i < bounds[0] else 1] += 1
            if j2 - j1 > i2 - i1: e[0 if i1 < bounds[0] else 1] += (j2 - j1) - (i2 - i1)
    return e[0], e[1], len(rw[0]), len(rw[1])
