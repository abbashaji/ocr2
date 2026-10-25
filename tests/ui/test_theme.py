import re
from pathlib import Path

import pytest

from matnyab.ui import theme
from matnyab.ui.format import fa_digits, fa_percent, fa_seconds, fa_datetime, gregorian_to_jalali
from matnyab.ui.strings import S

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


@pytest.mark.parametrize("name,tokens", [("light", theme.LIGHT), ("dark", theme.DARK)])
def test_text_pairs_reach_aa(name, tokens):
    for fg, bg in theme.TEXT_PAIRS:
        ratio = theme.contrast_ratio(tokens[fg], tokens[bg])
        assert ratio >= 4.5, f"{name}: {fg} on {bg} = {ratio:.2f}"


@pytest.mark.parametrize("name,tokens", [("light", theme.LIGHT), ("dark", theme.DARK)])
def test_ui_pairs_reach_3_to_1(name, tokens):
    for fg, bg in theme.UI_PAIRS:
        ratio = theme.contrast_ratio(tokens[fg], tokens[bg])
        assert ratio >= 3.0, f"{name}: {fg} vs {bg} = {ratio:.2f}"


def test_token_tables_have_same_keys_and_accents():
    assert set(theme.LIGHT) == set(theme.DARK)
    assert theme.LIGHT["accent"].lower() == "#2f6fed"
    assert theme.DARK["accent"].lower() == "#7aa2ff"
    assert theme.SPACING == (4, 8, 12, 16, 24, 32)
    assert (theme.RADIUS_SM, theme.RADIUS_MD, theme.RADIUS_LG) == (8, 12, 16)


@pytest.mark.parametrize("tokens", [theme.LIGHT, theme.DARK])
def test_qss_has_no_raw_hex_outside_token_table(tokens):
    assert not HEX.findall(theme.QSS_TEMPLATE), "template must use @token@ placeholders only"
    qss = theme.build_qss(tokens)
    allowed = {v.lower() for v in tokens.values()}
    found = {h.lower() for h in HEX.findall(qss)}
    assert found and found <= allowed
    assert "@" not in qss and "$" not in qss


def test_no_persian_literals_outside_strings_module():
    ui_dir = Path(theme.__file__).parent
    persian = re.compile(r"[؀-ۿ‌]")
    offenders = [p.name for p in ui_dir.glob("*.py")
                 if p.name != "strings.py" and persian.search(p.read_text(encoding="utf-8"))]
    assert offenders == []


def test_fa_digits():
    assert fa_digits("0123456789") == "۰۱۲۳۴۵۶۷۸۹"
    assert fa_digits("٣ and 7") == "۳ and ۷"
    assert fa_digits(42) == "۴۲"
    assert fa_percent(91.4) == "۹۱" + S.percent_sign
    assert fa_seconds(2.44) == "۲" + S.decimal_sep + "۴"


def test_jalali_dates():
    assert gregorian_to_jalali(2026, 3, 21) == (1405, 1, 1)
    assert gregorian_to_jalali(2026, 10, 24) == (1405, 8, 2)
    assert fa_datetime("2026-10-24T14:05:00") == "۲ آبان ۱۴۰۵، ۱۴:۰۵"


def test_all_icons_render(qapp):
    from PySide6.QtCore import QSize
    from matnyab.ui import icons

    for name in icons.ICON_NAMES:
        pm = icons.icon(name).pixmap(QSize(24, 24))
        assert not pm.isNull()
    assert not icons.app_icon().isNull()


def test_theme_manager_switches_live(qapp):
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QPalette, QColor

    m = theme.manager()
    m.set_mode("dark")
    assert m.is_dark and QApplication.palette().color(QPalette.Window) == QColor(theme.DARK["bg"])
    m.set_mode("light")
    assert not m.is_dark and QApplication.palette().color(QPalette.Window) == QColor(theme.LIGHT["bg"])
    m.set_mode("system")
