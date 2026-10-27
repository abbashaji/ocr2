"""Accuracy gate: fails the build when word accuracy, numbers F1 or punctuation F1 drop on the client samples.

Word accuracy only sees letters and digits. Numbers F1 and punctuation F1 (``engine/scoring.py``) also see decimal
and thousands separators (``۱٫۶۴``), lost or extra digits (``۹۲`` -> ``۹]``), commas read as full stops and so on.
Thresholds sit just below the values measured with the shipped model (see docs/DEVELOPER.md, "Accuracy gate").
"""

from __future__ import annotations

import pytest

from matnyab.api import OcrOptions
from matnyab.engine import scoring

pytestmark = pytest.mark.slow

# name: (word accuracy, numbers F1, punctuation F1) minimum
CLEAN_MIN = (0.98, 0.95, 0.98)   # measured 1.0000 / 1.0000 / 1.0000 (client ad: > 99% on clean screenshots)
LOW_MIN = (0.93, 0.66, 0.95)     # measured 0.9762 / 0.6667 / 0.9583 (client ad: > 90% on low quality)
# The low-quality numbers F1 is 2/3 because of one known error (۹۲ read as ۹۹۲); a second lost or damaged
# number (۳۱, ۱٫۶۴) drops it to 0.5 and fails the build.


def _scores(engine, image, ref_text) -> tuple[float, float, float]:
    res = engine.recognize(image, OcrOptions(mode="auto"))
    text = scoring.strip_markers(res.text)
    return (
        scoring.word_accuracy(ref_text, text),
        scoring.numbers_f1(ref_text, text),
        scoring.punct_f1(ref_text, text),
    )


def _check(label, got, minimum) -> None:
    print(f"{label} word {got[0]:.4f} numbers F1 {got[1]:.4f} punctuation F1 {got[2]:.4f}")
    for name, value, floor in zip(("word accuracy", "numbers F1", "punctuation F1"), got, minimum):
        assert value >= floor, f"{label}: {name} {value:.4f} < {floor}"


def test_clean_screenshot_accuracy(engine, clean_path, ref_text):
    _check("client_clean.png", _scores(engine, clean_path, ref_text), CLEAN_MIN)


def test_low_quality_photo_accuracy(engine, low_path, ref_text):
    _check("client_low.jpg", _scores(engine, low_path, ref_text), LOW_MIN)
