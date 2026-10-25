"""Line segmentation and per-line image helpers (port of ``legacy/lines.py``)."""

from __future__ import annotations

from typing import Optional

import numpy as np
from PIL import Image

__all__ = ["SEG_THR", "CROP_PAD", "otsu", "ink_mask", "segment_lines", "crops", "scale", "pad_white"]

SEG_THR = 0.015
CROP_PAD = 5


def otsu(a: np.ndarray) -> int:
    """Otsu threshold of a uint8 array (same tie-breaking as the legacy loop)."""
    h, _ = np.histogram(a, bins=256, range=(0, 256))
    tot = a.size
    sum_all = np.dot(np.arange(256), h)
    wb = sb = 0
    best: tuple[float, int] = (0, 128)
    for t in range(256):
        wb += h[t]
        if wb == 0 or wb == tot:
            continue
        sb += t * h[t]
        mb = sb / wb
        mf = (sum_all - sb) / (tot - wb)
        v = wb * (tot - wb) * (mb - mf) ** 2
        if v > best[0]:
            best = (v, t)
    return best[1]


def ink_mask(a: np.ndarray) -> np.ndarray:
    """Boolean mask of ink (pixels below the Otsu threshold).

    Identical to the legacy ``a < otsu(a)``, except for images with only two grey levels
    (pure black and white), where Otsu returns the lower level and nothing would count as
    ink; there the midpoint is used.
    """
    ink = a < otsu(a)
    if not ink.any() and a.size and int(a.max()) > int(a.min()):
        ink = a < (int(a.min()) + int(a.max())) / 2
    return ink


def segment_lines(
    gray: Image.Image, min_h: int = 6, thr_frac: Optional[float] = None
) -> list[tuple[int, int]]:
    """Row bands ``(y0, y1)`` that contain ink, from the horizontal ink profile."""
    a = np.asarray(gray)
    ink = ink_mask(a)
    prof = ink.sum(1).astype(float)
    prof = np.convolve(prof, np.ones(3) / 3, mode="same")
    thr = (thr_frac if thr_frac is not None else SEG_THR) * prof.max()
    rows = prof > thr
    bands: list[tuple[int, int]] = []
    start: Optional[int] = None
    for y, v in enumerate(rows):
        if v and start is None:
            start = y
        if not v and start is not None:
            if y - start >= min_h:
                bands.append((start, y))
            start = None
    if start is not None and len(rows) - start >= min_h:
        bands.append((start, len(rows)))
    return bands


def crops(
    gray: Image.Image, bands: list[tuple[int, int]], pad: Optional[int] = None
) -> list[tuple[Image.Image, int]]:
    """Full-width crops around each band, with the crop's top offset in the source."""
    pad = CROP_PAD if pad is None else pad
    out: list[tuple[Image.Image, int]] = []
    for y0, y1 in bands:
        top = max(0, y0 - pad)
        out.append((gray.crop((0, top, gray.width, min(gray.height, y1 + pad))), top))
    return out


def scale(im: Image.Image, s: float) -> Image.Image:
    return im if s == 1 else im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def pad_white(im: Image.Image, p: int) -> Image.Image:
    w = Image.new("L", (im.width + 2 * p, im.height + 2 * p), 255)
    w.paste(im, (p, p))
    return w
