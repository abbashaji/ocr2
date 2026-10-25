"""Rotating log file in ``data_dir()`` and the friendly unhandled-exception hook."""

from __future__ import annotations

import logging as _logging
import logging.handlers
import sys
import threading
import traceback
from pathlib import Path
from types import TracebackType
from typing import Callable, Optional

from matnyab import paths

__all__ = ["setup_logging", "log_path", "install_excepthook", "get_logger"]

_LOGGER_NAME = "matnyab"
_installed = False


def log_path() -> Path:
    return paths.data_dir() / "matnyab.log"


def get_logger(name: str = "") -> _logging.Logger:
    return _logging.getLogger(f"{_LOGGER_NAME}.{name}" if name else _LOGGER_NAME)


def setup_logging() -> _logging.Logger:
    """Attach (once per target file) a rotating handler to the ``matnyab`` logger."""
    logger = _logging.getLogger(_LOGGER_NAME)
    logger.setLevel(_logging.INFO)
    target = str(log_path())
    for h in logger.handlers:
        if getattr(h, "baseFilename", None) == target:
            return logger
    for h in list(logger.handlers):  # data dir changed (tests): drop old file handlers
        if isinstance(h, logging.handlers.RotatingFileHandler):
            logger.removeHandler(h)
            h.close()
    handler = logging.handlers.RotatingFileHandler(
        target, maxBytes=512_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(
        _logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger


def install_excepthook(
    show_dialog: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Log every unhandled exception; optionally show a friendly dialog.

    ``show_dialog(summary, details)`` runs on the thread that raised, so the
    caller must make it GUI-safe (the app passes a queued signal emitter).
    """
    global _installed
    logger = setup_logging()

    def handle(exc_type: type, exc: BaseException, tb: Optional[TracebackType]) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        details = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            logger.error("Unhandled exception\n%s", details)
        except Exception:
            pass
        if show_dialog is not None:
            try:
                show_dialog(f"{exc_type.__name__}: {exc}", details)
            except Exception:
                pass

    sys.excepthook = handle

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        handle(args.exc_type, args.exc_value, args.exc_traceback)  # type: ignore[arg-type]

    threading.excepthook = thread_hook
    _installed = True
