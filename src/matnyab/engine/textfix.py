"""Pure text fixes applied after recognition (``finalize_tok``, ``restore_placeholders``)."""

from __future__ import annotations

import re

__all__ = ["finalize_tok", "restore_placeholders"]

_LET = "ء-يٱ-ۓ"
_D = "0-9۰-۹"

_GLUED_HAMZA = re.compile("(?<=[" + _LET + "])ء(?=[^" + _LET + "]*$)")
_LATIN_COMMA = re.compile("(?<=[" + _LET + "]),")
_DECIMAL = re.compile("(?<=[" + _D + r"])\.(?=[" + _D + "])")
_THOUSANDS = re.compile("(?<=[" + _D + r"]),(?=[" + _D + "]{3}(?![" + _D + "]))")
# A comma between digits followed by one or two digits cannot be a thousands separator: it is a decimal mark.
_DECIMAL_COMMA = re.compile("(?<=[" + _D + "])[,،](?=[" + _D + "]{1,2}(?![" + _D + "]))")
# A full stop glued before a comma never occurs in text ("خط.،"): the stop is a misread speck.
_STRAY_STOP = re.compile("(?<=[" + _LET + r"])\.(?=[,،])")
_ARABIC_INDIC = str.maketrans("٠١٢٣٤٥٦٧٨٩", "۰۱۲۳۴۵۶۷۸۹")
_BIDI_MARKS = str.maketrans("", "", "\u200e\u200f")


def finalize_tok(t: str) -> str:
    """Glued hamza at word end -> Persian comma; Latin ',' after a letter and '?' -> Persian.

    Also: Arabic-Indic digits -> Persian digits (the model is trained on Persian digits, so ``٩`` is a glitch)
    and invisible bidi marks are dropped (they are not in the training labels either).
    """
    t = t.translate(_ARABIC_INDIC).translate(_BIDI_MARKS)
    t = _GLUED_HAMZA.sub("،", t)
    t = _LATIN_COMMA.sub("،", t)
    return t.replace("?", "؟")


def restore_placeholders(t: str) -> str:
    """The fine-tuned model emits ``, . #`` for ``، ٬ ٫ ٪``; restore them by context."""
    t = _STRAY_STOP.sub("", t)        # خط.، -> خط،
    t = _DECIMAL.sub("٫", t)          # 1.64 -> ۱٫۶۴
    t = _DECIMAL_COMMA.sub("٫", t)    # ۱،۶۴ -> ۱٫۶۴ (two digits after: not a thousands group)
    t = _THOUSANDS.sub("٬", t)        # 12,345 -> thousands separator
    t = t.replace(",", "،")
    return t.replace("#", "٪")
