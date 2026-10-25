"""Static checks of the packaging files (no PyInstaller, Inno Setup or Windows needed)."""

from __future__ import annotations

import ast
import re
import struct
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PKG = ROOT / "packaging"
WORKFLOW = ROOT / ".github" / "workflows" / "build-windows.yml"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ---- spec ------------------------------------------------------------------

def test_spec_parses_and_names_entries_data_and_excludes():
    source = _text(PKG / "matnyab.spec")
    ast.parse(source)  # raises SyntaxError if the spec is broken
    assert 'os.path.join(SRC, "matnyab", "app.py")' in source
    assert '"matnyab", "cli.py"' in source
    assert 'name="MatnYab"' in source and 'name="matnyab-cli"' in source
    assert source.count("COLLECT(") == 1 and source.count("Analysis(") == 1
    for needle in ('"model"', '"fonts"', "client_clean.png", "client_ref.txt",
                   'collect_data_files("wordfreq")', 'collect_data_files("docx")',
                   "platforms", "styles", "imageformats", "iconengines",
                   "MATNYAB_TESSERACT", "tesseract"):
        assert needle in source, needle
    for excluded in ("tkinter", "unittest", "pydoc", "PySide6.QtQml", "PySide6.QtQuick",
                     "PySide6.QtNetwork", "PySide6.QtPdf", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore"):
        assert '"%s"' % excluded in source, excluded
    assert "console=False" in source and "console=True" in source


def test_spec_data_sources_exist():
    for rel in ("model/fas.traineddata", "assets/fonts", "samples/client_clean.png",
                "samples/client_ref.txt", "src/matnyab/app.py", "src/matnyab/cli.py"):
        assert (ROOT / rel).exists(), rel


def test_no_packaging_source_lives_in_ignored_folder_names():
    ignored = {"build", "dist", "obj", "target"}
    for path in list(PKG.rglob("*")) + list((ROOT / "tests" / "packaging").rglob("*")):
        assert not ignored.intersection(path.relative_to(ROOT).parts), path


def test_version_info_generator():
    import importlib.util

    spec = importlib.util.spec_from_file_location("make_version_info", PKG / "make_version_info.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    version = module.read_version(str(ROOT / "src" / "matnyab" / "__init__.py"))
    text = module.render(version)
    assert module.version_tuple("1.2.3") == (1, 2, 3, 0)
    assert "VSVersionInfo(" in text and "ProductVersion', '%s'" % version in text
    ast.parse(text.split("\n", 1)[1])  # the resource is a Python expression for PyInstaller


# ---- icon ------------------------------------------------------------------

def test_icon_has_required_sizes():
    data = (PKG / "matnyab.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1) and count >= 4
    sizes = {(data[6 + 16 * i] or 256) for i in range(count)}
    assert {16, 32, 48, 256} <= sizes, sizes
    assert (PKG / "make_icon.py").is_file()


# ---- installer script ------------------------------------------------------

def test_iss_sections_and_decisions():
    iss = _text(PKG / "matnyab.iss")
    for section in ("[Setup]", "[Languages]", "[Files]", "[Icons]", "[Tasks]"):
        assert section in iss, section
    for needle in ("AppId={{", "PrivilegesRequired=lowest", "PrivilegesRequiredOverridesAllowed=dialog",
                   "DefaultDirName={autopf}\\{#AppName}", "#define AppName \"MatnYab\"", "OutputBaseFilename=MatnYab-Setup-{#AppVersion}",
                   "{autoprograms}", "{autodesktop}", "Flags: unchecked", "Farsi.isl", "compiler:Default.isl"):
        assert needle in iss, needle
    assert "[Registry]" not in iss  # no file association
    assert not re.search(r"(?i)\b[a-z]:\\", iss), "hard-coded absolute path in matnyab.iss"
    assert re.search(r"AppId=\{\{[0-9A-F-]{36}\}", iss)


# ---- PowerShell build script -----------------------------------------------

def test_ps1_mentions_every_stage():
    ps1 = _text(PKG / "build_windows.ps1")
    for needle in ("param(", "$Version", "venv", "pip", "install", ".[build]", "tesseract", "choco install tesseract",
                   "PyInstaller", "packaging\\matnyab.spec", "size report", "portable", "CreateFromDirectory",
                   "ISCC", "choco install innosetup", "Farsi.isl", "__version__", "exit 1", "summary",
                   "MATNYAB_TESSERACT", "-lt 5"):
        assert needle in ps1, needle
    assert re.search(r"-not \$script:Summary\.ok\) \{ exit 1 \}", ps1)
    assert not re.search(r"[^\x00-\x7f]", ps1), "keep the script ASCII for Windows PowerShell 5.1"


# ---- workflow --------------------------------------------------------------

def test_workflow_text():
    text = _text(WORKFLOW)
    for needle in ("workflow_dispatch", "app/**", "v*", "ubuntu-24.04", "windows-2022", "needs: test",
                   "contents: write", "python -m pytest -q", "sudo apt-get install -y tesseract-ocr",
                   "choco install", "packaging/build_windows.ps1", "selftest", "--smoke",
                   "QT_QPA_PLATFORM: offscreen", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/DIR=",
                   "build-report.json", "upload-artifact", "results", "app/$($env:RUN_ID)"):
        assert needle in text, needle
    # report, artifact upload and publish must run even after a failure
    for step in ("Write build-report.json", "Upload artifacts", "Publish report to the results branch"):
        block = text.split("- name: %s" % step, 1)[1].split("\n      - ", 1)[0]
        assert "if: always()" in block, step
    assert "signtool" in text and "# - name:" in text and "${{ false }}" in text
    assert "secrets." not in text


def test_workflow_yaml_structure():
    yaml = pytest.importorskip("yaml")
    doc = yaml.safe_load(_text(WORKFLOW))
    triggers = doc.get("on", doc.get(True))  # PyYAML reads the bare key `on` as True
    assert "workflow_dispatch" in triggers
    assert triggers["push"]["branches"] == ["app/**"] and triggers["push"]["tags"] == ["v*"]
    assert doc["permissions"] == {"contents": "write"}
    jobs = doc["jobs"]
    assert set(jobs) == {"test", "windows"}
    assert jobs["test"]["runs-on"] == "ubuntu-24.04"
    assert jobs["windows"]["runs-on"] == "windows-2022"
    assert jobs["windows"]["needs"] == "test"
    always = [s["name"] for s in jobs["windows"]["steps"] if s.get("if") == "always()"]
    assert "Write build-report.json" in always and "Upload artifacts" in always
    assert "Publish report to the results branch" in always
