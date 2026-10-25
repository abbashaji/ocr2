import json
import os
import threading

import pytest

from matnyab.api import AppSettings
from matnyab.services import create_settings_store


def test_defaults_when_missing(tmp_path):
    store = create_settings_store(tmp_path / "s.json")
    assert store.load() == AppSettings()


def test_round_trip_format_and_copy(tmp_path):
    p = tmp_path / "sub" / "s.json"
    store = create_settings_store(p)
    s = AppSettings(theme="dark", mode="lex", editor_font_pt=20, digit_style="fa",
                    normalize_text=False, window_geometry="g", last_open_dir="د", last_save_dir="y")
    store.save(s)
    raw = p.read_text(encoding="utf-8")
    data = json.loads(raw)
    assert data["_v"] == 1
    assert "\n  " in raw  # indent=2
    loaded = store.load()
    assert loaded == s and loaded is not s
    loaded.theme = "light"
    assert store.load().theme == "dark"


def test_default_location_uses_data_dir(tmp_data_dir):
    create_settings_store().save(AppSettings(theme="light"))
    assert (tmp_data_dir / "settings.json").is_file()
    assert create_settings_store().load().theme == "light"


def test_corrupt_json_kept_as_bad(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{not json", encoding="utf-8")
    store = create_settings_store(p)
    assert store.load() == AppSettings()
    assert (tmp_path / "s.json.bad").read_text(encoding="utf-8") == "{not json"
    assert not p.exists()


def test_non_object_and_binary_are_corrupt(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("[1,2]", encoding="utf-8")
    assert create_settings_store(p).load() == AppSettings()
    assert (tmp_path / "s.json.bad").exists()
    p.write_bytes(b"\xff\xfe\x00\x01")
    assert create_settings_store(p).load() == AppSettings()


def test_unknown_missing_and_invalid_values(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"theme": "purple", "mode": "lex", "digit_style": 5,
                             "editor_font_pt": 100, "extra": 1, "normalize_text": "yes",
                             "last_open_dir": 3}), encoding="utf-8")
    s = create_settings_store(p).load()
    assert s.theme == "system" and s.mode == "lex" and s.digit_style == "keep"
    assert s.editor_font_pt == 32
    assert s.normalize_text is True and s.last_open_dir == ""
    assert not hasattr(s, "extra")


@pytest.mark.parametrize("val,exp", [(1, 9), (9, 9), (32, 32), (33, 32), (-5, 9), (15.6, 16), ("x", 14), (True, 14)])
def test_font_clamp(tmp_path, val, exp):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"editor_font_pt": val}), encoding="utf-8")
    assert create_settings_store(p).load().editor_font_pt == exp


def test_save_clamps_and_validates(tmp_path):
    store = create_settings_store(tmp_path / "s.json")
    store.save(AppSettings(theme="bogus", editor_font_pt=2))  # type: ignore[arg-type]
    s = store.load()
    assert s.theme == "system" and s.editor_font_pt == 9


def test_atomic_failure_leaves_old_file(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    store = create_settings_store(p)
    store.save(AppSettings(theme="dark"))
    before = p.read_bytes()

    def boom(*a, **k):
        raise OSError("simulated")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        store.save(AppSettings(theme="light"))
    monkeypatch.undo()
    assert p.read_bytes() == before
    assert sorted(x.name for x in tmp_path.iterdir()) == ["s.json"]


def test_concurrent_saves(tmp_path):
    p = tmp_path / "s.json"
    store = create_settings_store(p)
    errors = []

    def work(n):
        try:
            for i in range(25):
                store.save(AppSettings(editor_font_pt=9 + n, last_save_dir=f"d{n}" * 50))
                store.load()
        except Exception as e:  # pragma: no cover
            errors.append(e)

    ts = [threading.Thread(target=work, args=(n,)) for n in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errors
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["_v"] == 1 and 9 <= data["editor_font_pt"] <= 16
    assert not (tmp_path / "s.json.bad").exists()
    assert sorted(x.name for x in tmp_path.iterdir()) == ["s.json"]
