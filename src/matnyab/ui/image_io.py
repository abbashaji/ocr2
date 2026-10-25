"""Image loading helpers: probing, decoding to RGB, QImage conversion, thumbnails."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, Optional, Union

import numpy as np
from PIL import Image, ImageOps
from PySide6.QtCore import QMimeData, QUrl
from PySide6.QtGui import QImage

__all__ = [
    "SUPPORTED_EXTS", "MAX_MEGAPIXELS", "ImageLoadError", "is_supported", "probe_image",
    "load_image", "pil_to_qimage", "qimage_to_pil", "make_thumbnail", "expand_paths",
    "paths_from_mime", "natural_key",
]

SUPPORTED_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif")
MAX_MEGAPIXELS = 100  # warn above this size


class ImageLoadError(Exception):
    """The file is missing, unreadable or not an image."""

    def __init__(self, message: str, kind: str = "unreadable") -> None:
        super().__init__(message)
        self.kind = kind  # "unreadable" | "missing"


def is_supported(path: Union[str, "os.PathLike[str]"]) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTS


def natural_key(path: Path) -> list:
    import re

    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", path.name)]


def probe_image(path: Union[str, "os.PathLike[str]"]) -> tuple[int, int]:
    """Read only the header: returns ``(width, height)`` or raises ImageLoadError."""
    p = Path(path)
    if not p.is_file():
        raise ImageLoadError(f"not a file: {p}", kind="missing")
    try:
        with Image.open(p) as im:
            width, height = im.size
    except Exception as exc:  # Pillow raises many different error types
        raise ImageLoadError(f"{type(exc).__name__}: {exc}") from exc
    if width <= 0 or height <= 0:
        raise ImageLoadError("image has no pixels")
    return int(width), int(height)


def _to_rgb(im: Image.Image) -> Image.Image:
    mode = im.mode
    if mode == "RGB":
        return im
    if mode in ("RGBA", "LA", "PA") or (mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    if mode in ("I;16", "I;16L", "I;16B", "I"):
        arr = np.asarray(im).astype(np.float64)
        top = float(arr.max()) if arr.size else 1.0
        scale = 255.0 / (65535.0 if top > 255 else max(top, 1.0))
        return Image.fromarray(np.clip(arr * scale, 0, 255).astype(np.uint8)).convert("RGB")
    if mode == "F":
        arr = np.asarray(im).astype(np.float64)
        lo, hi = float(arr.min()), float(arr.max())
        span = (hi - lo) or 1.0
        return Image.fromarray(((arr - lo) / span * 255).astype(np.uint8)).convert("RGB")
    return im.convert("RGB")


def load_image(path: Union[str, "os.PathLike[str]"]) -> Image.Image:
    """Decode the first frame as an upright RGB image (EXIF rotation applied)."""
    p = Path(path)
    if not p.is_file():
        raise ImageLoadError(f"not a file: {p}", kind="missing")
    old_limit = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None  # the caller already asked the user about huge images
    try:
        with Image.open(p) as im:
            im.seek(0)
            im.load()
            upright = ImageOps.exif_transpose(im) or im
            return _to_rgb(upright).copy()
    except ImageLoadError:
        raise
    except Exception as exc:
        raise ImageLoadError(f"{type(exc).__name__}: {exc}") from exc
    finally:
        Image.MAX_IMAGE_PIXELS = old_limit


def pil_to_qimage(img: Image.Image) -> QImage:
    """Copy of ``img`` as a QImage that owns its pixels."""
    if img.mode != "RGB":
        img = _to_rgb(img)
    width, height = img.size
    data = img.tobytes("raw", "RGB")
    return QImage(data, width, height, width * 3, QImage.Format_RGB888).copy()


def qimage_to_pil(qimg: QImage) -> Image.Image:
    rgba = qimg.convertToFormat(QImage.Format_RGBA8888)
    width, height = rgba.width(), rgba.height()
    raw = bytes(rgba.constBits())
    stride = rgba.bytesPerLine()
    if stride != width * 4:
        raw = b"".join(raw[y * stride:y * stride + width * 4] for y in range(height))
    return _to_rgb(Image.frombytes("RGBA", (width, height), raw))


def make_thumbnail(
    source: Union[str, "os.PathLike[str]", Image.Image], size: int = 96
) -> QImage:
    """Square-bounded thumbnail as QImage (safe to call off the GUI thread)."""
    if isinstance(source, Image.Image):
        im = source.copy()
    else:
        old_limit = Image.MAX_IMAGE_PIXELS
        Image.MAX_IMAGE_PIXELS = None
        try:
            with Image.open(source) as opened:
                try:
                    opened.draft("RGB", (size * 2, size * 2))  # fast JPEG downscale
                except Exception:
                    pass
                opened.seek(0)
                im = ImageOps.exif_transpose(opened) or opened
                im = im.copy() if im is opened else im
        finally:
            Image.MAX_IMAGE_PIXELS = old_limit
    im = _to_rgb(im)
    im.thumbnail((size, size), Image.LANCZOS)
    return pil_to_qimage(im)


def expand_paths(items: Iterable[Union[str, "os.PathLike[str]"]]) -> list[Path]:
    """Files stay as given; folders are expanded (recursively) to supported images."""
    out: list[Path] = []
    for item in items:
        p = Path(item)
        if p.is_dir():
            found = [
                c for c in p.rglob("*")
                if c.is_file() and is_supported(c) and not c.name.startswith(".")
            ]
            out.extend(sorted(found, key=natural_key))
        else:
            out.append(p)
    return out


def paths_from_mime(mime: QMimeData) -> list[Path]:
    """Local file or folder paths carried by a drop or by the clipboard."""
    result: list[Path] = []
    if mime.hasUrls():
        for url in mime.urls():
            if isinstance(url, QUrl) and url.isLocalFile():
                result.append(Path(url.toLocalFile()))
    return result
