# MatnYab (متن‌یاب)

Offline desktop app that converts Persian images (screenshots, photos of text)
into editable text. The OCR core is Tesseract 5 with a fine-tuned `fas` model
plus a per-line multi-scale pipeline and optional lexicon correction. The UI
(PySide6) is Persian and right-to-left; code, comments and docs are English.

## Layout

- `src/matnyab/api.py` - frozen contracts (engine types, services types).
- `src/matnyab/paths.py` - resource lookup (works in dev and when frozen).
- `src/matnyab/engine/` - OCR engine (`StubEngine` until the real one lands).
- `src/matnyab/services/` - settings, history, export, text helpers.
- `model/`, `samples/`, `assets/` - bundled model, test images, fonts.
- `legacy/` - research code that the engine is ported from.

## Run the tests

```
python -m venv .venv
.venv/bin/pip install -e .[dev]      # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest -q
```

Tests run with `MATNYAB_ENGINE=stub` and `QT_QPA_PLATFORM=offscreen` by default
(see `tests/conftest.py`).

## Entry points

- GUI: `python -m matnyab`
- CLI: `python -m matnyab.cli recognize IMAGE [--mode auto|raw|lex] [--json]`
  and `python -m matnyab.cli selftest`

The GUI and CLI are placeholders in this version.

## Developer setup

```
python -m venv .venv
.venv/bin/pip install -e .[dev]      # Windows: .venv\Scripts\pip
.venv/bin/python -m pytest -q
```

Python 3.12 is the reference version. Tesseract 5 must be installed for the real
engine (Linux: `sudo apt-get install tesseract-ocr`; Windows: `choco install tesseract`).
Set `MATNYAB_TESSERACT` to use a specific executable.

## Windows build (GitHub Actions)

The Windows bundle, installer and portable zip are built by
`.github/workflows/build-windows.yml` on a `windows-2022` runner. Nothing needs
to be installed on your own machine.

- Push to any branch named `app/...` (for example `app/packaging`), push a tag
  `v*`, or open Actions > build-windows > Run workflow.
- The `test` job (Linux, `python -m pytest -q`) must pass first; then the
  `windows` job builds, smoke-tests and reports.
- Smoke tests: the frozen `matnyab-cli.exe selftest` must report ok, then
  `MatnYab.exe --smoke` runs offscreen, then the installer is installed silently
  into a temporary folder, the INSTALLED `matnyab-cli.exe selftest` runs, and the
  installer is uninstalled again.

Outputs:

- Workflow run > Artifacts > `matnyab-windows-<n>`: `MatnYab-Setup-<version>.exe`
  (installer, per-user by default), `MatnYab-<version>-portable.zip` (unzip and
  run `MatnYab\MatnYab.exe`), `size-report.txt`, `build-report.json`, `log-tail.txt`.
- Branch `results`, folder `app/<run_id>/`: `build-report.json` (version, sizes,
  Tesseract version, selftest output, timings, outcome of every step) and a log
  tail. These are written even when a step fails.

Bundle layout (PyInstaller onedir, `packaging/matnyab.spec`): `MatnYab.exe`
(GUI), `matnyab-cli.exe` (console), and a shared `_internal` folder holding
`model/`, `assets/fonts/`, `samples/`, `tesseract/` (tesseract.exe plus its DLLs,
no tessdata) and the Python/Qt runtime. `matnyab.paths.app_root()` is that
`_internal` folder when frozen. The version comes from `src/matnyab/__init__.py`.

Build locally on Windows (PowerShell, Python 3.12, Tesseract 5 and Inno Setup 6
installed, or let the script run `choco install` for them):

```
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
# -SkipInstaller builds only the bundle and the zip; -TesseractDir "C:\Program Files\Tesseract-OCR"
```

Linux dry run (proves data collection and the frozen path logic, not a Windows build):

```
VENV=.venv sh packaging/linux_dry_run.sh /some/empty/folder
```

The installer wizard is English with Persian added on a best-effort basis: the
build downloads `Farsi.isl` from the Inno Setup repository and falls back to
English if that fails. No file association is registered.

### SmartScreen

The executables and the installer are not code-signed. On first run Windows
SmartScreen shows "Windows protected your PC": click "More info", then "Run
anyway". The warning fades only with a code-signing certificate (an EV
certificate removes it at once, a standard one builds reputation over time).

### Publishing a Release

1. Make sure `__version__` in `src/matnyab/__init__.py` is the version to ship.
2. Tag and push: `git tag v0.1.0 && git push origin v0.1.0` (this runs the workflow).
3. When the run is green, download the artifact, open GitHub > Releases > Draft a
   new release, choose the tag, attach the installer and the portable zip, publish.

### Signing later

Buy or obtain a code-signing certificate, store it as a repository secret (for
example a base64 PFX and its password), and enable the commented step
"Sign the executables" in the workflow. Sign `MatnYab.exe` and `matnyab-cli.exe`
before the installer is compiled (build with `-SkipInstaller`, sign, then compile
`packaging\matnyab.iss` with ISCC), and sign the installer afterwards with
`signtool sign /fd SHA256 /tr <timestamp-url> /td SHA256`.
