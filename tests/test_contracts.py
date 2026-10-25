import dataclasses
import sys
import threading

import pytest

from matnyab import paths
from matnyab.api import (
    AppSettings, CancelToken, Cancelled, HistoryItem, LineResult, OcrOptions,
    OcrResult, WordResult,
)
from matnyab.engine import create_engine
from matnyab.engine.stub import StubEngine
from matnyab.services import _stub

STAGES = ["preparing", "segmenting", "recognizing", "correcting", "done"]


def check_invariants(result: OcrResult) -> None:
    for line in result.lines:
        assert line.text == " ".join(w.text for w in line.words)
    assert result.text == "\n".join(line.text for line in result.lines)


# ---- dataclasses -----------------------------------------------------------

def test_options_defaults_and_frozen():
    o = OcrOptions()
    assert (o.mode, o.keep_markers, o.workers) == ("auto", False, None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        o.mode = "raw"  # type: ignore[misc]


def test_line_and_result_invariants_enforced():
    w = [WordResult("a", 90.0, (0, 0, 1, 1)), WordResult("b", 80.0)]
    assert w[1].box is None
    line = LineResult("a b", 85.0, None, tuple(w))
    with pytest.raises(ValueError):
        LineResult("a  b", 85.0, None, tuple(w))
    ok = OcrResult("a b", (line,), "raw", 0.0, 0.1, (10, 10))
    with pytest.raises(dataclasses.FrozenInstanceError):
        ok.text = "x"  # type: ignore[misc]
    with pytest.raises(ValueError):
        OcrResult("a b\n", (line,), "raw", 0.0, 0.1, (10, 10))


def test_cancel_token():
    t = CancelToken()
    assert not t.cancelled
    t.raise_if_cancelled()
    t.cancel()
    assert t.cancelled
    with pytest.raises(Cancelled):
        t.raise_if_cancelled()
    assert issubclass(Cancelled, Exception)


def test_settings_and_history_defaults():
    s = AppSettings()
    assert (s.theme, s.mode, s.editor_font_pt, s.digit_style) == ("system", "auto", 14, "keep")
    assert s.normalize_text is True
    assert (s.window_geometry, s.last_open_dir, s.last_save_dir) == ("", "", "")
    h = HistoryItem("1", "a.png", "2026-01-01T00:00:00", "t", "raw", 90.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        h.text = "x"  # type: ignore[misc]


# ---- stub engine -----------------------------------------------------------

def test_create_engine_returns_stub(monkeypatch):
    monkeypatch.setenv("MATNYAB_ENGINE", "stub")
    assert type(create_engine()).__name__ == "StubEngine"


def test_create_engine_without_real_engine_raises(monkeypatch):
    monkeypatch.delenv("MATNYAB_ENGINE", raising=False)
    monkeypatch.setitem(sys.modules, "matnyab.engine.tesseract_engine", None)
    with pytest.raises(RuntimeError):
        create_engine()


def test_stub_result_and_progress():
    events = []
    result = StubEngine().recognize(
        str(paths.samples_dir() / "client_clean.png"),
        progress=lambda f, s: events.append((f, s)),
    )
    check_invariants(result)
    assert len(result.lines) == 3
    assert result.mode_used == "raw"
    assert [s for _, s in events] == STAGES
    fractions = [f for f, _ in events]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert result.image_size[0] > 0 and result.image_size[1] > 0
    assert 0.0 < result.low_confidence_fraction < 1.0
    for line in result.lines:
        assert line.box is not None
        for w in line.words:
            assert 0 <= w.confidence <= 100


def test_stub_mode_passthrough_and_close():
    e = StubEngine()
    assert e.recognize("missing.png", OcrOptions(mode="lex")).mode_used == "lex"
    e.close()


def test_stub_cancel_before_start_and_midway():
    token = CancelToken()
    token.cancel()
    with pytest.raises(Cancelled):
        StubEngine().recognize("x.png", cancel=token)

    token = CancelToken()

    def progress(fraction, stage):
        if stage == "segmenting":
            token.cancel()

    with pytest.raises(Cancelled):
        StubEngine().recognize("x.png", progress=progress, cancel=token)


def test_stub_runs_in_threads():
    out = []
    t = threading.Thread(target=lambda: out.append(StubEngine().recognize("x.png")))
    t.start()
    t.join()
    check_invariants(out[0])


# ---- paths -----------------------------------------------------------------

def test_dev_tree_resources():
    assert (paths.app_root() / "src" / "matnyab").is_dir()
    assert (paths.model_dir() / "fas.traineddata").is_file()
    for name in ("client_clean.png", "client_low.jpg", "client_ref.txt"):
        assert (paths.samples_dir() / name).is_file()
    assert (paths.fonts_dir() / "Vazirmatn-Regular.ttf").is_file()


def test_env_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("MATNYAB_MODEL_DIR", str(tmp_path / "m"))
    assert paths.model_dir() == tmp_path / "m"
    monkeypatch.setenv("MATNYAB_TESSERACT", "/x/tesseract")
    assert paths.tesseract_cmd() == "/x/tesseract"


def test_tesseract_bundled_then_which(monkeypatch, tmp_path):
    monkeypatch.delenv("MATNYAB_TESSERACT", raising=False)
    exe = "tesseract.exe" if sys.platform == "win32" else "tesseract"
    (tmp_path / "tesseract").mkdir()
    (tmp_path / "tesseract" / exe).write_text("")
    monkeypatch.setattr(paths, "app_root", lambda: tmp_path)
    assert paths.tesseract_cmd() == str(tmp_path / "tesseract" / exe)
    (tmp_path / "tesseract" / exe).unlink()
    monkeypatch.setattr(paths.shutil, "which", lambda name: "/usr/bin/tesseract")
    assert paths.tesseract_cmd() == "/usr/bin/tesseract"
    monkeypatch.setattr(paths.shutil, "which", lambda name: None)
    assert paths.tesseract_cmd() is None


def test_frozen_root(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert paths.app_root() == tmp_path
    monkeypatch.delattr(sys, "_MEIPASS")
    assert paths.app_root() == paths.Path(sys.executable).resolve().parent


def test_data_dir_created(tmp_data_dir):
    assert not tmp_data_dir.exists()
    assert paths.data_dir() == tmp_data_dir
    assert tmp_data_dir.is_dir()


def test_data_dir_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("MATNYAB_DATA_DIR", raising=False)
    monkeypatch.setattr(paths.os, "name", "posix")
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    assert paths.data_dir() == tmp_path / "matnyab"
    assert (tmp_path / "matnyab").is_dir()


# ---- services stubs (the in-memory placeholders, imported explicitly) --------------------------------------------------------

def test_settings_round_trip():
    store = _stub.create_settings_store()
    s = store.load()
    assert s == AppSettings()
    s.theme = "dark"
    assert store.load().theme == "system"  # load returns a copy
    store.save(s)
    assert store.load().theme == "dark"


def test_history_round_trip():
    store = _stub.create_history_store()
    a = HistoryItem("a", "a.png", "2026-01-01T00:00:00", "x", "raw", 90.0)
    b = HistoryItem("b", "b.png", "2026-01-02T00:00:00", "y", "lex", 80.0)
    store.add(a)
    store.add(b)
    assert [i.id for i in store.list()] == ["b", "a"]
    store.delete("b")
    assert [i.id for i in store.list()] == ["a"]
    store.clear()
    assert store.list() == []


def test_export_text(tmp_path):
    p = tmp_path / "o.txt"
    _stub.export_text("متن\nدو", p, "txt")
    assert p.read_text(encoding="utf-8") == "متن\nدو"
    with pytest.raises(NotImplementedError):
        _stub.export_text("x", tmp_path / "o.docx", "docx")


def test_text_helpers_identity():
    for style in ("keep", "fa", "en"):
        assert _stub.convert_digits("abc ۱۲۳ 123", style) == "abc ۱۲۳ 123"
    assert _stub.normalize_text("ي ك") == "ي ك"


# ---- real services ---------------------------------------------------------

def test_real_services_are_wired():
    import matnyab.services as services
    assert services.convert_digits("12", "fa") == "۱۲"
    assert services.convert_digits("۱۲", "en") == "12"
    assert services.create_settings_store is not _stub.create_settings_store
    assert services.export_text is not _stub.export_text
