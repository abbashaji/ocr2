"""Real OCR engine: per-line multi-scale Tesseract pipeline (port of ``legacy/pipeline2.py``)."""

from __future__ import annotations

import concurrent.futures as cf
import math
import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, Optional, Sequence, Union

from PIL import Image
from rapidfuzz.distance import Levenshtein as Lev

from matnyab import paths
from matnyab.api import (
    AUTO_LOW_FRACTION,
    AUTO_MIN_WORDS,
    LOW_CONFIDENCE_THRESHOLD,
    Box,
    CancelToken,
    Cancelled,
    ImageInput,
    LineResult,
    ModeUsed,
    OcrOptions,
    OcrResult,
    ProgressCallback,
    Stage,
    WordResult,
)

from . import imageprep, lexicon, scoring, segment
from .hocr import parse_hocr
from .markers import Token, clean_words_conf
from .textfix import finalize_tok, restore_placeholders

__all__ = ["TesseractEngine", "TARGETS", "PAD", "choose_mode"]

TARGETS: tuple[int, ...] = (28, 32, 36, 40, 44, 48, 56)  # line heights (px) fed to Tesseract
PAD = 12                                                  # white padding around each scaled line
STAGES: tuple[Stage, ...] = ("preparing", "segmenting", "recognizing", "correcting", "done")
_CALL_TIMEOUT_S = 300.0
_POLL_S = 0.05
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0

# One scale's result for one line: tokens with boxes in the scaled+padded image, plus the
# transform back to source pixels: (x scale, y scale, crop top offset).
_Unit = tuple[list[Token], tuple[float, float, int]]


def choose_mode(confidences: Sequence[float]) -> ModeUsed:
    """``lex`` when >= 10% of at least 20 words have confidence < 80, else ``raw``."""
    if len(confidences) < AUTO_MIN_WORDS:
        return "raw"
    low = sum(c < LOW_CONFIDENCE_THRESHOLD for c in confidences) / len(confidences)
    return "lex" if low >= AUTO_LOW_FRACTION else "raw"


def _unbalanced_brackets(text: str) -> bool:
    """True when ``[`` and ``]`` do not pair up, e.g. a digit read as ``]`` (``۹۲`` -> ``۹]``).

    Citation markers that survive (``[۱۲]``) are balanced, so they do not trigger this.
    """
    return text.count("[") != text.count("]")


def _pick_scale(texts: Sequence[str]) -> int:
    """Index of the scale to keep for one line: the medoid, preferring readings with balanced brackets.

    A stray bracket is a misread glyph (the last digit of a number is often read as ``]``). When at least
    one scale read the line without one, the medoid is taken among those scales only.
    """
    ok = [i for i, t in enumerate(texts) if not _unbalanced_brackets(t)]
    if not ok or len(ok) == len(texts):
        return _medoid(texts)
    return ok[_medoid([texts[i] for i in ok])]


def _norm(s: str) -> str:
    return " ".join(scoring.base(s).split())


def _medoid(texts: Sequence[str]) -> int:
    """Index of the text with the smallest summed Levenshtein distance to all others."""
    n = [_norm(t) for t in texts]
    return min(range(len(n)), key=lambda i: sum(Lev.distance(n[i], n[j]) for j in range(len(n))))


def _resolve_tesseract(tesseract: Optional[Union[str, Path]]) -> str:
    if tesseract is None:
        found = paths.tesseract_cmd()
        if not found:
            raise FileNotFoundError(
                "Tesseract executable not found (not bundled and not on PATH); "
                "set MATNYAB_TESSERACT or pass tesseract=<path>"
            )
        return str(found)
    cmd = str(tesseract)
    if os.path.isfile(cmd):
        return cmd
    if os.sep not in cmd and (os.altsep is None or os.altsep not in cmd):
        which = shutil.which(cmd)
        if which:
            return which
    raise FileNotFoundError(f"Tesseract executable not found: {cmd}")


class TesseractEngine:
    """Implements :class:`matnyab.api.OcrEngine` with the Tesseract command-line tool."""

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        tesseract: Optional[Union[str, Path]] = None,
    ) -> None:
        mdir = Path(model_dir) if model_dir is not None else paths.model_dir()
        model_file = mdir / "fas.traineddata"
        if not mdir.is_dir():
            raise FileNotFoundError(f"Model directory not found: {mdir}")
        if not model_file.is_file():
            raise FileNotFoundError(f"Model file not found: {model_file}")
        self.model_dir = mdir
        self.tesseract = _resolve_tesseract(tesseract)
        self._env = dict(os.environ, OMP_THREAD_LIMIT="1")
        self.tesseract_version = self._read_version()
        self._pool: Optional[cf.ThreadPoolExecutor] = None
        self._pool_size = 0
        self._pool_lock = threading.Lock()

    # ------------------------------------------------------------------ setup ---

    def _read_version(self) -> str:
        try:
            proc = subprocess.run(
                [self.tesseract, "--version"], capture_output=True, env=self._env,
                timeout=60, creationflags=_NO_WINDOW,
            )
        except FileNotFoundError as exc:
            raise FileNotFoundError(f"Tesseract executable not found: {self.tesseract}") from exc
        except OSError as exc:
            raise RuntimeError(f"Cannot run Tesseract at {self.tesseract}: {exc}") from exc
        text = (proc.stdout or proc.stderr).decode("utf-8", "replace")
        if proc.returncode != 0:
            raise RuntimeError(f"Tesseract --version failed: {text[:300]}")
        lines = text.strip().splitlines()
        return lines[0].strip() if lines else "tesseract (unknown version)"

    def _executor(self, workers: int) -> cf.ThreadPoolExecutor:
        with self._pool_lock:
            if self._pool is None or self._pool_size < workers:
                old = self._pool
                self._pool = cf.ThreadPoolExecutor(max_workers=workers, thread_name_prefix="matnyab-ocr")
                self._pool_size = workers
                if old is not None:
                    old.shutdown(wait=False)
            return self._pool

    def close(self) -> None:
        """Shut the worker pool down. The engine can be used again afterwards."""
        with self._pool_lock:
            pool, self._pool, self._pool_size = self._pool, None, 0
        if pool is not None:
            pool.shutdown(wait=True)

    def __enter__(self) -> "TesseractEngine":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- one call ---

    def _tess_words(self, im: Image.Image, tmpdir: str, name: str) -> list:
        path = os.path.join(tmpdir, name + ".png")
        im.save(path, compress_level=1)
        cmd = [
            self.tesseract, path, "-", "--tessdata-dir", str(self.model_dir), "-l", "fas",
            "--psm", "7", "-c", "hocr_char_boxes=1", "-c", "tessedit_create_hocr=1",
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, env=self._env, timeout=_CALL_TIMEOUT_S,
                creationflags=_NO_WINDOW,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Tesseract timed out after {_CALL_TIMEOUT_S:.0f}s") from exc
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
        if proc.returncode != 0:
            raise RuntimeError(
                f"Tesseract failed (exit {proc.returncode}): "
                + proc.stderr.decode("utf-8", "replace")[:300]
            )
        return parse_hocr(proc.stdout.decode("utf-8", "replace"))

    def _run_unit(
        self, crop: Image.Image, top: int, target: int, tmpdir: str, name: str, remove_markers: bool
    ) -> _Unit:
        s = target / crop.height
        scaled = segment.scale(crop, s)
        sx = scaled.width / crop.width
        sy = scaled.height / crop.height
        words = self._tess_words(segment.pad_white(scaled, PAD), tmpdir, name)
        return clean_words_conf(words, remove_markers), (sx, sy, top)

    # -------------------------------------------------------------- recognise ---

    def recognize(
        self,
        image: ImageInput,
        options: OcrOptions = OcrOptions(),
        progress: Optional[ProgressCallback] = None,
        cancel: Optional[CancelToken] = None,
    ) -> OcrResult:
        t0 = time.perf_counter()
        last = [0.0]

        def report(frac: float, stage: Stage) -> None:
            frac = max(last[0], min(1.0, frac))  # never go backwards
            last[0] = frac
            if progress is not None:
                progress(frac, stage)

        def check() -> None:
            if cancel is not None:
                cancel.raise_if_cancelled()

        report(0.0, "preparing")
        check()
        want_lex = options.mode == "lex"
        preload = threading.Thread(target=lexicon.load, daemon=True) if want_lex else None
        if preload is not None:
            preload.start()

        gray, size = imageprep.prepare(image)
        check()
        report(0.05, "segmenting")
        crops = [] if imageprep.is_blank(gray) else segment.crops(gray, segment.segment_lines(gray))
        check()

        # ---- recognising: one work unit per (line, scale) ----
        n_lines, n_scales = len(crops), len(TARGETS)
        total = n_lines * n_scales
        report(0.05, "recognizing")
        grid: list[list[Optional[_Unit]]] = [[None] * n_scales for _ in range(n_lines)]
        if total:
            workers = max(1, options.workers or min(8, os.cpu_count() or 2))
            self._run_units(crops, grid, workers, not options.keep_markers, report, cancel)
        check()

        # ---- choose the medoid scale per line ----
        chosen: list[tuple[list[Token], tuple[float, float, int]]] = []
        for row in grid:
            units = [u for u in row if u is not None]
            texts = [" ".join(t.text for t in toks) for toks, _ in units]
            chosen.append(units[_pick_scale(texts)])

        confs = [t.conf for toks, _ in chosen for t in toks]
        mode_used: ModeUsed = choose_mode(confs) if options.mode == "auto" else options.mode  # type: ignore[assignment]

        report(0.92, "correcting")
        if preload is not None:
            preload.join()
        cfg = lexicon.RAW_CONFIG if mode_used == "raw" else lexicon.LEX_CONFIG
        lines: list[LineResult] = []
        for k, ((toks, (sx, sy, top)), (crop, _)) in enumerate(zip(chosen, crops)):
            check()
            words = [
                WordResult(
                    restore_placeholders(lexicon.fix_final_kaf(
                        lexicon.correct_tok(finalize_tok(t.text), t.conf, **cfg))),
                    t.conf,
                    self._to_source(t.box, sx, sy, top, size),
                )
                for t in toks
            ]
            if k == len(chosen) - 1 and words and words[-1].text.endswith("،"):
                # A text cannot end with a comma; at low resolution Tesseract reads the final full stop as one.
                tail = words[-1]  # not ``last``: that name belongs to the progress reporter above
                words[-1] = WordResult(tail.text[:-1] + ".", tail.confidence, tail.box)
            band = (0, top, crop.width, top + crop.height)
            lines.append(self._line(words, band, size))

        n_words = len(confs)
        low = sum(c < LOW_CONFIDENCE_THRESHOLD for c in confs) / n_words if n_words else 0.0
        result = OcrResult(
            text="\n".join(ln.text for ln in lines),
            lines=tuple(lines),
            mode_used=mode_used,
            low_confidence_fraction=low,
            elapsed_s=time.perf_counter() - t0,
            image_size=size,
        )
        report(1.0, "done")
        return result

    def _run_units(
        self,
        crops: list[tuple[Image.Image, int]],
        grid: list[list[Optional[_Unit]]],
        workers: int,
        remove_markers: bool,
        report: Callable[[float, Stage], None],
        cancel: Optional[CancelToken],
    ) -> None:
        pool = self._executor(workers)
        jobs = [(i, k) for i in range(len(crops)) for k in range(len(TARGETS))]
        total = len(jobs)
        pending: dict[cf.Future, tuple[int, int]] = {}
        next_job = done = 0
        error: Optional[BaseException] = None
        cancelled = False
        with tempfile.TemporaryDirectory(prefix="matnyab_") as tmp:
            while True:
                if cancel is not None and cancel.cancelled:
                    cancelled = True
                if not cancelled and error is None:
                    while next_job < total and len(pending) < workers:
                        i, k = jobs[next_job]
                        crop, top = crops[i]
                        fut = pool.submit(
                            self._run_unit, crop, top, TARGETS[k], tmp, f"l{i}_s{k}", remove_markers
                        )
                        pending[fut] = (i, k)
                        next_job += 1
                if not pending:
                    break
                finished, _ = cf.wait(pending, timeout=_POLL_S, return_when=cf.FIRST_COMPLETED)
                for fut in finished:
                    i, k = pending.pop(fut)
                    try:
                        grid[i][k] = fut.result()
                    except BaseException as exc:  # noqa: BLE001 - re-raised below
                        if error is None:
                            error = exc
                        continue
                    done += 1
                    if error is None and not cancelled:
                        report(0.05 + 0.85 * done / total, "recognizing")
        if error is not None:
            raise error
        if cancelled:
            raise Cancelled()

    # ----------------------------------------------------------------- boxes ---

    @staticmethod
    def _to_source(
        box: Optional[tuple[int, int, int, int]], sx: float, sy: float, top: int, size: tuple[int, int]
    ) -> Box:
        """Scaled+padded image coordinates -> source pixels (clamped to the image)."""
        if box is None:
            return None
        w, h = size
        x0 = max(0, min(w - 1, math.floor((box[0] - PAD) / sx)))
        y0 = max(0, min(h - 1, math.floor((box[1] - PAD) / sy) + top))
        x1 = max(x0 + 1, min(w, math.ceil((box[2] - PAD) / sx)))
        y1 = max(y0 + 1, min(h, math.ceil((box[3] - PAD) / sy) + top))
        return (x0, y0, x1, y1)

    @staticmethod
    def _line(words: list[WordResult], band: tuple[int, int, int, int], size: tuple[int, int]) -> LineResult:
        boxes = [w.box for w in words if w.box is not None]
        if boxes:
            box: Box = (
                min(b[0] for b in boxes), min(b[1] for b in boxes),
                max(b[2] for b in boxes), max(b[3] for b in boxes),
            )
        else:
            box = (band[0], band[1], min(size[0], band[2]), min(size[1], band[3]))
        conf = sum(w.confidence for w in words) / len(words) if words else 0.0
        return LineResult(
            text=" ".join(w.text for w in words), confidence=conf, box=box, words=tuple(words)
        )
