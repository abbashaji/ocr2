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


def finalize_tok(t: str) -> str:
    """Glued hamza at word end -> Persian comma; Latin ',' after a letter and '?' -> Persian."""
    t = _GLUED_HAMZA.sub("،", t)
    t = _LATIN_COMMA.sub("،", t)
    return t.replace("?", "؟")


def restore_placeholders(t: str) -> str:
    """The fine-tuned model emits ``, . #`` for ``، ٬ ٫ ٪``; restore them by context."""
    t = _DECIMAL.sub("٫", t)          # 1.64 -> ۱٫۶۴
    t = _THOUSANDS.sub("٬", t)        # 12,345 -> thousands separator
    t = t.replace(",", "،")
    return t.replace("#", "٪")
