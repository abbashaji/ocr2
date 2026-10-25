#!/bin/sh
# Linux dry run of the PyInstaller bundle: proves data collection and the
# frozen path logic. Not a Windows build. Usage: sh packaging/linux_dry_run.sh [OUT_DIR]
# Needs the project venv on PATH or $VENV (pip install -e .[build]) and tesseract.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
PY=${VENV:+$VENV/bin/}python
OUT=${1:-$(mktemp -d)}

TESS=${MATNYAB_TESSERACT:-$(command -v tesseract || true)}
[ -n "$TESS" ] || { echo "tesseract not found (set MATNYAB_TESSERACT)" >&2; exit 2; }
export MATNYAB_TESSERACT="$TESS"
export MATNYAB_CLI_ENTRY="$HERE/frozen_check.py"

cd "$ROOT"
"$PY" -m PyInstaller packaging/matnyab.spec --noconfirm --workpath "$OUT/work" --distpath "$OUT/dist"

BUNDLE="$OUT/dist/MatnYab"
echo "== size"
du -sm "$BUNDLE"
echo "== --paths (run with MATNYAB_TESSERACT unset so the bundled copy must be found)"
env -u MATNYAB_TESSERACT "$BUNDLE/matnyab-cli" --paths
echo "== selftest (placeholder CLI: failure is expected until the engine branch is merged)"
env -u MATNYAB_TESSERACT "$BUNDLE/matnyab-cli" selftest || echo "selftest exit code $?"
echo "bundle: $BUNDLE"
