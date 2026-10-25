"""OCR engine package. Use ``create_engine`` rather than importing engines."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

from matnyab.api import OcrEngine

__all__ = ["create_engine"]


def create_engine(
    model_dir: Optional[Union[str, Path]] = None,
    tesseract: Optional[Union[str, Path]] = None,
) -> OcrEngine:
    """Return a StubEngine if MATNYAB_ENGINE=stub, else a TesseractEngine."""
    if os.environ.get("MATNYAB_ENGINE", "").strip().lower() == "stub":
        from matnyab.engine.stub import StubEngine

        return StubEngine()
    try:
        from matnyab.engine.tesseract_engine import TesseractEngine
    except ModuleNotFoundError as exc:
        if exc.name == "matnyab.engine.tesseract_engine":
            raise RuntimeError(
                "The real OCR engine (matnyab.engine.tesseract_engine) is not "
                "available in this build; set MATNYAB_ENGINE=stub to use the stub."
            ) from exc
        raise
    return TesseractEngine(model_dir=model_dir, tesseract=tesseract)
