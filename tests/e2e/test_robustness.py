"""Robustness with the real engine: huge and tiny images, bad files, unwritable folders, odd paths."""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

import pytest
from PIL import Image, ImageDraw, ImageFont

from matnyab import paths
from matnyab.engine import scoring
from matnyab.ui.strings import S
from matnyab.ui.models import ItemState

pytestmark = [pytest.mark.slow, pytest.mark.ui]

# A GUI event loop that does not spin for this long counts as a frozen UI.
MAX_UI_STALL_S = 1.0


def _font(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(paths.fonts_dir() / "Vazirmatn-Regular.ttf"), px)


@pytest.fixture(scope="module")
def ref_words() -> list[str]:
    return (paths.samples_dir() / "client_ref.txt").read_text(encoding="utf-8").split()


@pytest.fixture
def small_text_image(tmp_path):
    """First ~3 lines of the clean sample: real Persian text, recognised in about a second."""
    im = Image.open(paths.samples_dir() / "client_clean.png").convert("RGB")
    out = tmp_path / "small.png"
    im.crop((0, 0, im.width, 120)).save(out)
    return out


def _big_page(path: Path, ref_words: list[str], size=(6000, 4000), lines=29) -> Path:
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    font = _font(64)
    i, y = 0, 100
    for _ in range(lines):
        line = ""
        while d.textlength(line + " " + ref_words[i % len(ref_words)], font=font) < size[0] - 400:
            line += " " + ref_words[i % len(ref_words)]
            i += 1
        d.text((size[0] - 100, y), line.strip(), font=font, fill="black", anchor="ra")
        y += 130
    im.save(path)
    return path


class _StallMeter:
    """Measures the longest gap between GUI timer ticks while the event loop is spinning."""

    def __init__(self):
        from PySide6.QtCore import QTimer

        self.max_gap = 0.0
        self._last = time.perf_counter()
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(20)

    def _tick(self):
        now = time.perf_counter()
        self.max_gap = max(self.max_gap, now - self._last)
        self._last = now

    def stop(self):
        self._timer.stop()


# --------------------------------------------------------------- big image ---

def test_very_large_page_completes_with_progress_and_responsive_ui(real_window, tmp_path, ref_words):
    big = _big_page(tmp_path / "big 6000x4000.png", ref_words)
    w = real_window()
    progress: list[tuple[float, str]] = []
    w.runner.progress.connect(lambda _id, f, s: progress.append((f, s)))
    meter = _StallMeter()
    w.add_paths([big])
    finished = w.wait_idle(600_000)
    meter.stop()
    assert finished
    item = next(iter(w.items.values()))
    assert item.state == ItemState.DONE, (item.state, item.error_message)
    assert item.size == (6000, 4000)
    assert len(item.result.lines) >= 25
    assert len(progress) >= 20, "progress should be reported during a long run"
    fractions = [f for f, _ in progress]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert meter.max_gap < MAX_UI_STALL_S, f"UI stalled for {meter.max_gap:.2f}s"
    # first line of the synthetic page is real reference text
    acc = scoring.word_accuracy(" ".join(ref_words[:8]), " ".join(item.result.lines[0].text.split()[:8]))
    assert acc >= 0.6, item.result.lines[0].text


def test_cancel_large_page_is_prompt_and_keeps_ui_usable(real_window, tmp_path, ref_words, small_text_image):
    big = _big_page(tmp_path / "big.png", ref_words)
    w = real_window()
    w.add_paths([big])
    deadline = time.perf_counter() + 60
    from PySide6.QtWidgets import QApplication

    while time.perf_counter() < deadline and w.runner.current_id is None:
        QApplication.processEvents()
        time.sleep(0.01)
    time.sleep(1.0)  # let the pipeline get going
    t0 = time.perf_counter()
    assert w.cancel_processing()
    assert w.wait_idle(30_000)
    assert time.perf_counter() - t0 < 10, "cancelling a large page must be prompt"
    item = next(iter(w.items.values()))
    assert item.state == ItemState.QUEUED and item.result is None
    # the window still works afterwards
    w.add_paths([small_text_image])
    assert w.wait_idle(120_000)
    assert w.result.editor.toPlainText().strip()


# ------------------------------------------------------------- tiny images ---

def test_one_pixel_image_does_not_crash(real_window, tmp_path):
    p = tmp_path / "one.png"
    Image.new("RGB", (1, 1), "white").save(p)
    w = real_window()
    w.add_paths([p])
    assert w.wait_idle(60_000)
    item = next(iter(w.items.values()))
    assert item.state in (ItemState.DONE, ItemState.ERROR)
    if item.state == ItemState.DONE:
        assert item.result.text == ""
    assert w.runner.is_idle


def test_tiny_word_image_is_recognised(real_window, tmp_path):
    im = Image.new("RGB", (40, 14), "white")
    ImageDraw.Draw(im).text((2, 0), "متن", font=_font(11), fill="black")
    p = tmp_path / "tiny.png"
    im.save(p)
    w = real_window()
    w.add_paths([p])
    assert w.wait_idle(60_000)
    item = next(iter(w.items.values()))
    assert item.state == ItemState.DONE
    assert item.result.text.strip() in ("متن", "من")  # 11 px text: either reading is acceptable


# --------------------------------------------------------- non-image files ---

@pytest.mark.parametrize("name,payload", [
    ("fake.png", b"this is not a png"),
    ("empty.jpg", b""),
    ("notes.txt", b"plain text"),
    ("truncated.png", None),  # first bytes of a real PNG
])
def test_non_image_files_give_error_item_and_queue_continues(
        real_window, tmp_path, small_text_image, name, payload):
    bad = tmp_path / name
    bad.write_bytes(small_text_image.read_bytes()[:40] if payload is None else payload)
    w = real_window()
    items = w.add_paths([bad, small_text_image])
    assert len(items) == 2
    assert w.wait_idle(120_000)
    assert items[0].state == ItemState.ERROR
    assert items[0].error_kind == "unreadable"
    assert items[1].state == ItemState.DONE, "a bad file must not stop the rest of the queue"
    # the error card is shown for the bad item and the Persian message is non-empty
    w.select_item(items[0].id)
    assert w.result.error.isVisibleTo(w.result)
    title, msg = w._error_texts(items[0])
    assert title and msg


# ---------------------------------------------------------- unwritable save ---

def _unwritable_folder(tmp_path, monkeypatch) -> Path:
    """A folder the app cannot save into.

    As a normal user: a real read-only folder. As root (permissions do not apply, e.g. in
    containers): a folder path below a regular file, which fails the same way (OSError).
    """
    ro = tmp_path / "read only"
    ro.mkdir()
    os.chmod(ro, stat.S_IRUSR | stat.S_IXUSR)
    if os.access(ro, os.W_OK):  # root: chmod has no effect
        os.chmod(ro, 0o755)
        blocker = tmp_path / "blocker"
        blocker.write_text("x")
        return blocker / "folder"
    return ro


def test_save_into_unwritable_folder_shows_toast_and_keeps_text(
        real_window, real_stores, tmp_path, monkeypatch, small_text_image):
    w = real_window()
    w.add_paths([small_text_image])
    assert w.wait_idle(120_000)
    text_before = w.result.editor.toPlainText()
    folder = _unwritable_folder(tmp_path, monkeypatch)
    last_dir_before = w.settings.last_save_dir
    try:
        for fmt in ("txt", "docx"):
            target = folder / f"out.{fmt}"
            monkeypatch.setattr(w, "_ask_save_path", lambda name, t=target, f=fmt: (str(t), f))
            w.save_current()  # must not raise
            assert w.toast._label.text() == S.toast_save_failed
            assert not target.exists()
        assert w.settings.last_save_dir == last_dir_before
        assert w.result.editor.toPlainText() == text_before
        leftovers = [p for p in folder.parent.iterdir() if p.name.endswith(".tmp")] if folder.parent.is_dir() else []
        assert not leftovers
    finally:
        os.chmod(tmp_path / "read only", 0o755)


def test_save_all_with_unwritable_folder_does_not_raise(
        real_window, tmp_path, monkeypatch, small_text_image):
    w = real_window()
    w.add_paths([small_text_image])
    assert w.wait_idle(120_000)
    folder = _unwritable_folder(tmp_path, monkeypatch)
    monkeypatch.setattr(w, "_ask_save_dir", lambda: str(folder))
    w.save_all()  # must not raise
    assert not folder.exists() or not any(folder.iterdir())


# ---------------------------------------------------- Persian paths, spaces ---

def test_persian_and_space_paths_end_to_end(real_window, real_stores, tmp_path, monkeypatch, small_text_image):
    from docx import Document

    src_dir = tmp_path / "پوشه آزمایشی  با فاصله"
    src_dir.mkdir()
    src = src_dir / "تصویر نمونه ۱ (کپی).png"
    src.write_bytes(small_text_image.read_bytes())
    w = real_window()
    w.add_paths([src])
    assert w.wait_idle(120_000)
    item = next(iter(w.items.values()))
    assert item.state == ItemState.DONE, item.error_message
    assert item.name == src.name
    text = w.result.editor.toPlainText()
    assert text.strip()
    assert real_stores[1].list()[0].source == src.name

    out_dir = tmp_path / "خروجی ها" / "نسخه ۲ نهایی"
    for fmt in ("txt", "docx"):
        target = out_dir / f"متن استخراج شده.{fmt}"
        monkeypatch.setattr(w, "_ask_save_path", lambda name, t=target, f=fmt: (str(t), f))
        w.save_current()
        assert target.is_file() and target.stat().st_size > 0
    assert w.settings.last_save_dir == str(out_dir)
    txt = (out_dir / "متن استخراج شده.txt").read_text(encoding="utf-8-sig")
    assert scoring.words(txt) == scoring.words(w.final_text(text))
    doc = Document(str(out_dir / "متن استخراج شده.docx"))
    assert scoring.words("\n".join(p.text for p in doc.paragraphs)) == scoring.words(w.final_text(text))

    # save_all uses the original file name (Persian + spaces) as the stem
    all_dir = tmp_path / "همه ی نتایج"
    all_dir.mkdir()
    monkeypatch.setattr(w, "_ask_save_dir", lambda: str(all_dir))
    w.save_all()
    assert (all_dir / "تصویر نمونه ۱ (کپی).txt").is_file()


def test_cli_with_persian_space_path(tmp_path, small_text_image, capsysbinary):
    from matnyab import cli

    src = tmp_path / "پوشه با فاصله" / "عکس ۱.png"
    src.parent.mkdir()
    src.write_bytes(small_text_image.read_bytes())
    assert cli.main(["recognize", str(src), "--mode", "raw"]) == 0
    out = capsysbinary.readouterr().out.decode("utf-8")
    assert out.strip()
