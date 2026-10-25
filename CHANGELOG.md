# Changelog

All notable changes to MatnYab. Versions follow `src/matnyab/__init__.py`.

## Unreleased (project v004: QA and release hardening)

### Fixed
- History drawer: the list showed a horizontal scrollbar and a corner box because the rows were
  wider than the list viewport once the vertical scrollbar appeared. Rows now follow the viewport
  width and horizontal scrolling is off (regression test `tests/e2e/test_ui_regressions.py`).
- `pytest` exited with code 139 (segmentation fault at interpreter exit) after all tests had passed,
  caused by a `QMimeData` left on the offscreen clipboard. The e2e conftest now clears the clipboard
  at session end (see `docs/DEVELOPER.md`, section 2, for the remaining limitation).

### Added
- End-to-end tests with the real engine and UI (`tests/e2e`): accuracy gate (>= 98 % clean, >= 93 % low
  quality), speed gate (<= 10 s on 2 CPUs), real-window test (copy, TXT, DOCX with `w:bidi`, history,
  clean shutdown) and robustness tests (6000x4000 page, tiny images, non-image files, unwritable
  folder, Persian and space paths).
- Screenshot generator with real results (`tests/e2e/review_shots.py`): light/dark, queue, error cards,
  150 % and 200 % scaling.
- Documentation: Persian user guide (`docs/USER_GUIDE_fa.md`), developer guide (`docs/DEVELOPER.md`).

## 0.1.0 (project v003)

- Tesseract 5 engine with the fine-tuned `fas` model, per-line multi-scale pipeline, lexicon correction,
  citation-marker removal, CLI (`recognize`, `selftest`).
- PySide6 right-to-left Persian UI: drag and drop, clipboard paste, batch queue, side-by-side image and
  text, low-confidence highlighting, history, light/dark themes, TXT/DOCX export.
- PyInstaller + Inno Setup packaging and the Windows GitHub Actions workflow.
