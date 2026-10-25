#!/usr/bin/env python3
"""Accuracy vs text size, and an adaptive auto-scale preprocessing step.
Tuned on chunks 0-1; reported on chunks 4-5 (held-out) and on the client's two sample images."""
import os, io, subprocess, json, csv
import numpy as np
from PIL import Image, ImageFilter
import bench as B

SIZES = [12, 14, 18, 26, 36]
FONTS = ['Vazirmatn', 'NotoNaskh', 'NotoKufi', 'DejaVu']
os.environ['OMP_THREAD_LIMIT'] = '1'

def otsu(a):
    h, _ = np.histogram(a, bins=256, range=(0, 256)); tot = a.size
    sum_all = np.dot(np.arange(256), h); wb = sb = 0; best = (0, 128)
    for t in range(256):
        wb += h[t]
        if wb == 0 or wb == tot: continue
        sb += t * h[t]; mb = sb / wb; mf = (sum_all - sb) / (tot - wb)
        v = wb * (tot - wb) * (mb - mf) ** 2
        if v > best[0]: best = (v, t)
    return best[1]

def line_height(im):
    a = np.asarray(im.convert('L')); ink = a < otsu(a)
    prof = ink.sum(1) > max(2, 0.004 * a.shape[1])
    runs, n = [], 0
    for v in prof:
        if v: n += 1
        elif n: runs.append(n); n = 0
    if n: runs.append(n)
    runs = [r for r in runs if r >= 4]
    return float(np.median(runs)) if runs else None

def auto(im, target):
    h = line_height(im)
    s = 1.0 if not h else float(np.clip(target / h, 0.5, 4.0))
    if abs(s - 1) > 0.08:
        im = im.convert('L').resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    return im

def ocr(im, td):
    p = f'/tmp/b2_{os.getpid()}.png'; im.convert('L').save(p)
    return B.tess(p, td, 6)

def pipeline(name, im):
    if name == 'baseline_std': return ocr(im, None)
    if name == 'best_raw':     return ocr(im, B.TESS_BEST)
    if name == 'best_2x':      return ocr(B.prep(im.convert('L'), 2, True, False), B.TESS_BEST)
    if name.startswith('auto'): return ocr(auto(im, int(name.split('_')[1])), B.TESS_BEST)
    raise ValueError(name)

def jpeg(im, q):
    b = io.BytesIO(); im.save(b, 'JPEG', quality=q); return Image.open(io.BytesIO(b.getvalue())).convert('L')

def make_items(chunk_ids, ch):
    items = []
    for ci in chunk_ids:
        for fn in FONTS:
            for sz in SIZES:
                im = B.render(ch[ci], B.FONTS[fn], size=sz)
                items.append(dict(font=fn, size=sz, chunk=ci, deg='clean', img=im, ref=ch[ci]))
                items.append(dict(font=fn, size=sz, chunk=ci, deg='jpeg30', img=jpeg(im, 30), ref=ch[ci]))
    return items

def evaluate(items, names):
    rows = []
    for it in items:
        for n in names:
            s = B.score(it['ref'], pipeline(n, it['img']))
            rows.append(dict(cand=n, font=it['font'], size=it['size'], deg=it['deg'], chunk=it['chunk'], **s))
    return rows

def mean(rows, key='letter', **flt):
    sel = [r for r in rows if all(r[k] == v for k, v in flt.items())]
    return 100 * np.mean([r[key] for r in sel])

if __name__ == '__main__':
    ref = open(os.path.join(B.HERE, 'ref.txt'), encoding='utf-8').read()
    ch = B.chunks(ref)
    cands = ['baseline_std', 'best_raw', 'best_2x', 'auto_35', 'auto_50', 'auto_65']
    tune = evaluate(make_items([0, 1], ch), cands)
    tm = {c: mean(tune, cand=c) for c in cands}
    print('TUNE letter-acc:', {k: round(v, 2) for k, v in tm.items()})
    chosen = max([c for c in cands if c.startswith('auto')], key=tm.get)
    print('CHOSEN auto target:', chosen)

    held = evaluate(make_items([4, 5], ch), ['baseline_std', 'best_raw', 'best_2x', chosen])
    with open(os.path.join(B.HERE, 'results_size_heldout.csv'), 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(held[0].keys())); w.writeheader(); w.writerows(held)

    print('\nHELD-OUT letter accuracy by font size (px):')
    print('size  ' + '  '.join(f'{c:>12s}' for c in ['baseline_std', 'best_raw', 'best_2x', chosen]))
    for sz in SIZES:
        print(f'{sz:>4}  ' + '  '.join(f'{mean(held, cand=c, size=sz):12.2f}' for c in ['baseline_std', 'best_raw', 'best_2x', chosen]))
    print('ALL   ' + '  '.join(f'{mean(held, cand=c):12.2f}' for c in ['baseline_std', 'best_raw', 'best_2x', chosen]))
    print('\nHELD-OUT word accuracy (all sizes):', {c: round(mean(held, "word", cand=c), 2) for c in ['baseline_std', 'best_raw', 'best_2x', chosen]})

    # the client's two real samples
    up = '/mnt/user-data/uploads/'
    samples = {'client_clean': 'P4vLQhumAEgQBDhZNMmn68WWQS0alblnqt6hj581.png', 'client_low': 'sAikXA7l7MlZDcY3A6maqY68vjCo76RN24J0Xwag.jpg'}
    print('\nCLIENT SAMPLES (line-height px, then letter / word acc):')
    for k, f in samples.items():
        im = Image.open(up + f).convert('L')
        print(k, 'line_h=', line_height(im))
        for c in ['baseline_std', 'best_raw', 'best_2x', chosen]:
            s = B.score(ref, pipeline(c, im))
            print(f'   {c:13s} letter={100*s["letter"]:.2f} word={100*s["word"]:.2f}')
    json.dump(dict(chosen=chosen, tune=tm), open(os.path.join(B.HERE, 'tuning2.json'), 'w'), indent=1)
