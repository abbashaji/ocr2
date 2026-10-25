"""Input handling: any PIL image/path -> upright, dark-on-light RGB image plus its grey version."""

from __future__ import annotations

import os
from typing import Union

import numpy as np
from PIL import Image, ImageOps

from .segment import ink_mask

__all__ = ["load_image", "to_gray", "is_blank", "is_light_on_dark", "prepare"]

BORDER_FRACTION = 0.03     # width of the border band, relative to the shorter side
DARK_BORDER_MEDIAN = 110   # median grey of the border band below this ...
INK_FRACTION = 0.5         # ... and Otsu foreground (dark) fraction above this -> invert
BLANK_RANGE = 16           # grey range (max - min) below this: nothing to read


def load_image(src: Union[str, "os.PathLike[str]", Image.Image]) -> Image.Image:
    """Open (if a path), apply the EXIF orientation and return a fully loaded image."""
    if isinstance(src, Image.Image):
        im = src
    else:
        with Image.open(src) as opened:
            opened.load()
            im = opened.copy()
    return ImageOps.exif_transpose(im)


def _to_rgb(im: Image.Image) -> Image.Image:
    mode = im.mode
    if mode == "P":
        im = im.convert("RGBA" if "transparency" in im.info else "RGB")
        mode = im.mode
    if mode in ("RGBA", "LA", "PA"):  # composite on white
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    if mode == "I" or mode.startswith("I;") or mode == "F":
        a = np.asarray(im).astype(np.float64)
        top = float(a.max()) if a.size else 0.0
        if top > 255.0:  # genuine 16-bit data; values up to 255 are taken as 8-bit
            a = a / 257.0
        return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "L").convert("RGB")
    return im.convert("RGB")


def to_gray(rgb: Image.Image) -> Image.Image:
    """BT.601 luma, truncated to uint8 (identical to ``legacy/lib.py:to_gray(im, 'L')``)."""
    a = np.asarray(rgb.convert("RGB")).astype(np.float32)
    g = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    return Image.fromarray(np.clip(g, 0, 255).astype(np.uint8))


def is_blank(gray: Image.Image) -> bool:
    """True for an empty image or one with (almost) no contrast."""
    a = np.asarray(gray)
    return a.size == 0 or int(a.max()) - int(a.min()) < BLANK_RANGE


def is_light_on_dark(gray: Image.Image) -> bool:
    """True for dark-mode style images: dark border band and most pixels below Otsu."""
    a = np.asarray(gray)
    if a.size == 0:
        return False
    h, w = a.shape
    b = max(2, int(round(BORDER_FRACTION * min(h, w))))
    b = min(b, max(1, min(h, w) // 2))
    mask = np.ones((h, w), dtype=bool)
    mask[b:h - b, b:w - b] = False
    if float(np.median(a[mask])) >= DARK_BORDER_MEDIAN:
        return False
    return float(ink_mask(a).mean()) > INK_FRACTION


def prepare(
    src: Union[str, "os.PathLike[str]", Image.Image],
) -> tuple[Image.Image, tuple[int, int]]:
    """-> (grey image in dark-on-light polarity, (width, height) after EXIF rotation)."""
    im = load_image(src)
    size = im.size
    rgb = _to_rgb(im)
    gray = to_gray(rgb)
    if is_light_on_dark(gray):
        gray = to_gray(ImageOps.invert(rgb))
    return gray, size
