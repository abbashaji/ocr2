"""Resource lookup that works from a source tree and from a frozen build.

Dev root is the parent of ``src``. Frozen root is ``sys._MEIPASS`` if set,
else the executable's folder.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Optional

__all__ = [
    "app_root", "model_dir", "tesseract_cmd", "fonts_dir", "samples_dir",
    "data_dir",
]


def app_root() -> Path:
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    # <root>/src/matnyab/paths.py -> <root>
    return Path(__file__).resolve().parents[2]


def model_dir() -> Path:
    env = os.environ.get("MATNYAB_MODEL_DIR")
    if env:
        return Path(env)
    return app_root() / "model"


def tesseract_cmd() -> Optional[str]:
    """Path of the tesseract executable, or None if none was found."""
    env = os.environ.get("MATNYAB_TESSERACT")
    if env:
        return env
    exe = "tesseract.exe" if os.name == "nt" else "tesseract"
    bundled = app_root() / "tesseract" / exe
    if bundled.is_file():
        return str(bundled)
    return shutil.which("tesseract")


def fonts_dir() -> Path:
    return app_root() / "assets" / "fonts"


def samples_dir() -> Path:
    return app_root() / "samples"


def data_dir() -> Path:
    env = os.environ.get("MATNYAB_DATA_DIR")
    if env:
        path = Path(env)
    elif os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        path = Path(base) / "MatnYab"
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        base_dir = Path(xdg) if xdg else Path.home() / ".local" / "share"
        path = base_dir / "matnyab"
    path.mkdir(parents=True, exist_ok=True)
    return path
