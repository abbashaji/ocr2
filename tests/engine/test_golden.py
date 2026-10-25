"""Golden comparisons against the legacy pipeline output, and the CLI contracts."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from matnyab import cli
from matnyab.api import OcrOptions

pytestmark = pytest.mark.slow

GOLDEN = Path(__file__).parent / "golden"


def _golden(name: str) -> str:
    # The legacy CLI printed the text followed by one newline.
    return (GOLDEN / name).read_text(encoding="utf-8").removesuffix("\n")


def test_clean_raw_identical_to_legacy(engine, clean_path):
    res = engine.recognize(clean_path, OcrOptions(mode="raw"))
    assert res.mode_used == "raw"
    assert res.text == _golden("client_clean.raw.txt")


def test_low_lex_identical_to_legacy(engine, low_path):
    res = engine.recognize(low_path, OcrOptions(mode="lex"))
    assert res.mode_used == "lex"
    assert res.text == _golden("client_low.lex.txt")


def _run_cli(monkeypatch, capsysbinary, argv):
    code = cli.main(argv)
    out = capsysbinary.readouterr().out.decode("utf-8")
    return code, out


def test_selftest_contract(monkeypatch, capsysbinary):
    code, out = _run_cli(monkeypatch, capsysbinary, ["selftest"])
    assert code == 0
    lines = out.strip().splitlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert set(data) == {"ok", "word_accuracy", "mode_used", "elapsed_s", "tesseract"}
    assert data["ok"] is True
    assert data["word_accuracy"] >= 0.98
    assert data["mode_used"] in ("raw", "lex")
    assert isinstance(data["elapsed_s"], float)
    assert "tesseract" in data["tesseract"].lower()


def test_recognize_json_contract(monkeypatch, capsysbinary, clean_path):
    code, out = _run_cli(
        monkeypatch, capsysbinary, ["recognize", str(clean_path), "--mode", "raw", "--json"]
    )
    assert code == 0
    data = json.loads(out)
    assert set(data) == {"text", "mode_used", "low_confidence_fraction", "elapsed_s", "lines"}
    assert data["mode_used"] == "raw"
    assert data["text"] == _golden("client_clean.raw.txt")
    assert data["text"] == "\n".join(ln["text"] for ln in data["lines"])
    for ln in data["lines"]:
        assert set(ln) == {"text", "confidence", "box"}
        assert len(ln["box"]) == 4


def test_recognize_plain_text_is_utf8(monkeypatch, capsysbinary, clean_path):
    code, out = _run_cli(monkeypatch, capsysbinary, ["recognize", str(clean_path), "--mode", "raw"])
    assert code == 0
    assert out == _golden("client_clean.raw.txt") + "\n"
