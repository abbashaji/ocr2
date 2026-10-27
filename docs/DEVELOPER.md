# MatnYab developer guide

MatnYab is an offline Windows desktop app that converts Persian images to editable text. This guide
covers the architecture, the frozen contracts, and how to test, build and release. User-facing
documentation is in `docs/USER_GUIDE_fa.md` (Persian).

## 1. Architecture

```
image  ->  engine (Tesseract pipeline)  ->  OcrResult  ->  UI (editor + image overlay)  ->  services (copy / TXT / DOCX / history)
```

| Package | Responsibility |
|---|---|
| `src/matnyab/api.py` | **Frozen contracts**: `OcrEngine`, `OcrOptions`, `OcrResult`, `LineResult`, `WordResult`, `CancelToken`, `Cancelled`, `AppSettings`, `HistoryItem`, `SettingsStore`, `HistoryStore`. |
| `src/matnyab/paths.py` | **Frozen**: resource lookup for a source tree and a PyInstaller build (`app_root`, `model_dir`, `tesseract_cmd`, `fonts_dir`, `samples_dir`, `data_dir`). |
| `src/matnyab/engine/` | OCR. `create_engine()` returns `TesseractEngine`, or `StubEngine` when `MATNYAB_ENGINE=stub`. |
| `src/matnyab/services/` | Settings (JSON), history (SQLite, newest first, 200 items), TXT/DOCX export (atomic writes), digit and Arabic-letter normalisation. |
| `src/matnyab/ui/` | PySide6 widgets, Persian strings only in `strings.py`, shortcuts only in `shortcuts.py`, colours only in `theme.py`. |
| `src/matnyab/cli.py` | `recognize IMAGE [--mode auto|raw|lex] [--json]` and `selftest`. |
| `packaging/`, `.github/workflows/build-windows.yml` | PyInstaller spec, Inno Setup script, Windows CI. |
| `legacy/`, `model/`, `samples/` | Research code, the fine-tuned `fas.traineddata`, the client samples. Treated as read-only data. |

### Engine pipeline (`engine/tesseract_engine.py`)

1. `imageprep.prepare`: EXIF rotation, grey conversion, dark-mode images are inverted.
2. `segment`: text lines are found and cropped.
3. Every line is rendered at 7 heights (`TARGETS`) and each is sent to `tesseract --psm 7` (hOCR).
   That is `lines x 7` independent subprocess calls (about 67 ms each), run in a thread pool of
   `min(8, CPUs)` workers. This is why recognition time scales with the CPU count.
4. Per line, the *medoid* reading (smallest summed edit distance to the others) is kept. Scales whose
   text has unbalanced square brackets (a digit read as `]`, e.g. `۹۲` -> `۹]`) are skipped while at
   least one scale read the line without one (`_pick_scale`).
5. Mode `auto` picks `lex` when at least 10 % of at least 20 words have confidence < 80, otherwise
   `raw`. `lex` corrects words with a Persian lexicon; it never shortens a word (a dropped letter was
   wrong more often than right on real screenshots, see CHANGELOG). Citation markers like `[12]` are removed
   unless `OcrOptions.keep_markers`.
6. Progress is reported through the `progress(fraction, stage)` callback; cancelling a `CancelToken`
   stops the run promptly (`Cancelled`).

### UI threading

`ui/runner.py`: one image at a time on a `QThreadPool` (1 thread); the GUI only receives Qt signals.
Image decoding and thumbnails run on a separate pool. Closing the window cancels the job and closes
the engine (the engine's worker threads are joined).

### Environment variables

| Variable | Effect |
|---|---|
| `MATNYAB_ENGINE=stub` | use the fast fake engine (default for `tests/ui`, `tests/services`, contract tests) |
| `MATNYAB_MODEL_DIR` | folder holding `fas.traineddata` |
| `MATNYAB_TESSERACT` | path of the tesseract executable |
| `MATNYAB_DATA_DIR` | settings, history, `ui_state.json`, `matnyab.log` (always set a fresh one for test runs) |
| `MATNYAB_REDUCE_MOTION=1` | disable animations (tests, screenshots) |
| `QT_QPA_PLATFORM=offscreen` | headless Qt |
| `QT_SCALE_FACTOR=1.5` / `2` | simulate 150 % / 200 % display scaling |

## 2. Tests

```
python -m venv .venv && .venv/bin/pip install -e .[dev] pyyaml     # Windows: .venv\Scripts\pip
sudo apt-get install tesseract-ocr                                  # needed by engine and e2e tests
export MATNYAB_DATA_DIR=$(mktemp -d)
.venv/bin/python -m pytest -q            # whole suite, about 6 minutes on 1 CPU
```

| Folder | What it covers | Engine |
|---|---|---|
| `tests/test_contracts.py`, `tests/services` | contracts, settings, history, export, text helpers | stub |
| `tests/engine` | pipeline units, golden output identical to the legacy pipeline, CLI contracts | real |
| `tests/ui` | window behaviour with deterministic stub text | stub |
| `tests/packaging` | static checks of the spec, Inno script and workflow | none |
| `tests/e2e` | the release gates below | **real** |

`tests/e2e` (the conftest removes `MATNYAB_ENGINE`, gives every test a fresh data folder):

- `test_accuracy_gate.py` (marker `slow`): mode `auto`, after citation-marker stripping, three scores per
  sample. The build fails if any is below its threshold:

  | sample | word accuracy | numbers F1 | punctuation F1 |
  |---|---|---|---|
  | `client_clean.png` threshold | 0.98 | 0.95 | 0.98 |
  | `client_clean.png` measured | 1.0000 | 1.0000 | 1.0000 |
  | `client_low.jpg` threshold | 0.93 | 0.66 | 0.95 |
  | `client_low.jpg` measured | 0.9762 | 0.6667 | 0.9583 |

  Numbers F1 and punctuation F1 are `engine/scoring.numbers_f1` / `punct_f1` (`2*LCS/(len(ref)+len(hyp))`,
  mirroring `ocr/ft/evaluate.py`). Numbers are compared with digits folded to ASCII and `٫ ٬` folded to
  `. ,`, so a wrong separator (`۱٫۶۴` -> `۱،۶۴`), a lost digit or an extra number all cost. The low-quality
  numbers F1 is 2/3 because of one known error (`۹۲` read as `۹۹۲`); a second damaged number fails the gate.
- `test_speed_gate.py`: `client_clean.png` in <= 10 s on 2 CPUs (the process is pinned to 2 CPUs when
  more exist; on a single-CPU machine the limit is scaled by 2/CPUs because the work is CPU bound).
- `test_ui_real.py`: real window + real engine + real stores: open, recognise, copy, save TXT and DOCX
  (re-read, `w:bidi`), one history entry, clean shutdown without leaked threads.
- `test_robustness.py`: 6000x4000 page (progress, UI never stalls > 1 s, prompt cancel), 1-pixel and
  tiny images, non-image files (queue continues), unwritable save folder, Persian and space paths, CLI.
- `test_ui_regressions.py`: one test per defect found in the QA pass.
- `review_shots.py` (not a test): `python tests/e2e/review_shots.py --all` writes the real-result
  screenshots (light/dark, queue, error cards, 150 % and 200 %) to `docs/screenshots/`.

Notes: a test that hands a `QMimeData` to the offscreen clipboard (`tests/ui/test_window.py::
test_clipboard_paste_image_and_files`) makes PySide6 6.12 crash at interpreter exit (exit code 139) after
all tests pass. `tests/e2e/conftest.py` clears the clipboard in `pytest_sessionfinish`, which only runs when
`tests/e2e` is part of the session. Running `pytest tests/ui` alone still exits 139; move the hook to
`tests/conftest.py` to cover that.

Confidence display: the UI never shows a percentage for confidence. "اطمینان" is Tesseract's own mean word
score (a clean page averages ~89, and per-word scores barely predict correctness), which is a different
metric from the word accuracy above. Showing both as percentages invites the wrong comparison, so only a
label (بالا / متوسط / کم; bands in `models.CONF_HIGH/CONF_MID`) and the suspicious-word count are shown.

Numbers and punctuation: the word accuracy compares letters and digits only; it ignores punctuation, the
ezafe mark and decimal separators, which is why the gate also checks numbers F1 and punctuation F1 (the
ezafe mark `ٔ` is still invisible to every metric: the model never outputs it). Marker removal (`engine/markers.py`) judges a word with a square bracket
as before; a word without one only loses clearly raised digits, so a plain number (`۳۱`, `۱٫۶۴`) survives.

## 3. Build

Windows installer, portable zip and bundle are built by `.github/workflows/build-windows.yml` on a
`windows-2022` runner (push to `app/**`, push a `v*` tag, or run the workflow manually). The Linux `test`
job (`python -m pytest -q`) must pass first. Local build: see `README.md`
(`packaging\build_windows.ps1`). The version is `__version__` in `src/matnyab/__init__.py`.

## 4. Release checklist

1. `python -m pytest -q` is green with the real engine (nothing skipped except Windows-only tests).
2. Bump `__version__`; add a `CHANGELOG.md` entry.
3. Regenerate screenshots (`review_shots.py --all`) if the UI changed, look at each one, update the guide.
4. Push a `v*` tag; wait for the `windows` job (frozen `selftest`, `--smoke`, silent install/uninstall).
5. On a clean Windows machine: install, open both samples, copy, save TXT and DOCX and open the DOCX in
   Word (right-to-left paragraphs), check 125/150/200 % scaling, dark mode, drag and drop from Explorer.
   These cannot be verified on Linux.
6. Check bundle size (target 120 MB), SmartScreen wording in the guide (executables are unsigned).
7. Attach `MatnYab-Setup-<version>.exe` and the portable zip to the release.

## 5. Conventions

- Code, comments, docs and commit text in English; end-user strings in Persian only in `ui/strings.py`.
- Never change `api.py` or `paths.py` without a scaffold task; propose the change instead.
- Keep each file's line endings. Every defect fix gets a regression test.
