"""JSON settings persistence with tolerant loading and atomic writes."""

from __future__ import annotations

import dataclasses
import json
import os
import threading
from pathlib import Path
from typing import Optional

from matnyab import paths
from matnyab.api import AppSettings
from matnyab.services._atomic import atomic_write_bytes

SCHEMA_VERSION = 1
_THEMES = ("system", "light", "dark")
_MODES = ("auto", "raw", "lex")
_DIGIT_STYLES = ("keep", "fa", "en")
FONT_MIN, FONT_MAX = 9, 32


def _valid_modes() -> tuple[str, ...]:
    try:
        from typing import get_args

        from matnyab.api import Mode

        args = get_args(Mode)
        if args:
            return tuple(args)
    except Exception:  # pragma: no cover - defensive
        pass
    return _MODES


class JsonSettingsStore:
    def __init__(self, path: Optional[str | os.PathLike[str]] = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else paths.data_dir() / "settings.json"

    def load(self) -> AppSettings:
        with self._lock:
            path = self.path
            defaults = AppSettings()
            try:
                raw = path.read_bytes()
            except FileNotFoundError:
                return defaults
            except OSError:
                return defaults
            try:
                data = json.loads(raw.decode("utf-8-sig"))
                if not isinstance(data, dict):
                    raise ValueError("settings root is not an object")
            except (ValueError, UnicodeDecodeError):
                self._keep_bad(path)
                return defaults
            return self._from_dict(data, defaults)

    def save(self, settings: AppSettings) -> None:
        with self._lock:
            data = {"_v": SCHEMA_VERSION}
            data.update(dataclasses.asdict(self._sanitize(settings)))
            payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
            atomic_write_bytes(self.path, payload)

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _keep_bad(path: Path) -> None:
        bad = path.with_name(path.name + ".bad")
        try:
            os.replace(path, bad)
        except OSError:
            pass

    @staticmethod
    def _sanitize(s: AppSettings) -> AppSettings:
        return JsonSettingsStore._from_dict(dataclasses.asdict(s), AppSettings())

    @staticmethod
    def _from_dict(data: dict, defaults: AppSettings) -> AppSettings:
        out = dataclasses.replace(defaults)

        def enum(key: str, allowed: tuple[str, ...]) -> None:
            v = data.get(key)
            if isinstance(v, str) and v in allowed:
                setattr(out, key, v)

        enum("theme", _THEMES)
        enum("mode", _valid_modes())
        enum("digit_style", _DIGIT_STYLES)

        pt = data.get("editor_font_pt")
        if isinstance(pt, float) and pt == pt and pt not in (float("inf"), float("-inf")):
            pt = int(round(pt))
        if isinstance(pt, int) and not isinstance(pt, bool):
            out.editor_font_pt = max(FONT_MIN, min(FONT_MAX, pt))

        if isinstance(data.get("normalize_text"), bool):
            out.normalize_text = data["normalize_text"]
        for key in ("window_geometry", "last_open_dir", "last_save_dir"):
            if isinstance(data.get(key), str):
                setattr(out, key, data[key])
        return out


def create_settings_store(path: Optional[str | os.PathLike[str]] = None) -> JsonSettingsStore:
    return JsonSettingsStore(path)
