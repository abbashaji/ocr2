#!/usr/bin/env python3
"""
Offline Persian OCR benchmark.
- Synthetic test set: 4 fonts x 6 degradations x 8 text chunks (shared reference text).
- Split: chunks 0-1 = TUNE set (used to pick pipeline settings),
         chunks 4-6 = HELD-OUT set (numbers reported here were never used for tuning).
- Metrics: letter-level accuracy (CER), word accuracy, strict char accuracy.
Reference text is in ref.txt (a human transcription; see README caveats).
"""
import os, re, sys, random, subprocess, unicodedata, io, json, csv, itertools, shutil
from concurrent.futures import ProcessPoolExecutor
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from rapidfuzz.distance import Levenshtein as L

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = {'Vazirmatn': 'Vazirmatn.ttf', 'NotoNaskh': 'NotoNaskh.ttf',
         'NotoKufi': 'NotoKufi.ttf', 'DejaVu': 'DejaVu.ttf'}
DEGS = ['clean', 'lowres', 'jpeg', 'blur', 'noise', 'combined']
TESS_BEST = os.path.join(HERE, 'tess')   # contains fas.traineddata (tessdata_best)
os.environ['OMP_THREAD_LIMIT'] = '1'

# ---------- normalisation & metrics ----------
def base(s):
    s = s.replace('ي', 'ی').replace('ى', 'ی').replace('ك', 'ک').replace('ة', 'ه').replace('ۀ', 'ه').replace('\u200c', ' ')
    s = ''.join(c for c in s if not (0x064B <= ord(c) <= 0x065F))
    s = s.translate(str.maketrans('۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩', '01234567890123456789'))
    return re.sub(r'[\u200e\u200f]', '', s)
def letters(s): return ''.join(c for c in base(s) if unicodedata.category(c)[0] == 'L')
def words(s): return ''.join(c if unicodedata.category(c)[0] in 'LN' else ' ' for c in base(s)).split()
def strict(s): return re.sub(r'\s+', ' ', base(s)).strip()
def score(ref, hyp):
    lr, lh = letters(ref), letters(hyp)
    wr, wh = words(ref), words(hyp)
    sr, sh = strict(ref), strict(hyp)
    return dict(letter=1 - L.distance(lr, lh) / max(1, len(lr)),
                word=1 - L.distance(wr, wh) / max(1, len(wr)),
                strict=1 - L.distance(sr, sh) / max(1, len(sr)))

# ---------- test-set generation ----------
def chunks(ref):
    sents = [s.strip() for s in re.split(r'(?<=[.؛])\s+', ref.replace('\n', ' ')) if s.strip()]
    out, cur = [], ''
    for s in sents:
        cur = (cur + ' ' + s).strip()
        if len(cur) > 170:
            out.append(cur); cur = ''
    if cur: out.append(cur)
    return out[:8]

def render(text, fontfile, size=26, width=900, pad=24):
    font = ImageFont.truetype(os.path.join(HERE, 'fonts', fontfile), size, layout_engine=ImageFont.Layout.RAQM)
    lines, cur = [], ''
    for w in text.split():
        t = (cur + ' ' + w).strip()
        if font.getlength(t, direction='rtl', language='fa') > width - 2 * pad and cur:
            lines.append(cur); cur = w
        else: cur = t
    lines.append(cur)
    lh = int(size * 1.9)
    im = Image.new('L', (width, lh * len(lines) + 2 * pad), 255)
    d = ImageDraw.Draw(im)
    for i, ln in enumerate(lines):
        wpx = font.getlength(ln, direction='rtl', language='fa')
        d.text((width - pad - wpx, pad + i * lh), ln, font=font, fill=20, direction='rtl', language='fa')
    return im

def degrade(im, kind, seed):
    rng = np.random.default_rng(seed)
    def noise(img, s):
        a = np.asarray(img, dtype=np.float32) + rng.normal(0, s, img.size[::-1])
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))
    def jpeg(img, q):
        b = io.BytesIO(); img.save(b, 'JPEG', quality=q); return Image.open(io.BytesIO(b.getvalue())).convert('L')
    if kind == 'clean': return im
    if kind == 'lowres':
        return im.resize((im.width * 6 // 10, im.height * 6 // 10), Image.BILINEAR)
    if kind == 'jpeg': return jpeg(im, 20)
    if kind == 'blur': return im.filter(ImageFilter.GaussianBlur(1.3))
    if kind == 'noise': return noise(im, 22)
    if kind == 'combined':
        im = im.resize((im.width * 7 // 10, im.height * 7 // 10), Image.BILINEAR)
        im = im.filter(ImageFilter.GaussianBlur(0.9))
        im = noise(im, 14)
        im = im.rotate(1.5, resample=Image.BICUBIC, fillcolor=255)
        return jpeg(im, 30)
    raise ValueError(kind)

# ---------- OCR pipelines ----------
def tess(path, tessdata=None, psm=6):
    cmd = ['tesseract', path, '-', '-l', 'fas', '--psm', str(psm)]
    if tessdata: cmd += ['--tessdata-dir', tessdata]
    return subprocess.run(cmd, capture_output=True, text=True).stdout

def prep(im, scale, sharpen, median):
    if median: im = im.filter(ImageFilter.MedianFilter(3))
    if scale != 1:
        im = im.resize((int(im.width * scale), int(im.height * scale)), Image.LANCZOS)
    if sharpen: im = im.filter(ImageFilter.UnsharpMask(2, 120, 2))
    return im

CANDIDATES = {   # name -> (tessdata, scale, sharpen, median, psm)
    'baseline_std':        (None,      1, False, False, 6),
    'best_raw':            (TESS_BEST, 1, False, False, 6),
    'best_2x_sharp':       (TESS_BEST, 2, True,  False, 6),
    'best_2x_sharp_med':   (TESS_BEST, 2, True,  True,  6),
}

def job(args):
    key, imgpath, ref, cand = args
    td, sc, sh, me, psm = CANDIDATES[cand]
    im = Image.open(imgpath).convert('L')
    tmp = f'/tmp/b_{os.getpid()}.png'
    prep(im, sc, sh, me).save(tmp)
    hyp = tess(tmp, td, psm)
    return key, cand, score(ref, hyp), hyp

def main():
    ref = open(os.path.join(HERE, 'ref.txt'), encoding='utf-8').read()
    ch = chunks(ref)
    os.makedirs(os.path.join(HERE, 'testset'), exist_ok=True)
    items = []
    for ci, text in enumerate(ch):
        for fn, ff in FONTS.items():
            base_im = render(text, ff)
            for dg in DEGS:
                p = os.path.join(HERE, 'testset', f'{fn}_{dg}_c{ci}.png')
                degrade(base_im, dg, seed=ci * 100 + hash(dg) % 97).save(p)
                items.append(dict(path=p, ref=text, font=fn, deg=dg, chunk=ci,
                                  split='tune' if ci < 2 else ('heldout' if 4 <= ci <= 6 else 'skip')))
    items=[i for i in items if i['split']!='skip']
    print(f'{len(items)} images ({sum(i["split"]=="tune" for i in items)} tune / {sum(i["split"]=="heldout" for i in items)} held-out)')

    # 1) tuning on TUNE split only
    jobs = [((i, c), it['path'], it['ref'], c) for i, it in enumerate(items) if it['split'] == 'tune' for c in CANDIDATES]
    res = {}
    with ProcessPoolExecutor(1) as ex:
        for key, c, s, _ in ex.map(job, jobs):
            res[key] = s
    tune_mean = {c: np.mean([res[(i, c)]['letter'] for i, it in enumerate(items) if it['split'] == 'tune']) for c in CANDIDATES}
    chosen = max(tune_mean, key=tune_mean.get)
    print('TUNE letter-acc:', {k: round(100 * v, 2) for k, v in tune_mean.items()}, '\nCHOSEN:', chosen)

    # 2) held-out: baseline vs chosen only
    jobs = [((i, c), it['path'], it['ref'], c) for i, it in enumerate(items) if it['split'] == 'heldout' for c in ('baseline_std', chosen)]
    rows = []
    with ProcessPoolExecutor(1) as ex:
        for key, c, s, _ in ex.map(job, jobs):
            it = items[key[0]]
            rows.append(dict(cand=c, font=it['font'], deg=it['deg'], chunk=it['chunk'], **s))
    with open(os.path.join(HERE, 'results_heldout.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    json.dump(dict(chosen=chosen, tune_letter_acc=tune_mean), open(os.path.join(HERE, 'tuning.json'), 'w'), indent=1)

    def agg(sel, m): return 100 * np.mean([r[m] for r in sel])
    print('\nHELD-OUT (n per candidate = %d)' % (len(rows) // 2))
    for c in ('baseline_std', chosen):
        sel = [r for r in rows if r['cand'] == c]
        print(f'{c:20s} letter={agg(sel,"letter"):.2f}  word={agg(sel,"word"):.2f}  strict={agg(sel,"strict"):.2f}')
    print('\nBy degradation (letter acc, baseline -> chosen):')
    for dg in DEGS:
        b = [r for r in rows if r['cand'] == 'baseline_std' and r['deg'] == dg]
        t = [r for r in rows if r['cand'] == chosen and r['deg'] == dg]
        print(f'{dg:9s} {agg(b,"letter"):.2f} -> {agg(t,"letter"):.2f}   (word {agg(b,"word"):.1f} -> {agg(t,"word"):.1f})')
    print('\nBy font (letter acc, baseline -> chosen):')
    for fn in FONTS:
        b = [r for r in rows if r['cand'] == 'baseline_std' and r['font'] == fn]
        t = [r for r in rows if r['cand'] == chosen and r['font'] == fn]
        print(f'{fn:10s} {agg(b,"letter"):.2f} -> {agg(t,"letter"):.2f}')

if __name__ == '__main__':
    main()
