import numpy as np
from PIL import Image
from lib import *
from bench2 import otsu

SEG_THR = 0.015
def segment_lines(gray, min_h=6, thr_frac=None):
    a = np.asarray(gray); ink = a < otsu(a)
    prof = ink.sum(1).astype(float)
    k = np.ones(3) / 3; prof = np.convolve(prof, k, mode='same')
    thr = (thr_frac if thr_frac is not None else SEG_THR) * prof.max()
    rows = prof > thr
    bands, start = [], None
    for y, v in enumerate(rows):
        if v and start is None: start = y
        if not v and start is not None:
            if y - start >= min_h: bands.append([start, y])
            start = None
    if start is not None and len(rows) - start >= min_h: bands.append([start, len(rows)])
    return bands

CROP_PAD = 5
def crops(gray, bands, pad=None):
    pad = CROP_PAD if pad is None else pad
    out = []
    for y0, y1 in bands:
        c = gray.crop((0, max(0, y0 - pad), gray.width, min(gray.height, y1 + pad)))
        out.append(c)
    return out

def pad_white(im, p):
    w = Image.new('L', (im.width + 2 * p, im.height + 2 * p), 255); w.paste(im, (p, p)); return w
