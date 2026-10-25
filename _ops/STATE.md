# STATE
Name: matnyab
Version: 4
Return: full
Build: none (pure Python; `pip install -e .[dev]` in a venv)
Test: python -m pytest -q (needs tesseract on PATH; set a fresh MATNYAB_DATA_DIR; ~7.5 min on 1 CPU)
Toolchain: Python 3.12 (merge verified on 3.13), setuptools src layout, pytest (importlib import mode), tesseract 5.x; pyyaml optional for one packaging test
Baseline: green (v004: full suite 176 passed, exit 0, none skipped, fresh MATNYAB_DATA_DIR; gates: clean 99.11%, low 96.13%)

## Requirements
- Offline Windows desktop app (product name MatnYab, Persian: متن‌یاب) that converts Persian images (screenshots, photos of text) to editable text.
- Accuracy (client ad): word accuracy > 99% on clean full-size screenshots, > 90% on low-quality ones. Measured so far with the bundled model: 99.1% clean / 96.1% low on the client samples (samples/).
- UI language Persian (fa), right-to-left, Vazirmatn font, light/dark themes, top-tier UX: drag-drop, clipboard paste, batch queue, side-by-side image/text, low-confidence highlighting, export TXT/DOCX, copy.
- Core engine: Tesseract 5 (bundled model/fas.traineddata, fine-tuned) + per-line multi-scale pipeline, lexicon correction, citation-marker removal; fast (parallel across lines), cancelable, no network at runtime.
- Stack: Python 3.12, PySide6 (Qt Widgets), Pillow, numpy, rapidfuzz, wordfreq, python-docx; packaged with PyInstaller + Inno Setup on a GitHub Windows runner.
- All code, comments, commit text, docs and build steps in English; only the end-user UI strings are Persian.

## Roadmap (optional; [ ] todo, [x] done)
- [x] 01 scaffold: package layout, frozen contracts (api.py, paths.py), stub engine/services, test runner - Done when: `python -m pytest -q` is green
- [x] 02a engine, 02b ui, 02c packaging, 02d services (parallel group), 02m merge
- [x] 03 end-to-end QA, accuracy gate, UI screenshot review, docs

## Decisions and why
- Research code from the fine-tuning work lives in legacy/ (flat imports, tessdata path hacks); the engine branch ports it into src/matnyab/engine/.
- Folder names build/, dist/, target/, obj/, Binaries/ are excluded from snapshots by _ops/EXCLUDE.txt: never use them for source.

- api.py: confidences are 0..100; LineResult/OcrResult raise ValueError if the text invariants are violated. HistoryStore.list() is newest first; AppSettings is mutable, stores return copies.
- create_engine only maps a missing matnyab.engine.tesseract_engine to RuntimeError; other import errors propagate.
- tesseract_cmd() returns None when nothing is found.

- ui: UI strings only in ui/strings.py; shortcuts only in ui/shortcuts.py; colours only in ui/theme.py tokens. ui_state.json in data_dir() holds splitter sizes.
- services: TXT export is utf-8-sig + CRLF; docx works; services/_stub.py is kept only for contract tests (not re-exported).

## Known hazards / open issues
- Speed gate (<= 10 s clean sample, 2 CPUs) never measured on 2 CPUs: 1 CPU gives ~10.3 s (147 Tesseract calls x ~67 ms), so the test scales its limit by 2/CPUs below 2 CPUs.
- tests/ui alone exits 139 (PySide6 6.12 offscreen clipboard mime at exit); tests/e2e/conftest.py pytest_sessionfinish clears it only when e2e is in the session. Move it to tests/conftest.py.
- README.md still says GUI/CLI are placeholders and the engine is a stub: outdated, not changed (outside May change).
- Read-only save folder is tested with a real chmod only when not root; as root it uses a path below a file.
- Windows installer/exe, Inno script, real DPI/Explorer drag-drop and DOCX in Word are unverified; Windows bundle size target (120 MB) probably missed.
- Settings tests write to MATNYAB_DATA_DIR: always use a fresh temp dir for the full run.
- The sandbox is Linux: the Windows exe/installer cannot be built or run here; it is built by a GitHub Actions Windows job.

## History (newest first, last 8, one line each)
- v004: TASK 03 QA: tests/e2e (accuracy/speed gates, real UI, robustness, regressions), review_shots.py, docs (guide fa, DEVELOPER), CHANGELOG; fixed history drawer horizontal scrollbar and exit-139 clipboard crash
- v003: merged a,b,c,d: engine (Tesseract pipeline, CLI), PySide6 RTL UI, PyInstaller/Inno/CI packaging, real services; contract tests retargeted to _stub + real-services test; UI save test reads utf-8-sig; shots.py --real
- v002: TASK 01 scaffold: pyproject, api.py, paths.py, stub engine/services, placeholders, 20 contract tests
- v001: starting point (kit + legacy research pipeline + model + client samples + Vazirmatn fonts)
