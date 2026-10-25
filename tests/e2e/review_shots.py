"""UI review screenshots with REAL results (real engine, real services, offscreen Qt).

    python tests/e2e/review_shots.py [--out DIR] [--scale 1|1.5|2] [--full]

``--scale`` sets QT_SCALE_FACTOR (must be set before Qt starts, so each scale is its own
process). Without ``--full`` only the scale-sensitive subset is written. ``run_all.sh``-style
driver: ``python tests/e2e/review_shots.py --all`` runs scale 1 (full), 1.5 and 2 as subprocesses.
Not collected by pytest (file name does not start with ``test_``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

_p = argparse.ArgumentParser()
_p.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
_p.add_argument("--scale", default="1")
_p.add_argument("--full", action="store_true")
_p.add_argument("--all", action="store_true")
ARGS = _p.parse_args()

if ARGS.all:
    out = ARGS.out
    for scale, extra in (("1", ["--full"]), ("1.5", []), ("2", [])):
        subprocess.run([sys.executable, __file__, "--out", out, "--scale", scale, *extra], check=True)
    raise SystemExit(0)

os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ.pop("MATNYAB_ENGINE", None)
os.environ["MATNYAB_REDUCE_MOTION"] = "1"
os.environ["MATNYAB_DATA_DIR"] = tempfile.mkdtemp(prefix="matnyab_review_")
if ARGS.scale != "1":
    os.environ["QT_SCALE_FACTOR"] = ARGS.scale

from PySide6.QtWidgets import QApplication  # noqa: E402

from matnyab import paths, services  # noqa: E402
from matnyab.engine.tesseract_engine import TesseractEngine  # noqa: E402
from matnyab.ui.app import create_app, create_main_window  # noqa: E402

OUT = Path(ARGS.out)
SUFFIX = "" if ARGS.scale == "1" else f"_x{ARGS.scale.replace('.', '')}"
SIZE = (1280, 800)


def pump(ms: int = 80) -> None:
    end = time.time() + ms / 1000
    while time.time() < end:
        QApplication.processEvents()
        time.sleep(0.005)


def new_window(engine, theme_name: str):
    # fresh data folder per window: history/settings never leak from one screenshot into the next
    os.environ["MATNYAB_DATA_DIR"] = tempfile.mkdtemp(prefix="matnyab_review_")
    settings = services.create_settings_store()
    s = settings.load()
    s.theme = theme_name
    settings.save(s)
    w = create_main_window(engine=engine, settings_store=settings, history_store=services.create_history_store())
    w.resize(*SIZE)
    w.show()
    w.activateWindow()
    pump(150)
    return w


def shot(w, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pump(200)
    path = OUT / f"{name}{SUFFIX}.png"
    pix = w.grab()
    pix.save(str(path))
    print("wrote", path.relative_to(ROOT) if path.is_relative_to(ROOT) else path,
          f"{pix.width()}x{pix.height()} dpr={pix.devicePixelRatio()}", flush=True)


def finish(w) -> None:
    w.close()
    w.deleteLater()
    pump(60)


def run(w, *files: Path) -> None:
    w.add_paths(list(files))
    if not w.wait_idle(300_000):
        raise RuntimeError("recognition did not finish")
    pump(150)


def main() -> int:
    create_app(["review"])
    clean, low = paths.samples_dir() / "client_clean.png", paths.samples_dir() / "client_low.jpg"
    tmp = Path(tempfile.mkdtemp(prefix="matnyab_review_files_"))
    bad = tmp / "عکس خراب.png"
    bad.write_bytes(b"this is not an image")
    engine = TesseractEngine()
    try:
        full = ARGS.full
        if full:
            w = new_window(None, "light")
            shot(w, "01_empty_light")
            finish(w)
            w = new_window(None, "dark")
            shot(w, "01_empty_dark")
            finish(w)

            # processing: grab while the real engine is half way
            w = new_window(engine, "light")
            w.add_paths([clean])
            end = time.time() + 60
            item = next(iter(w.items.values()))
            while time.time() < end and not (0.4 < item.progress < 0.8):
                pump(30)
            shot(w, "02_processing_light")
            w.wait_idle(300_000)
            finish(w)

        for theme_name in (("light", "dark") if full else ("light",)):
            w = new_window(engine, theme_name)
            run(w, clean)
            shot(w, f"03_clean_{theme_name}")
            finish(w)
        for theme_name in (("light", "dark") if full else ("light",)):
            w = new_window(engine, theme_name)
            run(w, low)
            w.result.editor.next_uncertain()
            shot(w, f"04_low_{theme_name}")
            finish(w)

        for theme_name in (("light", "dark") if full else ("light",)):
            w = new_window(engine, theme_name)
            run(w, clean, low)
            w.toggle_queue(True)
            w.select_item(w.panel.order()[1])
            shot(w, f"05_queue_{theme_name}")
            if full and theme_name == "light":
                w.toggle_history()
                shot(w, "06_history_light")
            finish(w)

        # error states: a bad file in a queue, and a real "engine unavailable" error
        w = new_window(engine, "light")
        run(w, bad, clean)
        w.select_item(w.panel.order()[0])
        shot(w, "07_error_bad_file_light")
        finish(w)
        if full:
            w = new_window(engine, "dark")
            run(w, bad, clean)
            w.select_item(w.panel.order()[0])
            shot(w, "07_error_bad_file_dark")
            finish(w)
            old = os.environ.get("MATNYAB_MODEL_DIR")
            os.environ["MATNYAB_MODEL_DIR"] = str(tmp / "no-model")
            try:
                w = new_window(None, "light")
                run(w, clean)
                w.result.error.details_btn.click()
                shot(w, "08_error_engine_light")
                finish(w)
            finally:
                if old is None:
                    os.environ.pop("MATNYAB_MODEL_DIR")
                else:
                    os.environ["MATNYAB_MODEL_DIR"] = old
    finally:
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
