"""Background processing: one image at a time, results reach the GUI by signals only."""

from __future__ import annotations

import threading
import traceback
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Union

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

from matnyab import engine as engine_pkg
from matnyab.api import (
    Cancelled, CancelToken, Mode, OcrEngine, OcrOptions, OcrResult,
)
from matnyab.ui import image_io
from matnyab.ui.logging import get_logger

__all__ = ["JobRunner", "EngineHolder", "ImageLoader"]

_log = get_logger("runner")


class EngineHolder:
    """Creates the engine lazily (first use, in the worker thread) and keeps it."""

    def __init__(self, engine: Optional[OcrEngine] = None) -> None:
        self._engine = engine
        self._lock = threading.Lock()

    @property
    def created(self) -> bool:
        return self._engine is not None

    def get(self) -> OcrEngine:
        with self._lock:
            if self._engine is None:
                self._engine = engine_pkg.create_engine()
            return self._engine

    def close(self) -> None:
        with self._lock:
            eng, self._engine = self._engine, None
        if eng is not None:
            try:
                eng.close()
            except Exception:
                _log.exception("engine close failed")


@dataclass(eq=False)
class _Job:
    item_id: str
    source: Union[Path, Image.Image]
    mode: Mode
    token: CancelToken = field(default_factory=CancelToken)
    abandoned: bool = False


class _WorkerSignals(QObject):
    progress = Signal(str, float, str)
    finished = Signal(str, object)
    failed = Signal(str, str, str, str)  # item id, kind, short message, technical detail
    ended = Signal(object)  # the _Job, always emitted last


class _Task(QRunnable):
    def __init__(self, job: _Job, holder: EngineHolder, signals: _WorkerSignals) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._job, self._holder, self._sig = job, holder, signals

    def run(self) -> None:  # worker thread
        job, sig = self._job, self._sig
        try:
            if job.abandoned:
                return
            try:
                engine = self._holder.get()
            except Exception as exc:
                sig.failed.emit(job.item_id, "unavailable", str(exc), f"{type(exc).__name__}: {exc}")
                return
            try:
                image = job.source if isinstance(job.source, Image.Image) else image_io.load_image(job.source)
            except image_io.ImageLoadError as exc:
                sig.failed.emit(job.item_id, exc.kind, str(exc), str(exc))
                return

            def on_progress(fraction: float, stage: str) -> None:
                if not job.abandoned:
                    sig.progress.emit(job.item_id, float(fraction), str(stage))

            try:
                result = engine.recognize(image, OcrOptions(mode=job.mode), on_progress, job.token)
            except Cancelled:
                return
            except Exception as exc:
                _log.exception("recognition failed")
                sig.failed.emit(job.item_id, "engine", f"{type(exc).__name__}: {exc}", f"{type(exc).__name__}: {exc}")
                return
            if not job.abandoned:
                sig.finished.emit(job.item_id, result)
        finally:
            sig.ended.emit(job)


class JobRunner(QObject):
    """Sequential job runner. All signals are delivered in the GUI thread."""

    started = Signal(str)
    progress = Signal(str, float, str)
    finished = Signal(str, object)          # item id, OcrResult
    failed = Signal(str, str, str, str)     # item id, kind, message, technical detail
    cancelled = Signal(str)                 # item id (immediately on cancel)
    idleChanged = Signal(bool)              # True when nothing runs and nothing waits

    def __init__(self, holder: Optional[EngineHolder] = None, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self.holder = holder or EngineHolder()
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(1)
        self._sig = _WorkerSignals(self)
        self._sig.progress.connect(self._on_progress)
        self._sig.finished.connect(self._on_finished)
        self._sig.failed.connect(self._on_failed)
        self._sig.ended.connect(self._on_ended)
        self._pending: deque[_Job] = deque()
        self._current: Optional[_Job] = None
        self._running_worker = False  # a worker task is executing (even if abandoned)
        self._idle = True

    # -- public
    @property
    def is_idle(self) -> bool:
        return self._idle

    @property
    def current_id(self) -> Optional[str]:
        return self._current.item_id if self._current and not self._current.abandoned else None

    @property
    def waiting_ids(self) -> list[str]:
        return [j.item_id for j in self._pending]

    def submit(self, item_id: str, source: Union[Path, Image.Image], mode: Mode) -> None:
        self._pending.append(_Job(item_id, source, mode))
        self._set_idle(False)
        self._advance()

    def cancel_all(self) -> list[str]:
        """Cancel the running job and drop waiting ones; returns affected item ids at once."""
        affected = [j.item_id for j in self._pending]
        self._pending.clear()
        cur = self._current
        if cur is not None and not cur.abandoned:
            cur.abandoned = True
            cur.token.cancel()
            affected.insert(0, cur.item_id)
        for item_id in affected:
            self.cancelled.emit(item_id)
        if not self._running_worker:
            self._current = None
            self._set_idle(True)
        return affected

    def remove_waiting(self, item_id: str) -> None:
        self._pending = deque(j for j in self._pending if j.item_id != item_id)
        if self._current and self._current.item_id == item_id and not self._current.abandoned:
            self._current.abandoned = True
            self._current.token.cancel()
            self.cancelled.emit(item_id)
        self._check_idle()

    def shutdown(self, wait_ms: int = 4000) -> None:
        self._pending.clear()
        if self._current is not None:
            self._current.abandoned = True
            self._current.token.cancel()
        self._pool.waitForDone(wait_ms)
        self.holder.close()

    # -- internals
    def _advance(self) -> None:
        if self._running_worker or not self._pending:
            self._check_idle()
            return
        job = self._pending.popleft()
        self._current = job
        self._running_worker = True
        self.started.emit(job.item_id)
        self._pool.start(_Task(job, self.holder, self._sig))

    def _check_idle(self) -> None:
        self._set_idle(not self._running_worker and not self._pending)

    def _set_idle(self, idle: bool) -> None:
        if idle != self._idle:
            self._idle = idle
            self.idleChanged.emit(idle)

    def _on_progress(self, item_id: str, fraction: float, stage: str) -> None:
        cur = self._current
        if cur is not None and cur.item_id == item_id and not cur.abandoned:
            self.progress.emit(item_id, fraction, stage)

    def _on_finished(self, item_id: str, result: OcrResult) -> None:
        cur = self._current
        if cur is not None and cur.item_id == item_id and not cur.abandoned:
            self.finished.emit(item_id, result)

    def _on_failed(self, item_id: str, kind: str, message: str, detail: str) -> None:
        cur = self._current
        if cur is not None and cur.item_id == item_id and not cur.abandoned:
            self.failed.emit(item_id, kind, message, detail)

    def _on_ended(self, job: _Job) -> None:
        self._running_worker = False
        if self._current is job:
            self._current = None
        self._advance()


# ------------------------------------------------------------- image tasks ---
class _LoaderSignals(QObject):
    thumb = Signal(str, object, object)   # item id, QImage, (w, h)
    full = Signal(str, object)            # item id, QImage
    failed = Signal(str, str, str)        # item id, kind, message


class _LoadTask(QRunnable):
    def __init__(self, item_id: str, source: Union[Path, Image.Image], want_full: bool,
                 signals: _LoaderSignals, thumb_px: int) -> None:
        super().__init__()
        self.setAutoDelete(True)
        self._id, self._src, self._full, self._sig, self._px = item_id, source, want_full, signals, thumb_px

    def run(self) -> None:
        try:
            if self._full:
                img = self._src if isinstance(self._src, Image.Image) else image_io.load_image(self._src)
                self._sig.full.emit(self._id, image_io.pil_to_qimage(img))
            else:
                thumb = image_io.make_thumbnail(self._src, self._px)
                size = self._src.size if isinstance(self._src, Image.Image) else image_io.probe_image(self._src)
                self._sig.thumb.emit(self._id, thumb, size)
        except image_io.ImageLoadError as exc:
            self._sig.failed.emit(self._id, exc.kind, str(exc))
        except Exception as exc:
            self._sig.failed.emit(self._id, "unreadable", f"{type(exc).__name__}: {exc}")


class ImageLoader(QObject):
    """Loads thumbnails and display images off the GUI thread."""

    thumbReady = Signal(str, object, object)
    fullReady = Signal(str, object)
    failed = Signal(str, str, str)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._pool = QThreadPool(self)
        self._pool.setMaxThreadCount(2)
        self._sig = _LoaderSignals(self)
        self._sig.thumb.connect(self.thumbReady)
        self._sig.full.connect(self.fullReady)
        self._sig.failed.connect(self.failed)

    def load_thumbnail(self, item_id: str, source: Union[Path, Image.Image], px: int = 96) -> None:
        self._pool.start(_LoadTask(item_id, source, False, self._sig, px))

    def load_full(self, item_id: str, source: Union[Path, Image.Image]) -> None:
        self._pool.start(_LoadTask(item_id, source, True, self._sig, 0))

    def wait(self, ms: int = 3000) -> None:
        self._pool.waitForDone(ms)
