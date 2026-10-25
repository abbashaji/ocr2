"""Plain data model of the processing queue (no widgets)."""

from __future__ import annotations

import enum
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtGui import QImage

from matnyab.api import LOW_CONFIDENCE_THRESHOLD, Mode, OcrResult

__all__ = ["ItemState", "QueueItem", "mean_confidence", "uncertain_level", "CONF_HIGH", "CONF_MID"]

_ids = itertools.count(1)
POOR_CONFIDENCE = 60.0
CONF_HIGH, CONF_MID = 85.0, 75.0  # label bands for the mean word confidence (no % is shown)


class ItemState(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"


def mean_confidence(result: OcrResult) -> float:
    confs = [w.confidence for ln in result.lines for w in ln.words]
    return sum(confs) / len(confs) if confs else 0.0


def uncertain_level(confidence: float) -> int:
    """0 = fine, 1 = uncertain (< 80), 2 = poor (< 60)."""
    if confidence < POOR_CONFIDENCE:
        return 2
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return 1
    return 0


@dataclass(eq=False)
class QueueItem:
    name: str
    path: Optional[Path] = None
    image: Optional[Image.Image] = None  # pasted / dropped image data (no file)
    id: str = field(default_factory=lambda: f"item{next(_ids)}")
    size: Optional[tuple[int, int]] = None
    state: ItemState = ItemState.QUEUED
    submitted: bool = False
    progress: float = 0.0
    stage: str = ""
    result: Optional[OcrResult] = None
    text: Optional[str] = None  # edited editor text (None = untouched)
    ranges: Optional[list] = None  # saved word ranges that match ``text``
    error_kind: str = ""
    error_message: str = ""
    error_detail: str = ""
    thumb: Optional[QImage] = None
    mode_override: Optional[Mode] = None
    from_history: bool = False
    history_text: str = ""
    history_mode: str = "raw"
    confidence: float = 0.0

    @property
    def megapixels(self) -> float:
        return (self.size[0] * self.size[1]) / 1_000_000 if self.size else 0.0

    @property
    def has_image(self) -> bool:
        return self.image is not None or self.path is not None

    @property
    def is_modified(self) -> bool:
        return self.result is not None and self.text is not None and self.text != self.result.text
