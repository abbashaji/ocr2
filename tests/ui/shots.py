"""Deterministic screenshot generator: ``python tests/ui/shots.py``.

Writes PNGs to ``out/ui_shots/`` (offscreen Qt, stub engine, in-memory services).
``python tests/ui/shots.py --real`` instead runs the real engine and real services
on the client samples and writes ``real_*.png``.
"""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
REAL = "--real" in sys.argv
if REAL:
    os.environ.pop("MATNYAB_ENGINE", None)
else:
    os.environ["MATNYAB_ENGINE"] = "stub"
os.environ["MATNYAB_REDUCE_MOTION"] = "1"
_DATA = tempfile.mkdtemp(prefix="matnyab_shots_")
os.environ["MATNYAB_DATA_DIR"] = _DATA

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from matnyab import paths, services  # noqa: E402
from matnyab.api import HistoryItem  # noqa: E402
from matnyab.engine.stub import StubEngine  # noqa: E402
from matnyab.ui import dialogs, theme  # noqa: E402
from matnyab.ui.app import create_app, create_main_window  # noqa: E402
from matnyab.ui.models import ItemState  # noqa: E402

OUT = ROOT / "out" / "ui_shots"
SIZE = (1280, 800)
GATE_SIZE = (300, 200)  # images of this size block until released


class ShotEngine:
    """Stub with a fixed elapsed time; blocks on GATE_SIZE images."""

    def __init__(self, fail: bool = False):
        self.gate = threading.Event()
        self.fail = fail

    def recognize(self, image, options=None, progress=None, cancel=None):
        if self.fail:
            raise RuntimeError("tesseract: failed to load model 'fas' (code 0x1F)")
        if getattr(image, "size", None) == GATE_SIZE:
            while not self.gate.is_set():
                if cancel is not None:
                    cancel.raise_if_cancelled()
                time.sleep(0.01)
        res = StubEngine().recognize(image, options, progress, cancel)
        return dataclasses.replace(res, elapsed_s=2.4)

    def close(self):
        pass


def pump(ms: int = 60) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.005)


def new_window(engine=None, theme_name="light", history=None):
    stores = (services.create_settings_store(), history or services.create_history_store())
    s = stores[0].load()
    s.theme = theme_name
    stores[0].save(s)
    w = create_main_window(engine=engine, settings_store=stores[0], history_store=stores[1])
    w.resize(*SIZE)
    w.show()
    w.activateWindow()
    pump(100)
    return w


def shot(widget, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pump(120)
    path = OUT / f"{name}.png"
    widget.grab().save(str(path))
    print("wrote", path.relative_to(ROOT))


def close(w) -> None:
    w.close()
    w.deleteLater()
    pump(50)


def main_real() -> int:
    """Real engine + real services on the client samples."""
    from matnyab.engine import create_engine

    create_app(["shots"])
    engine = create_engine()
    for name, sample, theme_name in (
        ("real_clean_light", paths.samples_dir() / "client_clean.png", "light"),
        ("real_low_light", paths.samples_dir() / "client_low.jpg", "light"),
        ("real_low_dark", paths.samples_dir() / "client_low.jpg", "dark"),
    ):
        w = new_window(engine, theme_name)
        w.add_paths([sample])
        if not w.wait_idle(180000):
            raise RuntimeError(f"{name}: recognition did not finish")
        shot(w, name)
        close(w)
    engine.close()
    return 0


def main() -> int:
    create_app(["shots"])
    sample = paths.samples_dir() / "client_clean.png"
    low = paths.samples_dir() / "client_low.jpg"
    tmp = Path(tempfile.mkdtemp(prefix="matnyab_shots_files_"))
    gate_img = tmp / "scan_page_3.png"
    Image.new("RGB", GATE_SIZE, (240, 236, 220)).save(gate_img)
    bad = tmp / "broken_photo.jpg"
    bad.write_bytes(b"\xff\xd8 definitely not a jpeg")

    # 1. empty state (and drag-over variant)
    w = new_window()
    shot(w, "01_empty_state")
    w.empty.set_dragging(True)
    shot(w, "01b_empty_state_drag_over")
    close(w)

    # 2. processing
    eng = ShotEngine()
    w = new_window(eng)
    w.add_paths([gate_img])
    pump(250)
    item = next(iter(w.items.values()))
    w._on_progress(item.id, 0.55, "recognizing")
    shot(w, "02_processing")
    eng.gate.set()
    w.wait_idle()
    close(w)

    # 3. result light
    w = new_window(ShotEngine())
    w.add_paths([sample])
    w.wait_idle()
    w.result.editor.next_uncertain()
    shot(w, "03_result_light")
    # 4. result dark (same window, live switch)
    s = w.settings
    s.theme = "dark"
    w.apply_settings(s)
    shot(w, "04_result_dark")
    close(w)

    # 5. queue with mixed states
    eng = ShotEngine()
    w = new_window(eng)
    w.add_paths([sample])
    w.wait_idle()
    w.add_paths([gate_img, low, bad], select=False)
    pump(300)
    # order: done, processing (blocked), queued behind it, error
    w.select_item(w.panel.order()[0])
    w._on_progress(w.panel.order()[1], 0.62, "recognizing")
    w.toggle_queue(True)
    shot(w, "05_queue_mixed")
    eng.gate.set()
    w.wait_idle()

    # 5b. minimum window size with the queue open
    w.resize(960, 640)
    pump(100)
    shot(w, "11_min_size_queue")
    w.resize(*SIZE)
    close(w)

    # 6. settings dialog
    w = new_window(ShotEngine())
    dlg = dialogs.SettingsDialog(w.settings, w.apply_settings, w)
    dlg.show()
    shot(dlg, "06_settings_dialog")
    dlg.close()
    # 9. shortcuts dialog and about
    sc = dialogs.ShortcutsDialog(w)
    sc.show()
    shot(sc, "09_shortcuts_dialog")
    sc.close()
    ab = dialogs.AboutDialog(w)
    ab.show()
    shot(ab, "10_about_dialog")
    ab.close()
    close(w)

    # 7. history drawer
    hist = services.create_history_store()
    texts = [
        ("client_clean.png", "2026-10-24T14:05:00", 91.2, "ایران با نام رسمی جمهوری اسلامی ایران کشوری در غرب آسیا است این کشور از غرب با عراق"),
        ("صورتحساب ۱۴۰۵.jpg", "2026-10-23T09:41:00", 76.5, "مبلغ قابل پرداخت ۸۵۰۰۰۰ ریال تا تاریخ ۱۴۰۵/۰۸/۱۵ می‌باشد"),
        ("تصویر چسبانده‌شده ۱", "2026-10-21T18:22:00", 58.0, "این متن با کیفیت کم خوانده شده است"),
        ("scan_page_3.png", "2026-10-02T11:00:00", 95.0, "فصل سوم: بررسی نتایج و جمع‌بندی پژوهش"),
    ]
    for i, (src, when, conf, text) in enumerate(reversed(texts)):
        hist.add(HistoryItem(id=f"h{i}", source=src, created=when, text=text,
                             mode_used="raw", confidence=conf))
    w = new_window(ShotEngine(), history=hist)
    w.add_paths([sample])
    w.wait_idle()
    w.toggle_history()
    shot(w, "07_history_drawer")
    close(w)

    # 8. error card
    w = new_window(ShotEngine(fail=True))
    w.add_paths([sample])
    w.wait_idle()
    w.result.error.details_btn.click()
    shot(w, "08_error_card")
    close(w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main_real() if REAL else main())
