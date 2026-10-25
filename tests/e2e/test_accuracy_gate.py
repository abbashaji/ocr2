"""Accuracy gate: fails the build when word accuracy on the client samples drops."""

from __future__ import annotations

import pytest

from matnyab.api import OcrOptions
from matnyab.engine import scoring

pytestmark = pytest.mark.slow

CLEAN_MIN = 0.98  # client ad: > 99% on clean full-size screenshots (measured 99.1%)
LOW_MIN = 0.93    # client ad: > 90% on low quality (measured 96.1%)


def _accuracy(engine, image, ref_text) -> float:
    res = engine.recognize(image, OcrOptions(mode="auto"))
    return scoring.word_accuracy(ref_text, scoring.strip_markers(res.text))


def test_clean_screenshot_accuracy(engine, clean_path, ref_text):
    acc = _accuracy(engine, clean_path, ref_text)
    print(f"client_clean.png word accuracy: {acc:.4f}")
    assert acc >= CLEAN_MIN, f"clean accuracy {acc:.4f} < {CLEAN_MIN}"


def test_low_quality_photo_accuracy(engine, low_path, ref_text):
    acc = _accuracy(engine, low_path, ref_text)
    print(f"client_low.jpg word accuracy: {acc:.4f}")
    assert acc >= LOW_MIN, f"low-quality accuracy {acc:.4f} < {LOW_MIN}"
