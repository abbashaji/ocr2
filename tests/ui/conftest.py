"""Qt test fixtures (offscreen, in-memory services, isolated data dir)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("MATNYAB_ENGINE", "stub")
os.environ.setdefault("MATNYAB_REDUCE_MOTION", "1")

import pytest  # noqa: E402

from matnyab import paths, services  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("MATNYAB_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MATNYAB_REDUCE_MOTION", "1")


@pytest.fixture(scope="session")
def qapp():
    from matnyab.ui.app import create_app

    return create_app(["matnyab-tests"])


@pytest.fixture
def stores():
    return services.create_settings_store(), services.create_history_store()


@pytest.fixture
def make_window(qapp, stores):
    from PySide6.QtWidgets import QApplication

    from matnyab.ui.app import create_main_window

    created = []

    def factory(engine=None, settings_store=None, history_store=None):
        w = create_main_window(
            engine=engine,
            settings_store=settings_store or stores[0],
            history_store=history_store or stores[1],
        )
        w.show()
        w.activateWindow()
        from PySide6.QtTest import QTest

        QApplication.processEvents()
        created.append(w)
        return w

    yield factory
    from PySide6.QtCore import QEvent

    for w in created:
        w.close()
        w.deleteLater()
    QApplication.processEvents()
    QApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    QApplication.processEvents()


@pytest.fixture
def sample_png():
    return paths.samples_dir() / "client_clean.png"


@pytest.fixture
def sample_jpg():
    return paths.samples_dir() / "client_low.jpg"
