"""Stub engine: fixed 3-line Persian result, reports every stage, honours cancel."""

from __future__ import annotations

import os
import time
from typing import Optional

from matnyab.api import (
    LOW_CONFIDENCE_THRESHOLD, CancelToken, ImageInput, LineResult, OcrOptions,
    OcrResult, ProgressCallback, WordResult,
)

# (word, confidence) per line, written right-to-left.
_LINES = (
    (("این", 96.0), ("یک", 94.5), ("متن", 91.0), ("آزمایشی", 72.5), ("است", 97.0)),
    (("برای", 95.0), ("بررسی", 88.0), ("رابط", 66.0), ("کاربری", 90.5)),
    (("متن‌یاب", 78.0), ("نسخه", 93.0), ("اولیه", 89.0)),
)
_STAGES = (
    (0.05, "preparing"), (0.25, "segmenting"), (0.60, "recognizing"),
    (0.90, "correcting"), (1.0, "done"),
)
_SLEEP_S = 0.01


def _image_size(image: ImageInput) -> tuple[int, int]:
    size = getattr(image, "size", None)
    if isinstance(size, tuple) and len(size) == 2:
        return int(size[0]), int(size[1])
    try:
        from PIL import Image

        with Image.open(os.fspath(image)) as im:
            return im.size
    except Exception:
        return (0, 0)


class StubEngine:
    def recognize(
        self,
        image: ImageInput,
        options: OcrOptions = OcrOptions(),
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[CancelToken] = None,
    ) -> OcrResult:
        start = time.perf_counter()
        width, height = _image_size(image)
        for fraction, stage in _STAGES:
            if cancel is not None:
                cancel.raise_if_cancelled()
            if progress is not None:
                progress(fraction, stage)  # type: ignore[arg-type]
            time.sleep(_SLEEP_S)

        lines = []
        n_lines = len(_LINES)
        line_h = max(height // n_lines, 1) if height else 40
        line_w = width if width else 400
        for i, words in enumerate(_LINES):
            top, bottom = i * line_h, (i + 1) * line_h
            step = line_w // len(words)
            wrs = []
            for j, (text, conf) in enumerate(words):  # first word is rightmost
                right = line_w - j * step
                wrs.append(WordResult(text, conf, (right - step, top, right, bottom)))
            lines.append(
                LineResult(
                    text=" ".join(w.text for w in wrs),
                    confidence=sum(w.confidence for w in wrs) / len(wrs),
                    box=(0, top, line_w, bottom),
                    words=tuple(wrs),
                )
            )
        all_words = [w for ln in lines for w in ln.words]
        low = sum(w.confidence < LOW_CONFIDENCE_THRESHOLD for w in all_words)
        return OcrResult(
            text="\n".join(ln.text for ln in lines),
            lines=tuple(lines),
            mode_used="raw" if options.mode == "auto" else options.mode,
            low_confidence_fraction=low / len(all_words),
            elapsed_s=time.perf_counter() - start,
            image_size=(width, height),
        )

    def close(self) -> None:
        pass
