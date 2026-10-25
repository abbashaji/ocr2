"""Behavioural tests of TesseractEngine on the bundled samples."""

from __future__ import annotations

import threading
import time

import numpy as np
import pytest
from PIL import Image, ImageOps

from matnyab.api import CancelToken, Cancelled, OcrOptions
from matnyab.engine import imageprep, scoring, segment
from matnyab.engine.tesseract_engine import TesseractEngine


@pytest.fixture(scope="session")
def small_image(clean_path) -> Image.Image:
    """The top part of the clean sample: a few lines, fast to recognise."""
    with Image.open(clean_path) as im:
        return im.convert("RGB").crop((0, 0, im.width, 170))


def _check_invariants(res) -> None:
    assert res.text == "\n".join(ln.text for ln in res.lines)
    for ln in res.lines:
        assert ln.text == " ".join(w.text for w in ln.words)


# ------------------------------------------------------------ structure ---


def test_text_invariants_and_boxes_inside_image(engine, small_image):
    res = engine.recognize(small_image, OcrOptions(mode="raw"))
    assert res.lines and res.image_size == small_image.size
    _check_invariants(res)
    w, h = res.image_size
    for ln in res.lines:
        assert ln.box is not None
        for box in [ln.box] + [x.box for x in ln.words]:
            assert box is not None
            l, t, r, b = box
            assert 0 <= l < r <= w and 0 <= t < b <= h
        assert 0 <= ln.confidence <= 100
        for x in ln.words:  # word boxes lie inside their line box
            assert ln.box[0] <= x.box[0] and x.box[2] <= ln.box[2]


def test_progress_stages_order_and_monotonic(engine, small_image):
    events: list[tuple[float, str]] = []
    engine.recognize(small_image, OcrOptions(mode="raw"), progress=lambda f, s: events.append((f, s)))
    fracs = [f for f, _ in events]
    stages = [s for _, s in events]
    assert fracs == sorted(fracs)
    assert all(0.0 <= f <= 1.0 for f in fracs)
    assert events[0] == (0.0, "preparing")
    assert events[-1] == (1.0, "done")
    order = ["preparing", "segmenting", "recognizing", "correcting", "done"]
    seen = [s for i, s in enumerate(stages) if i == 0 or s != stages[i - 1]]
    assert seen == order
    rec = [f for f, s in events if s == "recognizing"]
    assert rec[0] == pytest.approx(0.05) and rec[-1] == pytest.approx(0.90) and len(rec) > 2
    assert [f for f, s in events if s == "correcting"] == [pytest.approx(0.92)]


def test_cancel_mid_run_raises_within_2s(engine, small_image):
    token = CancelToken()
    state: dict[str, float] = {}

    def progress(frac: float, stage: str) -> None:
        if stage == "recognizing" and frac > 0.06 and "t" not in state:
            state["t"] = time.perf_counter()
            token.cancel()

    with pytest.raises(Cancelled):
        engine.recognize(small_image, OcrOptions(mode="raw", workers=2), progress, token)
    assert "t" in state, "cancel was never triggered"
    assert time.perf_counter() - state["t"] < 2.0


def test_cancel_before_start(engine, small_image):
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        engine.recognize(small_image, OcrOptions(), cancel=token)


def test_cancel_from_other_thread(engine, small_image):
    token = CancelToken()
    threading.Timer(0.5, token.cancel).start()
    t0 = time.perf_counter()
    with pytest.raises(Cancelled):
        engine.recognize(small_image, OcrOptions(mode="raw", workers=2), cancel=token)
    assert time.perf_counter() - t0 < 2.5


def test_worker_count_independence(engine, small_image):
    a = engine.recognize(small_image, OcrOptions(mode="raw", workers=1))
    b = engine.recognize(small_image, OcrOptions(mode="raw", workers=3))
    assert a.text == b.text and a.text
    assert [ln.box for ln in a.lines] == [ln.box for ln in b.lines]


def test_engine_reusable_after_close(small_image):
    eng = TesseractEngine()
    first = eng.recognize(small_image, OcrOptions(mode="raw", workers=2))
    eng.close()
    second = eng.recognize(small_image, OcrOptions(mode="raw", workers=2))
    eng.close()
    assert first.text == second.text


def test_blank_image_gives_empty_result(engine):
    for colour in ("white", "black", (120, 120, 120)):
        res = engine.recognize(Image.new("RGB", (200, 120), colour))
        assert res.text == "" and res.lines == () and res.low_confidence_fraction == 0.0
        assert res.image_size == (200, 120)


def test_two_level_image_is_segmented_in_both_polarities(small_image):
    bw = small_image.convert("L").point(lambda v: 255 if v > 140 else 0)
    assert set(np.unique(np.asarray(bw))) == {0, 255}
    gray, _ = imageprep.prepare(bw)
    inv_gray, _ = imageprep.prepare(ImageOps.invert(bw))
    assert np.array_equal(np.asarray(gray), np.asarray(inv_gray))   # dark-mode copy is re-inverted
    assert segment.segment_lines(gray)                                # Otsu alone would give no ink


def test_tiny_image_does_not_crash(engine):
    res = engine.recognize(Image.new("L", (3, 3), 255))
    assert res.text == ""


# ------------------------------------------------------- input variants ---


def _accuracy(engine, image, ref_text) -> float:
    res = engine.recognize(image, OcrOptions(mode="auto"))
    _check_invariants(res)
    return scoring.word_accuracy(ref_text, scoring.strip_markers(res.text))


@pytest.fixture(scope="session")
def clean_rgb(clean_path) -> Image.Image:
    with Image.open(clean_path) as im:
        return im.convert("RGB")


def test_variant_rgba_with_transparent_background(engine, clean_rgb, ref_text):
    rgba = clean_rgb.convert("RGBA")
    arr = np.asarray(rgba).copy()
    arr[..., 3] = 255
    white = (arr[..., :3] > 250).all(axis=2)
    arr[white, 3] = 0           # transparent where the page is white
    arr[white, :3] = 0          # ... and black underneath: wrong unless composited on white
    assert _accuracy(engine, Image.fromarray(arr, "RGBA"), ref_text) >= 0.97


def test_variant_palette(engine, clean_rgb, ref_text):
    pal = clean_rgb.quantize(colors=256)
    assert pal.mode == "P"
    assert _accuracy(engine, pal, ref_text) >= 0.97


def test_variant_16bit(engine, clean_rgb, ref_text):
    g = np.asarray(clean_rgb.convert("L")).astype(np.uint16) * 257
    im = Image.fromarray(g)
    assert im.mode.startswith("I;16")
    assert _accuracy(engine, im, ref_text) >= 0.97


def test_variant_exif_rotated(engine, clean_rgb, ref_text, tmp_path):
    rotated = clean_rgb.transpose(Image.Transpose.ROTATE_90)   # stored sideways ...
    exif = Image.Exif()
    exif[0x0112] = 6                                           # ... orientation: rotate 90 CW to view
    path = tmp_path / "rotated.png"
    rotated.save(path, exif=exif)
    res = engine.recognize(path, OcrOptions(mode="auto"))
    assert res.image_size == clean_rgb.size
    assert scoring.word_accuracy(ref_text, scoring.strip_markers(res.text)) >= 0.97


def test_variant_inverted_dark_mode(engine, clean_rgb, ref_text):
    assert _accuracy(engine, ImageOps.invert(clean_rgb), ref_text) >= 0.97


def test_inversion_decision_is_conservative(clean_rgb):
    gray = imageprep.to_gray(clean_rgb)
    assert imageprep.is_light_on_dark(gray) is False
    assert imageprep.is_light_on_dark(imageprep.to_gray(ImageOps.invert(clean_rgb))) is True


# ---------------------------------------------------------------- modes ---


def test_auto_picks_raw_for_clean_and_lex_for_low(clean_auto, low_auto):
    assert clean_auto.mode_used == "raw"
    assert low_auto.mode_used == "lex"
    assert clean_auto.low_confidence_fraction < 0.10 <= low_auto.low_confidence_fraction
    _check_invariants(clean_auto)
    _check_invariants(low_auto)


def test_keep_markers_option_keeps_more_text(engine, clean_path):
    kept = engine.recognize(clean_path, OcrOptions(mode="raw", keep_markers=True))
    assert "[" in kept.text or "]" in kept.text


# --------------------------------------------------------------- errors ---


def test_missing_model_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        TesseractEngine(model_dir=tmp_path / "nonexistent")


def test_empty_model_dir_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="fas.traineddata"):
        TesseractEngine(model_dir=tmp_path)


def test_missing_tesseract_raises(tmp_path):
    missing = tmp_path / "no" / "tesseract"
    with pytest.raises(FileNotFoundError, match="tesseract"):
        TesseractEngine(tesseract=missing)


def test_nonzero_exit_raises_runtime_error(tmp_path):
    import os
    import stat
    import sys

    if os.name == "nt":
        pytest.skip("shell script stub")
    fake = tmp_path / "fake_tesseract"
    fake.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "--version" ]; then echo "tesseract 5.0.0"; exit 0; fi\n'
        "echo 'boom: bad things' >&2\nexit 3\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    eng = TesseractEngine(tesseract=fake)
    assert eng.tesseract_version == "tesseract 5.0.0"
    img = Image.new("L", (200, 60), 255)
    for x in range(20, 180):
        for y in range(20, 40):
            img.putpixel((x, y), 0)
    with pytest.raises(RuntimeError, match="boom: bad things"):
        eng.recognize(img, OcrOptions(mode="raw", workers=1))
    eng.close()
