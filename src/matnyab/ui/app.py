"""GUI entry point: application setup, ``main``, ``--smoke`` and window factory."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional, Sequence

__all__ = ["main", "create_main_window", "create_app"]


def create_app(argv: Optional[Sequence[str]] = None):
    """Create (or reuse) the QApplication with RTL, font, theme and icon."""
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from matnyab.ui import icons, theme

    app = QApplication.instance()
    if app is None:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        app = QApplication(list(argv) if argv is not None else sys.argv[:1])
        app.setApplicationName("MatnYab")
        app.setApplicationDisplayName("MatnYab")
    app.setStyle("Fusion")
    app.setLayoutDirection(Qt.RightToLeft)
    theme.load_fonts()
    icons.reset_app_icon_cache()
    app.setWindowIcon(icons.app_icon())
    theme.manager().apply()
    return app


def create_main_window(engine=None, settings_store=None, history_store=None):
    """Build a MainWindow (used by tests and by ``main``)."""
    create_app()
    from matnyab.ui.main_window import MainWindow

    return MainWindow(engine=engine, settings_store=settings_store, history_store=history_store)


def _install_crash_hook(window_getter) -> None:
    from PySide6.QtCore import QObject, Qt, Signal

    from matnyab.ui import dialogs
    from matnyab.ui.logging import install_excepthook, log_path

    class _Bridge(QObject):
        crashed = Signal(str, str)

    bridge = _Bridge()
    bridge.crashed.connect(
        lambda summary, details: dialogs.show_crash_dialog(
            window_getter(), summary, details, str(log_path())),
        Qt.QueuedConnection)
    install_excepthook(lambda summary, details: bridge.crashed.emit(summary, details))
    _install_crash_hook.bridge = bridge  # type: ignore[attr-defined]  # keep alive


def _run_smoke() -> int:
    from PySide6.QtWidgets import QApplication

    from matnyab import paths, services

    sample = paths.samples_dir() / "client_clean.png"
    window = None
    try:
        tmp = Path(tempfile.mkdtemp(prefix="matnyab_smoke_"))
        stores = (services.create_settings_store(tmp / "settings.json"),
                  services.create_history_store(tmp / "history.json"))
        window = create_main_window(settings_store=stores[0], history_store=stores[1])
        window.show()
        window.add_paths([sample])
        ok = window.wait_idle(180_000)
        text = window.result.editor.toPlainText()
        words = len(text.split())
        ok = ok and words > 0 and window.window() is window
        print(json.dumps({"ok": bool(ok), "window": True, "words": words}), flush=True)
        return 0 if ok else 1
    except Exception as exc:  # pragma: no cover - defensive
        print(json.dumps({"ok": False, "window": window is not None, "words": 0,
                          "error": f"{type(exc).__name__}: {exc}"}), flush=True)
        return 1
    finally:
        if window is not None:
            window.close()
            QApplication.processEvents()


def main(argv: Optional[Sequence[str]] = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog="matnyab", add_help=True)
    parser.add_argument("--smoke", action="store_true", help="self-test: open window, run one image")
    parser.add_argument("--theme", choices=("light", "dark"), default=None)
    parser.add_argument("files", nargs="*", help="images or folders to open")
    ns, _unknown = parser.parse_known_args(args_in)

    if ns.smoke:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        if "MATNYAB_DATA_DIR" not in os.environ:
            os.environ["MATNYAB_DATA_DIR"] = tempfile.mkdtemp(prefix="matnyab_smoke_data_")
    app = create_app(["matnyab"])
    if ns.smoke:
        return _run_smoke()

    from matnyab.ui import theme
    from matnyab.ui.logging import setup_logging

    setup_logging()
    holder: dict = {}
    _install_crash_hook(lambda: holder.get("window"))
    if ns.theme:
        theme.manager().set_override(ns.theme)
    window = create_main_window()
    holder["window"] = window
    window.show()
    if ns.files:
        window.add_paths([Path(f) for f in ns.files])
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
