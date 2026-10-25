"""Frozen contracts shared by the engine, ui, services and packaging branches.

Change only through a scaffold/merge task. Conventions:

- Confidences are Tesseract-style percentages, 0..100.
- Boxes are ``(left, top, right, bottom)`` in source-image pixels, or None.
- ``low_confidence_fraction`` is the share of words with confidence < 80, 0..1.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Literal, Optional, Protocol, Union

if TYPE_CHECKING:  # keep `import matnyab.api` light
    from PIL import Image

__all__ = [
    "Mode", "ModeUsed", "Stage", "Box", "ImageInput", "ProgressCallback",
    "OcrOptions", "WordResult", "LineResult", "OcrResult",
    "CancelToken", "Cancelled", "OcrEngine",
    "Theme", "DigitStyle", "ExportFormat", "AppSettings", "HistoryItem",
    "SettingsStore", "HistoryStore",
    "LOW_CONFIDENCE_THRESHOLD", "AUTO_MIN_WORDS", "AUTO_LOW_FRACTION",
]

# ---------------------------------------------------------------- engine ---

Mode = Literal["auto", "raw", "lex"]
ModeUsed = Literal["raw", "lex"]
Stage = Literal["preparing", "segmenting", "recognizing", "correcting", "done"]
Box = Optional[tuple[int, int, int, int]]
ImageInput = Union[str, "os.PathLike[str]", "Image.Image"]

# Auto-mode rule (from legacy/pipeline2.py choose_mode): "lex" when at least
# AUTO_LOW_FRACTION of the words have confidence < LOW_CONFIDENCE_THRESHOLD and
# there are at least AUTO_MIN_WORDS words, else "raw".
LOW_CONFIDENCE_THRESHOLD = 80
AUTO_MIN_WORDS = 20
AUTO_LOW_FRACTION = 0.10

# progress(fraction 0..1, stage)
ProgressCallback = Callable[[float, Stage], None]


@dataclass(frozen=True)
class OcrOptions:
    mode: Mode = "auto"
    keep_markers: bool = False  # keep citation markers instead of removing them
    workers: Optional[int] = None  # None = engine decides


@dataclass(frozen=True)
class WordResult:
    text: str
    confidence: float
    box: Box = None


@dataclass(frozen=True)
class LineResult:
    text: str
    confidence: float
    box: Box
    words: tuple[WordResult, ...]

    def __post_init__(self) -> None:
        if self.text != " ".join(w.text for w in self.words):
            raise ValueError("LineResult.text must equal ' '.join(word texts)")


@dataclass(frozen=True)
class OcrResult:
    text: str
    lines: tuple[LineResult, ...]
    mode_used: ModeUsed
    low_confidence_fraction: float
    elapsed_s: float
    image_size: tuple[int, int]  # (width, height) of the source image

    def __post_init__(self) -> None:
        if self.text != "\n".join(ln.text for ln in self.lines):
            raise ValueError("OcrResult.text must equal '\\n'.join(line texts)")


class Cancelled(Exception):
    """Raised by an engine when its CancelToken was cancelled."""


class CancelToken:
    """Thread-safe cancellation flag."""

    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise Cancelled()


class OcrEngine(Protocol):
    """Image in, OcrResult out.

    ``recognize`` is thread-safe for different engine instances, never touches
    the GUI, calls ``progress`` from the calling or a worker thread, and raises
    ``Cancelled`` if ``cancel`` fires.
    """

    def recognize(
        self,
        image: ImageInput,
        options: OcrOptions = OcrOptions(),
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[CancelToken] = None,
    ) -> OcrResult: ...

    def close(self) -> None: ...


# -------------------------------------------------------------- services ---

Theme = Literal["system", "light", "dark"]
DigitStyle = Literal["keep", "fa", "en"]
ExportFormat = Literal["txt", "docx"]


@dataclass
class AppSettings:
    theme: Theme = "system"
    mode: Mode = "auto"
    editor_font_pt: int = 14
    digit_style: DigitStyle = "keep"
    normalize_text: bool = True
    window_geometry: str = ""
    last_open_dir: str = ""
    last_save_dir: str = ""


@dataclass(frozen=True)
class HistoryItem:
    id: str
    source: str  # image file name or description
    created: str  # ISO 8601 timestamp
    text: str
    mode_used: ModeUsed
    confidence: float  # mean word confidence, 0..100


class SettingsStore(Protocol):
    def load(self) -> AppSettings: ...
    def save(self, settings: AppSettings) -> None: ...


class HistoryStore(Protocol):
    def add(self, item: HistoryItem) -> None: ...
    def list(self) -> list[HistoryItem]: ...  # newest first
    def delete(self, item_id: str) -> None: ...
    def clear(self) -> None: ...
