"""Modal dialogs: settings (live), shortcuts cheat-sheet, about, confirmations."""

from __future__ import annotations

import dataclasses
from typing import Callable, Optional

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit,
    QSlider, QVBoxLayout, QWidget,
)

import matnyab
from matnyab.api import AppSettings
from matnyab.ui import icons, shortcuts, theme
from matnyab.ui.format import fa_digits, wrap_ltr
from matnyab.ui.strings import S
from matnyab.ui.widgets import SegmentedControl, push_button

__all__ = [
    "SettingsDialog", "ShortcutsDialog", "AboutDialog", "ask_yes_no", "show_crash_dialog",
    "show_info",
]


def _style_box(box: QMessageBox) -> None:
    box.setLayoutDirection(Qt.RightToLeft)


def ask_yes_no(parent: Optional[QWidget], title: str, text: str,
               yes_text: str = S.dlg_yes_continue, no_text: str = S.dlg_cancel) -> bool:
    box = QMessageBox(parent)
    _style_box(box)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(text)
    yes = box.addButton(yes_text, QMessageBox.AcceptRole)
    no = box.addButton(no_text, QMessageBox.RejectRole)
    box.setDefaultButton(no)
    box.setEscapeButton(no)
    box.exec()
    return box.clickedButton() is yes


def show_info(parent: Optional[QWidget], title: str, text: str) -> None:
    box = QMessageBox(parent)
    _style_box(box)
    box.setIcon(QMessageBox.Information)
    box.setWindowTitle(title)
    box.setText(title)
    box.setInformativeText(text)
    box.addButton(S.dlg_ok, QMessageBox.AcceptRole)
    box.exec()


def show_crash_dialog(parent: Optional[QWidget], summary: str, details: str, log_file: str) -> None:
    box = QMessageBox(parent)
    _style_box(box)
    box.setIcon(QMessageBox.Critical)
    box.setWindowTitle(S.crash_title)
    box.setText(S.crash_title)
    box.setInformativeText(S.crash_msg + "\n\n" + S.crash_log_at.format(path=wrap_ltr(log_file)))
    box.setDetailedText(f"{summary}\n\n{details}")
    box.addButton(S.dlg_ok, QMessageBox.AcceptRole)
    box.exec()


class _Section(QWidget):
    def __init__(self, title: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.lay.setSpacing(theme.SP_2)
        head = QLabel(title)
        head.setProperty("role", "h3")
        self.lay.addWidget(head)


class SettingsDialog(QDialog):
    """Applies every change immediately through ``on_change(settings)``."""

    def __init__(self, settings: AppSettings, on_change: Callable[[AppSettings], None],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle(S.settings_title)
        self.setModal(True)
        self.setMinimumWidth(540)
        self._settings = dataclasses.replace(settings)
        self._on_change = on_change

        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_5, theme.SP_4, theme.SP_5, theme.SP_4)
        root.setSpacing(theme.SP_4)

        title = QLabel(S.settings_title)
        title.setProperty("role", "h2")
        root.addWidget(title)

        # appearance
        sec = _Section(S.set_theme)
        self.theme_ctl = SegmentedControl(
            [("system", S.theme_system), ("light", S.theme_light), ("dark", S.theme_dark)],
            access_name=S.set_theme)
        self.theme_ctl.set_value(self._settings.theme)
        sec.lay.addWidget(self.theme_ctl, 0, Qt.AlignLeading)
        root.addWidget(sec)

        # recognition mode
        sec = _Section(S.set_mode)
        self.mode_ctl = SegmentedControl(
            [("auto", S.mode_auto), ("raw", S.mode_raw), ("lex", S.mode_lex)], access_name=S.set_mode)
        self.mode_ctl.set_value(self._settings.mode)
        self.mode_desc = QLabel()
        self.mode_desc.setProperty("role", "muted")
        self.mode_desc.setWordWrap(True)
        self.mode_desc.setAccessibleName(S.set_mode)
        sec.lay.addWidget(self.mode_ctl, 0, Qt.AlignLeading)
        sec.lay.addWidget(self.mode_desc)
        root.addWidget(sec)

        # digits
        sec = _Section(S.set_digits)
        self.digits_ctl = SegmentedControl(
            [("keep", S.digits_keep), ("fa", S.digits_fa), ("en", S.digits_en)], access_name=S.set_digits)
        self.digits_ctl.set_value(self._settings.digit_style)
        self.digits_desc = QLabel()
        self.digits_desc.setProperty("role", "muted")
        self.digits_desc.setWordWrap(True)
        self.digits_desc.setAccessibleName(S.set_digits)
        sec.lay.addWidget(self.digits_ctl, 0, Qt.AlignLeading)
        sec.lay.addWidget(self.digits_desc)
        root.addWidget(sec)

        # normalise
        sec = _Section(S.set_section_text)
        self.normalize = QCheckBox(S.set_normalize)
        self.normalize.setChecked(self._settings.normalize_text)
        self.normalize.setAccessibleName(S.set_normalize)
        self.normalize.setAccessibleDescription(S.set_normalize_desc)
        nd = QLabel(S.set_normalize_desc)
        nd.setProperty("role", "muted")
        nd.setWordWrap(True)
        sec.lay.addWidget(self.normalize)
        sec.lay.addWidget(nd)
        root.addWidget(sec)

        # font size
        sec = _Section(S.set_font_size)
        row = QHBoxLayout()
        self.font_slider = QSlider(Qt.Horizontal)
        self.font_slider.setRange(10, 28)
        self.font_slider.setValue(self._settings.editor_font_pt)
        self.font_slider.setAccessibleName(S.set_font_size)
        self.font_slider.setLayoutDirection(Qt.LeftToRight)
        self.font_label = QLabel()
        self.font_label.setMinimumWidth(80)
        self.font_label.setAlignment(Qt.AlignCenter)
        row.addWidget(self.font_slider, 1)
        row.addWidget(self.font_label)
        sec.lay.addLayout(row)
        self.preview = QLabel(S.set_font_preview)
        self.preview.setWordWrap(True)
        self.preview.setObjectName("card")
        self.preview.setContentsMargins(theme.SP_3, theme.SP_3, theme.SP_3, theme.SP_3)
        self.preview.setAccessibleName(S.set_font_size)
        sec.lay.addWidget(self.preview)
        root.addWidget(sec)

        foot = QHBoxLayout()
        note = QLabel(S.set_applies_live)
        note.setProperty("role", "small")
        self.btn_close = push_button(S.settings_close, "primary")
        self.btn_close.setDefault(True)
        foot.addWidget(note)
        foot.addStretch(1)
        foot.addWidget(self.btn_close)
        root.addLayout(foot)

        self.theme_ctl.valueChanged.connect(lambda v: self._set("theme", v))
        self.mode_ctl.valueChanged.connect(lambda v: self._set("mode", v))
        self.digits_ctl.valueChanged.connect(lambda v: self._set("digit_style", v))
        self.normalize.toggled.connect(lambda v: self._set("normalize_text", bool(v)))
        self.font_slider.valueChanged.connect(lambda v: self._set("editor_font_pt", int(v)))
        self.btn_close.clicked.connect(self.accept)
        self._refresh_texts()
        self.setTabOrder(self.btn_close, self.btn_close)

    def _set(self, field: str, value) -> None:
        setattr(self._settings, field, value)
        self._refresh_texts()
        self._on_change(dataclasses.replace(self._settings))

    def _refresh_texts(self) -> None:
        self.mode_desc.setText({"auto": S.mode_auto_desc, "raw": S.mode_raw_desc,
                                "lex": S.mode_lex_desc}[self._settings.mode])
        self.digits_desc.setText({"keep": S.digits_keep_desc, "fa": S.digits_fa_desc,
                                  "en": S.digits_en_desc}[self._settings.digit_style])
        pt = self._settings.editor_font_pt
        self.font_label.setText(S.set_font_pt.format(n=fa_digits(pt)))
        f = self.preview.font()
        f.setPointSizeF(float(pt))
        self.preview.setFont(f)

    @property
    def settings(self) -> AppSettings:
        return dataclasses.replace(self._settings)


class _Keycap(QFrame):
    def __init__(self, text: str) -> None:
        super().__init__()
        self.setObjectName("keycap")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 2, 8, 2)
        lab = QLabel(wrap_ltr(text))
        lab.setLayoutDirection(Qt.LeftToRight)
        lab.setAlignment(Qt.AlignCenter)
        lay.addWidget(lab)
        self.setAccessibleName(text)


class ShortcutsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle(S.shortcuts_title)
        self.setModal(True)
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_5, theme.SP_4, theme.SP_5, theme.SP_4)
        root.setSpacing(theme.SP_3)
        title = QLabel(S.shortcuts_title)
        title.setProperty("role", "h2")
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(theme.SP_4)
        grid.setVerticalSpacing(theme.SP_3)
        self.rows: list[tuple[str, list[str]]] = []
        for gi, (gname, entries) in enumerate(shortcuts.groups()):
            card = QFrame()
            card.setObjectName("card")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(theme.SP_3, theme.SP_3, theme.SP_3, theme.SP_3)
            cl.setSpacing(theme.SP_2)
            head = QLabel(gname)
            head.setProperty("role", "h3")
            cl.addWidget(head)
            for label, keys in entries:
                self.rows.append((label, keys))
                row = QHBoxLayout()
                row.setSpacing(theme.SP_1)
                name = QLabel(label)
                row.addWidget(name, 1)
                for ki, key in enumerate(keys):
                    if ki:
                        row.addWidget(QLabel("/"))
                    row.addWidget(_Keycap(key))
                cl.addLayout(row)
            cl.addStretch(1)
            grid.addWidget(card, gi // 2, gi % 2)
        root.addLayout(grid)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.btn_close = push_button(S.shortcuts_close, "primary")
        self.btn_close.setDefault(True)
        foot.addWidget(self.btn_close)
        root.addLayout(foot)
        self.btn_close.clicked.connect(self.accept)


class AboutDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setLayoutDirection(Qt.RightToLeft)
        self.setWindowTitle(S.about_title)
        self.setModal(True)
        self.setMinimumWidth(480)
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_5, theme.SP_5, theme.SP_5, theme.SP_4)
        root.setSpacing(theme.SP_3)
        mark = QLabel()
        mark.setPixmap(icons.app_pixmap(72, max(self.devicePixelRatioF(), 1.0)))
        mark.setAlignment(Qt.AlignCenter)
        mark.setAccessibleName(S.app_name)
        name = QLabel(S.app_name)
        name.setProperty("role", "title")
        name.setAlignment(Qt.AlignCenter)
        ver = QLabel(S.about_version.format(v=fa_digits(matnyab.__version__)))
        ver.setProperty("role", "muted")
        ver.setAlignment(Qt.AlignCenter)
        tag = QLabel(S.app_tagline)
        tag.setAlignment(Qt.AlignCenter)
        root.addWidget(mark)
        root.addWidget(name)
        root.addWidget(ver)
        root.addWidget(tag)

        off = QFrame()
        off.setObjectName("card")
        ol = QHBoxLayout(off)
        ol.setContentsMargins(theme.SP_3, theme.SP_3, theme.SP_3, theme.SP_3)
        ol.setSpacing(theme.SP_3)
        from matnyab.ui.widgets import IconLabel

        ol.addWidget(IconLabel("lock", "success", 22), 0, Qt.AlignTop)
        offt = QLabel(S.about_offline)
        offt.setWordWrap(True)
        ol.addWidget(offt, 1)
        root.addWidget(off)

        lt = QLabel(S.about_licences_title)
        lt.setProperty("role", "h3")
        lb = QLabel(S.about_licences)
        lb.setWordWrap(True)
        lb.setProperty("role", "muted")
        root.addWidget(lt)
        root.addWidget(lb)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.btn_close = push_button(S.about_close, "primary")
        self.btn_close.setDefault(True)
        foot.addWidget(self.btn_close)
        root.addLayout(foot)
        self.btn_close.clicked.connect(self.accept)
