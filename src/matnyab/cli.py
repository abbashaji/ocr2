"""Command line: ``python -m matnyab.cli recognize IMAGE`` and ``selftest``."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence

from matnyab import paths
from matnyab.api import OcrOptions, OcrResult

SELFTEST_MIN_ACCURACY = 0.98


def _out(text: str) -> None:
    """Write UTF-8 to stdout regardless of the console code page (Windows)."""
    sys.stdout.buffer.write(text.encode("utf-8"))
    sys.stdout.buffer.flush()


def _err(text: str) -> None:
    sys.stderr.buffer.write((text + "\n").encode("utf-8", "replace"))
    sys.stderr.buffer.flush()


def _add_engine_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--model-dir", help="folder with fas.traineddata")
    p.add_argument("--tesseract", help="path of the tesseract executable")
    p.add_argument("--workers", type=int, help="parallel Tesseract calls (default: min(8, CPUs))")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="matnyab.cli", description="MatnYab offline Persian OCR")
    sub = parser.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("recognize", help="print the text of an image")
    rec.add_argument("image")
    rec.add_argument("--mode", choices=["auto", "raw", "lex"], default="auto")
    rec.add_argument("--json", action="store_true", help="print one JSON object instead of the text")
    _add_engine_args(rec)
    st = sub.add_parser("selftest", help="OCR the bundled clean sample and check its accuracy")
    _add_engine_args(st)
    return parser


def _make_engine(args: argparse.Namespace):  # type: ignore[no-untyped-def]
    from matnyab.engine.tesseract_engine import TesseractEngine

    return TesseractEngine(model_dir=args.model_dir, tesseract=args.tesseract)


def _result_json(res: OcrResult) -> dict[str, Any]:
    return {
        "text": res.text,
        "mode_used": res.mode_used,
        "low_confidence_fraction": res.low_confidence_fraction,
        "elapsed_s": res.elapsed_s,
        "lines": [
            {"text": ln.text, "confidence": ln.confidence, "box": list(ln.box) if ln.box else None}
            for ln in res.lines
        ],
    }


def _cmd_recognize(args: argparse.Namespace) -> int:
    if args.workers is not None and args.workers < 1:
        _err("error: --workers must be >= 1")
        return 2
    if not Path(args.image).is_file():
        _err(f"error: image not found: {args.image}")
        return 1
    engine = _make_engine(args)
    try:
        res = engine.recognize(args.image, OcrOptions(mode=args.mode, workers=args.workers))
    finally:
        engine.close()
    if args.json:
        _out(json.dumps(_result_json(res), ensure_ascii=False) + "\n")
    else:
        _out(res.text + "\n")
    return 0


def _cmd_selftest(args: argparse.Namespace) -> int:
    from matnyab.engine import scoring

    if args.workers is not None and args.workers < 1:
        _err("error: --workers must be >= 1")
        return 2
    samples = paths.samples_dir()
    image, ref_file = samples / "client_clean.png", samples / "client_ref.txt"
    for f in (image, ref_file):
        if not f.is_file():
            _err(f"error: sample not found: {f}")
            return 1
    ref = ref_file.read_text(encoding="utf-8")
    engine = _make_engine(args)
    try:
        res = engine.recognize(image, OcrOptions(workers=args.workers))
        version = engine.tesseract_version
    finally:
        engine.close()
    acc = scoring.word_accuracy(ref, scoring.strip_markers(res.text))
    ok = acc >= SELFTEST_MIN_ACCURACY
    _out(json.dumps({
        "ok": ok, "word_accuracy": acc, "mode_used": res.mode_used,
        "elapsed_s": res.elapsed_s, "tesseract": version,
    }, ensure_ascii=False) + "\n")
    return 0 if ok else 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse: 2 = usage error, 0 = --help
        return exc.code if isinstance(exc.code, int) else 2
    try:
        if args.command == "recognize":
            return _cmd_recognize(args)
        return _cmd_selftest(args)
    except (FileNotFoundError, RuntimeError, OSError) as exc:
        _err(f"error: {exc}")
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary: report, exit 1
        _err(f"error: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
