"""Entry script for the Linux PyInstaller dry run (owned by packaging/).

``frozen_check.py --paths`` prints one JSON line describing what the frozen
program can see: ``paths.app_root()``, model, fonts, samples, the bundled
tesseract, imports of every runtime dependency and wordfreq's Persian list.
Any other arguments are handed to ``matnyab.cli.main`` unchanged, so
``selftest`` and ``recognize`` behave exactly as in the real CLI.

It is bundled as ``matnyab-cli`` only when MATNYAB_CLI_ENTRY points here
(packaging/linux_dry_run.sh does that). The shipped CLI is src/matnyab/cli.py.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys


def _collect() -> dict:
    from matnyab import __version__, paths

    root = paths.app_root()
    model = paths.model_dir() / "fas.traineddata"
    fonts = sorted(p.name for p in paths.fonts_dir().glob("*.ttf"))
    samples = paths.samples_dir()
    info = {
        "ok": True,
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "app_root": str(root),
        "model": model.is_file(),
        "model_bytes": model.stat().st_size if model.is_file() else 0,
        "fonts": fonts,
        "samples": {n: (samples / n).is_file() for n in ("client_clean.png", "client_ref.txt")},
    }

    tess = paths.tesseract_cmd()
    info["tesseract"] = tess
    info["tesseract_bundled"] = bool(tess) and str(tess).startswith(str(root))
    if tess:
        try:
            out = subprocess.run([tess, "--version"], capture_output=True, text=True, timeout=30)
            info["tesseract_version"] = (out.stdout or out.stderr).splitlines()[0]
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            info["tesseract_version"] = "error: %s" % exc
            info["ok"] = False

    imports = {}
    for name in ("numpy", "PIL", "rapidfuzz", "docx", "PySide6.QtCore", "PySide6.QtGui",
                 "PySide6.QtWidgets", "PySide6.QtSvg", "wordfreq"):
        try:
            importlib.import_module(name)
            imports[name] = True
        except Exception as exc:  # noqa: BLE001
            imports[name] = "%s: %s" % (type(exc).__name__, exc)
            info["ok"] = False
    info["imports"] = imports

    try:
        import wordfreq

        top = wordfreq.top_n_list("fa", 5)
        info["wordfreq_fa_top"] = top
        info["wordfreq_fa_ok"] = len(top) == 5 and wordfreq.word_frequency("و", "fa") > 0
    except Exception as exc:  # noqa: BLE001
        info["wordfreq_fa_ok"] = False
        info["wordfreq_error"] = "%s: %s" % (type(exc).__name__, exc)
    if not info["wordfreq_fa_ok"]:
        info["ok"] = False

    if not (info["model"] and fonts and all(info["samples"].values())):
        info["ok"] = False
    return info


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--paths"]:
        info = _collect()
        sys.stdout.write(json.dumps(info, ensure_ascii=False) + "\n")
        return 0 if info["ok"] else 1
    from matnyab.cli import main as cli_main

    return cli_main(args)


if __name__ == "__main__":
    sys.exit(main())
