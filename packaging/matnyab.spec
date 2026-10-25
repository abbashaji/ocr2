# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MatnYab (onedir bundle MatnYab/).

Build (from the repository root, any OS):

    pyinstaller packaging/matnyab.spec --noconfirm --workpath <tmp> --distpath <tmp>

Environment variables read here:

    MATNYAB_TESSERACT   Path of the tesseract executable to bundle. On Windows
                        its whole folder is bundled (exe + DLLs, without
                        tessdata). If unset, no tesseract is bundled.
    MATNYAB_CLI_ENTRY   Override of the CLI entry script (the Linux dry run
                        points it at packaging/frozen_check.py).

Layout of the result:

    MatnYab/MatnYab.exe          windowed GUI   (entry src/matnyab/app.py)
    MatnYab/matnyab-cli.exe      console CLI    (entry src/matnyab/cli.py)
    MatnYab/_internal/           shared runtime = sys._MEIPASS = paths.app_root()
        model/ assets/fonts/ samples/ tesseract/ ...

Both executables come from ONE Analysis and ONE COLLECT, so they share
_internal. Every data folder is placed under _internal at the same relative
path that matnyab.paths expects below app_root().
"""
import importlib.util
import os
import re
import sys

from PyInstaller.config import CONF
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# SPECPATH is injected by PyInstaller: the folder that holds this spec.
PKG_DIR = os.path.abspath(SPECPATH)
ROOT = os.path.dirname(PKG_DIR)
SRC = os.path.join(ROOT, "src")
IS_WINDOWS = sys.platform.startswith("win")

GUI_ENTRY = os.path.join(SRC, "matnyab", "app.py")
CLI_ENTRY = os.environ.get("MATNYAB_CLI_ENTRY") or os.path.join(SRC, "matnyab", "cli.py")
ICON = os.path.join(PKG_DIR, "matnyab.ico")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---- version resource (Windows only; harmless elsewhere) -------------------
_vi = _load("make_version_info", os.path.join(PKG_DIR, "make_version_info.py"))
_work = CONF["workpath"]
VERSION_FILE = os.path.join(_work, "version_info.txt")
os.makedirs(_work, exist_ok=True)
_vi.write(VERSION_FILE, _vi.read_version(os.path.join(SRC, "matnyab", "__init__.py")))

# ---- data ------------------------------------------------------------------
datas = [
    (os.path.join(ROOT, "model"), "model"),
    (os.path.join(ROOT, "assets", "fonts"), os.path.join("assets", "fonts")),
    (os.path.join(ROOT, "samples", "client_clean.png"), "samples"),
    (os.path.join(ROOT, "samples", "client_ref.txt"), "samples"),
]
datas += collect_data_files("wordfreq")
datas += collect_data_files("docx")
for _optional in ("language_data", "langcodes"):  # wordfreq dependencies with data files
    try:
        datas += collect_data_files(_optional)
    except Exception:
        pass

binaries = []

# ---- bundled tesseract -> _internal/tesseract (what paths.tesseract_cmd() reads)
_tess = os.environ.get("MATNYAB_TESSERACT")
if _tess and os.path.isfile(_tess):
    _tess_dir = os.path.dirname(os.path.abspath(_tess))
    if IS_WINDOWS:
        # tesseract.exe + every DLL next to it; never tessdata, docs or training tools.
        for _name in sorted(os.listdir(_tess_dir)):
            _low = _name.lower()
            if _low == "tesseract.exe" or _low.endswith(".dll"):
                datas.append((os.path.join(_tess_dir, _name), "tesseract"))
    else:
        # PyInstaller resolves the shared libraries of an executable listed as a binary.
        binaries.append((os.path.abspath(_tess), "tesseract"))

# ---- size discipline -------------------------------------------------------
EXCLUDES = [
    "tkinter", "_tkinter", "unittest", "pydoc", "doctest", "test", "tests",
    "pytest", "setuptools", "pkg_resources", "distutils", "lib2to3",
    "numpy.tests", "numpy.f2py", "numpy.distutils", "PIL.ImageTk",
    "PySide6.QtQml", "PySide6.QtQmlCore", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuick3D", "PySide6.QtNetwork", "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras", "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtBluetooth", "PySide6.QtNfc", "PySide6.QtPositioning",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtStateMachine", "PySide6.QtSpatialAudio",
]

_KEEP_PLUGIN_DIRS = {"platforms", "styles", "imageformats", "iconengines"}
_DROP_PLUGIN_FILES = re.compile(r"qpdf|qwebp|qtiff|qtga|qwbmp|qmacjp2|qicns", re.I)
_DROP_QT_LIBS = re.compile(
    r"(^|[\\/])(lib)?Qt6?(Qml|Quick|Network|Pdf|WebEngine|WebChannel|WebSockets|3D|"
    r"Multimedia|Sql|Test|OpenGL|Designer|Help|Charts|DataVisualization|VirtualKeyboard|"
    r"Positioning|Sensors|Bluetooth|Nfc|SerialPort|RemoteObjects|Scxml|StateMachine|"
    r"SpatialAudio|Concurrent|PrintSupport|Xml)",
    re.I,
)
_DROP_RUNTIME_FILES = re.compile(r"(opengl32sw|d3dcompiler_47)\.dll$", re.I)
_KEEP_TRANSLATIONS = re.compile(r"qtbase_fa\.qm$", re.I)
# wordfreq ships ~60 word lists (about 58 MB); the app needs Persian and English only.
_KEEP_WORDFREQ = re.compile(r"_(fa|en)\.msgpack\.gz$")


def _wanted(dest):
    """False for Qt files the app does not need (dest is the path inside the bundle)."""
    norm = dest.replace("\\", "/")
    if norm.startswith("wordfreq/data/"):
        return bool(_KEEP_WORDFREQ.search(norm))
    if _DROP_RUNTIME_FILES.search(norm):
        return False
    base = norm.rsplit("/", 1)[-1]
    if "/translations/" in norm or norm.startswith("translations/"):
        return bool(_KEEP_TRANSLATIONS.search(base))
    if "/plugins/" in norm:
        parts = norm.split("/plugins/", 1)[1].split("/")
        if parts[0] not in _KEEP_PLUGIN_DIRS:
            return False
        return not _DROP_PLUGIN_FILES.search(base)
    if base.lower().startswith(("qt6", "libqt6", "qt5", "libqt5")) and _DROP_QT_LIBS.search(base):
        return False
    if "/qml/" in norm or norm.startswith("PySide6/qml") or "/PySide6/Qt/qml" in norm:
        return False
    return True


# Imported only by branches that may not be merged yet (UI, engine): name them so
# the bundle is complete whatever the entry scripts import statically.
RUNTIME_IMPORTS = [
    "PySide6.QtCore", "PySide6.QtGui", "PySide6.QtWidgets", "PySide6.QtSvg",
    "PySide6.QtSvgWidgets", "rapidfuzz", "rapidfuzz.fuzz", "rapidfuzz.process",
    "numpy", "PIL", "docx", "wordfreq",
]

a = Analysis(
    [GUI_ENTRY, CLI_ENTRY],
    pathex=[SRC],
    binaries=binaries,
    datas=datas,
    # create_engine imports matnyab.engine.tesseract_engine dynamically.
    hiddenimports=collect_submodules("matnyab") + RUNTIME_IMPORTS,
    hookspath=[],
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
)

a.binaries = [b for b in a.binaries if _wanted(b[0])]
a.datas = [d for d in a.datas if _wanted(d[0])]

# a.scripts entries are (name, source path, 'PYSOURCE'); name is the script's basename.
_scripts = {s[0]: s for s in a.scripts}
_gui_script = _scripts[os.path.splitext(os.path.basename(GUI_ENTRY))[0]]
_cli_script = _scripts[os.path.splitext(os.path.basename(CLI_ENTRY))[0]]

pyz = PYZ(a.pure)

_icon = ICON if (IS_WINDOWS and os.path.isfile(ICON)) else None
_version = VERSION_FILE if IS_WINDOWS else None

gui_exe = EXE(
    pyz, [_gui_script],
    exclude_binaries=True,
    name="MatnYab",
    console=False,
    icon=_icon,
    version=_version,
    upx=False,
    debug=False,
    strip=False,
)

cli_exe = EXE(
    pyz, [_cli_script],
    exclude_binaries=True,
    name="matnyab-cli",
    console=True,
    icon=_icon,
    version=_version,
    upx=False,
    debug=False,
    strip=False,
)

coll = COLLECT(
    gui_exe, cli_exe,
    a.binaries, a.datas,
    strip=False,
    upx=False,
    name="MatnYab",
)
