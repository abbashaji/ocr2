"""Number, time and date formatting for the user (Persian digits, Jalali dates)."""

from __future__ import annotations

from datetime import datetime
from typing import Union

from matnyab.ui.strings import S

__all__ = [
    "fa_digits", "fa_number", "fa_percent", "fa_seconds", "fa_clock",
    "fa_datetime", "gregorian_to_jalali", "jalali_to_gregorian", "wrap_ltr",
]

_PERSIAN = "".join(chr(0x06F0 + i) for i in range(10))
_ARABIC_INDIC = "".join(chr(0x0660 + i) for i in range(10))
_TABLE = {ord("0123456789"[i]): _PERSIAN[i] for i in range(10)}
_TABLE.update({ord(_ARABIC_INDIC[i]): _PERSIAN[i] for i in range(10)})

LRI = "⁦"  # left-to-right isolate
PDI = "⁩"  # pop directional isolate


def fa_digits(text: Union[str, int, float]) -> str:
    """Replace ASCII and Arabic-Indic digits in ``text`` by Persian digits."""
    return str(text).translate(_TABLE)


def fa_number(value: int) -> str:
    return fa_digits(int(value))


def fa_percent(value: float) -> str:
    """``91.4`` -> Persian ``91`` plus the Persian percent sign."""
    return fa_digits(int(round(value))) + S.percent_sign


def fa_seconds(seconds: float) -> str:
    """Short duration for chips: one decimal below 10 s, whole seconds above."""
    seconds = max(0.0, float(seconds))
    if seconds < 10:
        text = f"{seconds:.1f}".replace(".", S.decimal_sep)
    else:
        text = str(int(round(seconds)))
    return fa_digits(text)


def fa_clock(seconds: float) -> str:
    """``mm:ss`` with Persian digits (for the elapsed-time field)."""
    total = max(0, int(seconds))
    return fa_digits(f"{total // 60:02d}:{total % 60:02d}")


def wrap_ltr(text: str) -> str:
    """Isolate a Latin fragment (a shortcut, a file name) inside RTL text."""
    return f"{LRI}{text}{PDI}"


def gregorian_to_jalali(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (
        365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
        - 80 + gd + g_d_m[gm - 1]
    )
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> tuple[int, int, int]:
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (
        365 * jy + (jy // 33) * 8 + ((jy % 33) + 3) // 4 + 78 + jd
        + ((jm - 1) * 31 if jm < 7 else ((jm - 7) * 30) + 186)
    )
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    leap = (gy % 4 == 0 and gy % 100 != 0) or gy % 400 == 0
    sal_a = (0, 31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
    gm = 0
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd


def fa_datetime(iso: str) -> str:
    """ISO 8601 timestamp -> Jalali date and time with Persian digits."""
    try:
        moment = datetime.fromisoformat(iso)
    except (TypeError, ValueError):
        return fa_digits(str(iso))
    if moment.tzinfo is not None:
        moment = moment.astimezone()
    jy, jm, jd = gregorian_to_jalali(moment.year, moment.month, moment.day)
    return fa_digits(
        S.date_format.format(
            d=jd, month=S.months[jm - 1], y=jy,
            hh=f"{moment.hour:02d}", mm=f"{moment.minute:02d}",
        )
    )
