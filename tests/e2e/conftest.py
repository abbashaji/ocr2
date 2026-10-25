"""Fixtures for the end-to-end tests: real Tesseract engine, real services, real Qt window (offscreen)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

from matnyab import paths, services  # noqa: E402


@pytest.fixture(autouse=True)
def real_env(tmp_path, monkeypatch):
    """Real engine (never the stub), fresh data dir, no animations."""
    monkeypatch.delenv("MATNYAB_ENGINE", raising=False)
    monkeypatch.setenv("MATNYAB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MATNYAB_REDUCE_MOTION", "1")
    assert paths.tesseract_cmd(), "e2e tests need the tesseract executable on PATH"


@pytest.fixture(scope="session")
def engine():
    from matnyab.engine.tesseract_engine import TesseractEngine

    eng = TesseractEngine()
    yield eng
    eng.close()


@pytest.fixture(scope="session")
def clean_path():
    return paths.samples_dir() / "client_clean.png"


@pytest.fixture(scope="session")
def low_path():
    return paths.samples_dir() / "client_low.jpg"


@pytest.fixture(scope="session")
def ref_text() -> str:
    return (paths.samples_dir() / "client_ref.txt").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def qapp():
    from matnyab.ui.app import create_app

    return create_app(["matnyab-e2e"])


@pytest.fixture
def real_stores():
    """Real file-backed settings/history stores inside the fresh data dir."""
    return services.create_settings_store(), services.create_history_store()


@pytest.fixture
def real_window(qapp, real_stores):
    """Factory for MainWindows that use the real engine (created lazily by the window)."""
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication

    from matnyab.ui.app import create_main_window

    made = []

    def factory(engine=None):
        w = create_main_window(
            engine=engine, settings_store=real_stores[0], history_store=real_stores[1])
        w.resize(1280, 800)
        w.show()
        QApplication.processEvents()
        made.append(w)
        return w

    yield factory
    for w in made:
        w.close()
        w.deleteLater()
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


def pytest_sessionfinish(session, exitstatus):
    """Release what an earlier test left on the (offscreen) clipboard before interpreter exit.

    ``tests/ui/test_window.py::test_clipboard_paste_image_and_files`` hands a QMimeData to the
    clipboard; if it is still there when Python finalises, PySide6 6.12 on the offscreen platform
    crashes with a segmentation fault (exit code 139) after all tests passed.
    """
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.clipboard().clear()
            app.processEvents()
    except Exception:  # pragma: no cover - never fail the session from a cleanup hook
        pass
