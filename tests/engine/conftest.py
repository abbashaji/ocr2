"""Shared fixtures for the engine tests (real Tesseract, bundled samples)."""

from __future__ import annotations

import pytest

from matnyab import paths
from matnyab.api import OcrOptions, OcrResult

if paths.tesseract_cmd() is None:  # pragma: no cover - environment guard
    pytest.skip("tesseract executable not available", allow_module_level=True)

from matnyab.engine.tesseract_engine import TesseractEngine  # noqa: E402


@pytest.fixture(scope="session")
def engine():
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
def clean_auto(engine, clean_path) -> OcrResult:
    return engine.recognize(clean_path, OcrOptions(mode="auto"))


@pytest.fixture(scope="session")
def low_auto(engine, low_path) -> OcrResult:
    return engine.recognize(low_path, OcrOptions(mode="auto"))
