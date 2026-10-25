"""Design system: colour tokens (light and dark), spacing, radii, QSS, theme manager.

All colours of the interface come from the two token tables below. The QSS is
generated from ``QSS_TEMPLATE`` by replacing ``@token@`` placeholders; the
template itself holds no colour literals.
"""

from __future__ import annotations

import os
import re
from typing import Literal, Optional

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QPalette
from PySide6.QtWidgets import QApplication

from matnyab import paths

__all__ = [
    "SPACING", "SP_1", "SP_2", "SP_3", "SP_4", "SP_5", "SP_6", "RADIUS_SM", "RADIUS_MD",
    "RADIUS_LG", "LIGHT", "DARK", "TEXT_PAIRS", "UI_PAIRS", "QSS_TEMPLATE",
    "contrast_ratio", "build_qss", "ThemeManager", "manager", "color", "load_fonts",
    "FONT_FAMILY", "UI_POINT_SIZE", "animations_enabled", "ANIM_MS",
]

Mode = Literal["system", "light", "dark"]

# 8-pt spacing scale and radii.
SPACING = (4, 8, 12, 16, 24, 32)
SP_1, SP_2, SP_3, SP_4, SP_5, SP_6 = SPACING
RADIUS_SM, RADIUS_MD, RADIUS_LG = 8, 12, 16

FONT_FAMILY = "Vazirmatn"
UI_POINT_SIZE = 10.5
ANIM_MS = 160

LIGHT: dict[str, str] = {
    "bg": "#F4F5F8",
    "surface": "#FFFFFF",
    "surface_alt": "#ECEEF3",
    "surface_hover": "#E3E6EE",
    "border": "#DADEE7",
    "border_strong": "#7C8499",
    "text": "#1A1E2B",
    "text_muted": "#505A70",
    "text_on_accent": "#FFFFFF",
    "accent": "#2F6FED",
    "accent_hover": "#2559C8",
    "accent_pressed": "#1E49A6",
    "accent_soft": "#E4ECFD",
    "accent_fg": "#1F55C7",
    "success": "#13724A",
    "success_bg": "#DFF3E8",
    "warning": "#8A4B00",
    "warning_bg": "#FFEFCF",
    "warning_line": "#B26A00",
    "error": "#B3261E",
    "error_bg": "#FCE6E3",
    "error_line": "#C62828",
    "focus": "#1F55C7",
    "selection_bg": "#CFE0FF",
    "selection_text": "#0F1A33",
}

DARK: dict[str, str] = {
    "bg": "#101218",
    "surface": "#1A1D26",
    "surface_alt": "#242835",
    "surface_hover": "#2D3242",
    "border": "#2F3445",
    "border_strong": "#7F889E",
    "text": "#E9ECF3",
    "text_muted": "#A6AEC0",
    "text_on_accent": "#0A1428",
    "accent": "#7AA2FF",
    "accent_hover": "#93B3FF",
    "accent_pressed": "#A9C3FF",
    "accent_soft": "#222F4F",
    "accent_fg": "#8DB0FF",
    "success": "#5FD39A",
    "success_bg": "#16342A",
    "warning": "#F5BC55",
    "warning_bg": "#3A2E12",
    "warning_line": "#F5B94A",
    "error": "#FF8E84",
    "error_bg": "#3F1F1E",
    "error_line": "#FF6F61",
    "focus": "#9DBBFF",
    "selection_bg": "#2F4A85",
    "selection_text": "#FFFFFF",
}

# (foreground, background) pairs used for text; each must reach 4.5:1.
TEXT_PAIRS: tuple[tuple[str, str], ...] = (
    ("text", "bg"), ("text", "surface"), ("text", "surface_alt"),
    ("text", "surface_hover"), ("text", "accent_soft"), ("text", "warning_bg"), ("text", "error_bg"),
    ("text_muted", "bg"), ("text_muted", "surface"), ("text_muted", "surface_alt"),
    ("text_muted", "surface_hover"),
    ("accent_fg", "bg"), ("accent_fg", "surface"), ("accent_fg", "surface_alt"),
    ("accent_fg", "accent_soft"),
    ("text_on_accent", "accent"), ("text_on_accent", "accent_hover"),
    ("text_on_accent", "accent_pressed"),
    ("success", "success_bg"), ("success", "surface"),
    ("warning", "warning_bg"), ("warning", "surface"),
    ("error", "error_bg"), ("error", "surface"),
    ("selection_text", "selection_bg"),
)
# Non-text UI parts (icons, borders of inputs, focus ring, marks); each >= 3:1.
UI_PAIRS: tuple[tuple[str, str], ...] = (
    ("border_strong", "surface"), ("border_strong", "bg"),
    ("focus", "surface"), ("focus", "bg"), ("focus", "surface_alt"),
    ("accent", "surface"), ("accent", "surface_alt"), ("accent", "bg"),
    ("warning_line", "surface"), ("warning_line", "surface_alt"),
    ("error_line", "surface"), ("error_line", "surface_alt"),
    ("success", "surface"), ("text_muted", "surface"),
)


def _linear(channel: int) -> float:
    c = channel / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _linear(r) + 0.7152 * _linear(g) + 0.0722 * _linear(b)


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio of two ``#RRGGBB`` colours."""
    a, b = _luminance(fg), _luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


# ------------------------------------------------------------------ QSS ---
# Placeholders: @token@ (colour), $name$ (spacing / radius numbers).
QSS_TEMPLATE = """
* { outline: 0; }
QWidget { color: @text@; selection-background-color: @selection_bg@; selection-color: @selection_text@; }
QMainWindow, QDialog { background: @bg@; }
QWidget#central, QWidget#workspace { background: @bg@; }
QToolTip {
  background: @surface@; color: @text@; border: 1px solid @border_strong@;
  border-radius: $r_sm$px; padding: $sp1$px $sp2$px;
}

/* ---- surfaces ---- */
QFrame#card, QFrame#panel {
  background: @surface@; border: 1px solid @border@; border-radius: $r_md$px;
}
QFrame#panelFlat { background: @surface@; border: none; }
QFrame#header { background: @surface@; border: none; border-bottom: 1px solid @border@; }
QFrame#sidebar { background: @surface@; border: none; border-left: 1px solid @border@; }
QFrame#drawer { background: @surface@; border: none; border-right: 1px solid @border_strong@; }
QFrame#toolbar { background: transparent; border: none; }
QFrame#dropzone {
  background: @surface@; border: 2px dashed @border_strong@; border-radius: $r_lg$px;
}
QFrame#dropzone[dragging="true"] {
  background: @accent_soft@; border: 3px solid @accent@;
}
QFrame#toast {
  background: @text@; border: none; border-radius: $r_md$px;
}
QFrame#toast QLabel { color: @surface@; background: transparent; }
QFrame#toast QPushButton { color: @accent_hover@; }
QStatusBar { background: @surface@; border-top: 1px solid @border@; color: @text_muted@; }
QStatusBar::item { border: none; }
QStatusBar QLabel { color: @text_muted@; background: transparent; }

/* ---- text roles ---- */
QLabel { background: transparent; }
QLabel[role="title"] { font-size: 19pt; font-weight: 700; }
QLabel[role="h2"] { font-size: 13pt; font-weight: 600; }
QLabel[role="h3"] { font-size: 11pt; font-weight: 600; }
QLabel[role="muted"] { color: @text_muted@; }
QLabel[role="small"] { color: @text_muted@; font-size: 9pt; }
QLabel[role="error"] { color: @error@; }

/* ---- buttons ---- */
QPushButton {
  background: @surface@; color: @text@; border: 1px solid @border_strong@;
  border-radius: $r_sm$px; padding: $sp2$px $sp4$px; font-weight: 500; min-height: 20px;
}
QPushButton:hover { background: @surface_hover@; }
QPushButton:pressed { background: @surface_alt@; }
QPushButton:disabled { color: @text_muted@; border-color: @border@; background: @surface_alt@; }
QPushButton:focus { border: 2px solid @focus@; padding: 7px 15px; }
QPushButton[variant="primary"] {
  background: @accent@; color: @text_on_accent@; border: 1px solid @accent@;
}
QPushButton[variant="primary"]:hover { background: @accent_hover@; border-color: @accent_hover@; }
QPushButton[variant="primary"]:pressed { background: @accent_pressed@; border-color: @accent_pressed@; }
QPushButton[variant="primary"]:disabled { background: @surface_alt@; color: @text_muted@; border-color: @border@; }
QPushButton[variant="primary"]:focus { border: 2px solid @focus@; padding: 7px 15px; }
QPushButton[variant="ghost"] { background: transparent; border: 1px solid transparent; color: @accent_fg@; }
QPushButton[variant="ghost"]:hover { background: @accent_soft@; }
QPushButton[variant="ghost"]:focus { border: 2px solid @focus@; padding: 7px 15px; }
QPushButton[variant="danger"] { color: @error@; border-color: @error_line@; }
QPushButton[variant="danger"]:hover { background: @error_bg@; }

QToolButton {
  background: transparent; border: 2px solid transparent; border-radius: $r_sm$px;
  padding: $sp1$px; color: @text@; font-weight: 500;
}
QToolButton:hover { background: @surface_hover@; }
QToolButton:pressed { background: @surface_alt@; }
QToolButton:checked { background: @accent_soft@; color: @accent_fg@; }
QToolButton:disabled { color: @text_muted@; }
QToolButton:focus { border: 2px solid @focus@; }
QToolButton[text-button="true"] { padding: $sp1$px 6px; }
QToolButton::menu-indicator { image: none; width: 0; }

/* ---- inputs ---- */
QLineEdit {
  background: @surface@; color: @text@; border: 1px solid @border_strong@;
  border-radius: $r_sm$px; padding: 5px $sp3$px; min-height: 22px;
}
QLineEdit:focus { border: 2px solid @focus@; padding: 4px 11px; }
QPlainTextEdit, QTextEdit {
  background: @surface@; color: @text@; border: 2px solid transparent; border-radius: $r_md$px;
  padding: $sp3$px;
}
QPlainTextEdit:focus, QTextEdit:focus { border: 2px solid @focus@; }
QSpinBox {
  background: @surface@; border: 1px solid @border_strong@; border-radius: $r_sm$px;
  padding: 4px $sp2$px; min-height: 22px;
}
QSpinBox:focus { border: 2px solid @focus@; }
QCheckBox, QRadioButton { spacing: $sp2$px; background: transparent; padding: $sp1$px 0; }
QCheckBox:focus, QRadioButton:focus { color: @accent_fg@; }
QSlider::groove:horizontal { height: 4px; background: @surface_alt@; border-radius: 2px; }
QSlider::sub-page:horizontal { background: @accent@; border-radius: 2px; }
QSlider::add-page:horizontal { background: @border_strong@; border-radius: 2px; }
QSlider::handle:horizontal {
  background: @accent@; border: 2px solid @surface@; width: 16px; height: 16px;
  margin: -8px 0; border-radius: 10px;
}
QSlider::handle:horizontal:focus { border: 2px solid @focus@; }

/* ---- progress ---- */
QProgressBar {
  background: @surface_alt@; border: none; border-radius: 2px;
  min-height: 4px; max-height: 4px; text-align: center; color: transparent;
}
QProgressBar::chunk { background: @accent@; border-radius: 2px; }

/* ---- lists ---- */
QListWidget, QListView {
  background: transparent; border: none; padding: $sp1$px;
}
QListWidget::item { border-radius: $r_sm$px; padding: 0; margin: 2px 0; }
QListWidget::item:hover { background: @surface_alt@; }
QListWidget::item:selected { background: @accent_soft@; }
QListWidget:focus { border: none; }
QListWidget::item:selected:!active { background: @accent_soft@; }
QWidget#itemRow { background: transparent; border-radius: $r_sm$px; }

/* ---- chips ---- */
QFrame[chip="neutral"] { background: @surface_alt@; border-radius: 12px; border: none; }
QFrame[chip="accent"] { background: @accent_soft@; border-radius: 12px; border: none; }
QFrame[chip="success"] { background: @success_bg@; border-radius: 12px; border: none; }
QFrame[chip="warning"] { background: @warning_bg@; border-radius: 12px; border: none; }
QFrame[chip="error"] { background: @error_bg@; border-radius: 12px; border: none; }
QFrame[chip] QLabel { background: transparent; font-size: 9.5pt; font-weight: 500; }
QFrame[chip="neutral"] QLabel { color: @text@; }
QFrame[chip="accent"] QLabel { color: @accent_fg@; }
QFrame[chip="success"] QLabel { color: @success@; }
QFrame[chip="warning"] QLabel { color: @warning@; }
QFrame[chip="error"] QLabel { color: @error@; }

/* ---- error card ---- */
QFrame#errorCard {
  background: @error_bg@; border: 1px solid @error_line@; border-radius: $r_md$px;
}
QFrame#errorCard QLabel { background: transparent; }
QFrame#errorCard QPlainTextEdit {
  background: @surface@; border: 1px solid @border@; border-radius: $r_sm$px;
  font-family: Consolas, "Cascadia Mono", monospace; font-size: 9pt;
}

/* ---- menus ---- */
QMenu {
  background: @surface@; border: 1px solid @border_strong@; border-radius: $r_sm$px;
  padding: $sp1$px;
}
QMenu::item { padding: 6px 14px 6px 28px; border-radius: 6px; }
QMenu::item:selected { background: @accent_soft@; color: @text@; }
QMenu::item:disabled { color: @text_muted@; }
QMenu::separator { height: 1px; background: @border@; margin: 4px 8px; }

/* ---- scrollbars ---- */
QScrollBar:vertical { background: transparent; width: 12px; margin: 2px; }
QScrollBar::handle:vertical { background: @border_strong@; border-radius: 4px; min-height: 32px; margin: 0 2px; }
QScrollBar::handle:vertical:hover { background: @text_muted@; }
QScrollBar:horizontal { background: transparent; height: 12px; margin: 2px; }
QScrollBar::handle:horizontal { background: @border_strong@; border-radius: 4px; min-width: 32px; margin: 2px 0; }
QScrollBar::handle:horizontal:hover { background: @text_muted@; }
QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; }
QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }

/* ---- splitter ---- */
QSplitter::handle { background: transparent; }
QSplitter::handle:horizontal { width: 10px; }
QSplitter::handle:hover { background: @accent_soft@; }
QSplitter::handle:pressed { background: @accent_soft@; }

QGraphicsView { background: @surface_alt@; border: none; }
QFrame#keycap {
  background: @surface_alt@; border: 1px solid @border_strong@; border-radius: 6px;
}
QFrame#keycap QLabel { color: @text@; font-weight: 600; font-size: 9.5pt; }
QFrame#segmented { background: @surface_alt@; border: 1px solid @border@; border-radius: 10px; }
QToolButton[segment="true"] { border-radius: 8px; padding: 4px 14px; color: @text@; }
QToolButton[segment="true"]:checked {
  background: @surface@; border: 1px solid @border_strong@; color: @accent_fg@; font-weight: 700;
}
QToolButton[segment="true"]:focus { border: 2px solid @focus@; }
QFrame#hline { background: @border@; max-height: 1px; min-height: 1px; border: none; }
"""

_PLACEHOLDER = re.compile(r"@([a-z_]+)@")
_NUMBERS = {
    "$r_sm$": str(RADIUS_SM), "$r_md$": str(RADIUS_MD), "$r_lg$": str(RADIUS_LG),
    "$sp1$": str(SP_1), "$sp2$": str(SP_2), "$sp3$": str(SP_3), "$sp4$": str(SP_4),
}


def build_qss(tokens: dict[str, str]) -> str:
    """Return the application QSS for one token table."""
    qss = QSS_TEMPLATE
    for key, value in _NUMBERS.items():
        qss = qss.replace(key, value)
    return _PLACEHOLDER.sub(lambda m: tokens[m.group(1)], qss)


# -------------------------------------------------------------- manager ---
def animations_enabled() -> bool:
    """False when the user (or the environment) asked for reduced motion."""
    if os.environ.get("MATNYAB_REDUCE_MOTION", "").strip() in ("1", "true", "yes"):
        return False
    hints = QGuiApplication.styleHints() if QGuiApplication.instance() else None
    for name in ("prefersReducedMotion", "reducedMotion"):
        value = getattr(hints, name, None)
        if callable(value):
            try:
                if value():
                    return False
            except Exception:
                pass
    return True


class ThemeManager(QObject):
    """Resolves the theme setting, applies QSS and palette, notifies on change."""

    changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._mode: Mode = "system"
        self._override: Optional[str] = None
        self._tokens = LIGHT
        self._dark = False
        self._hooked = False

    # -- state
    @property
    def tokens(self) -> dict[str, str]:
        return self._tokens

    @property
    def is_dark(self) -> bool:
        return self._dark

    @property
    def mode(self) -> Mode:
        return self._mode

    def set_override(self, mode: Optional[str]) -> None:
        """Force light/dark for this run only (command-line flag)."""
        self._override = mode if mode in ("light", "dark") else None
        self.apply()

    def set_mode(self, mode: str) -> None:
        self._mode = mode if mode in ("system", "light", "dark") else "system"  # type: ignore[assignment]
        self.apply()

    def _resolve_dark(self) -> bool:
        mode = self._override or self._mode
        if mode == "dark":
            return True
        if mode == "light":
            return False
        app = QGuiApplication.instance()
        if app is None:
            return False
        scheme = app.styleHints().colorScheme()
        return scheme == Qt.ColorScheme.Dark

    def apply(self) -> None:
        app = QApplication.instance()
        self._dark = self._resolve_dark()
        self._tokens = DARK if self._dark else LIGHT
        if app is not None:
            if not self._hooked:
                app.styleHints().colorSchemeChanged.connect(self._on_system_scheme)
                self._hooked = True
            _apply_palette(app, self._tokens, self._dark)
            app.setStyleSheet(build_qss(self._tokens))
        self.changed.emit()

    def _on_system_scheme(self, *_args) -> None:
        if self._override is None and self._mode == "system":
            self.apply()


def _apply_palette(app: QApplication, t: dict[str, str], dark: bool) -> None:
    pal = QPalette()
    roles = {
        QPalette.Window: t["bg"], QPalette.WindowText: t["text"],
        QPalette.Base: t["surface"], QPalette.AlternateBase: t["surface_alt"],
        QPalette.Text: t["text"], QPalette.Button: t["surface"],
        QPalette.ButtonText: t["text"], QPalette.ToolTipBase: t["surface"],
        QPalette.ToolTipText: t["text"], QPalette.Highlight: t["selection_bg"],
        QPalette.HighlightedText: t["selection_text"], QPalette.Link: t["accent_fg"],
        QPalette.PlaceholderText: t["text_muted"], QPalette.BrightText: t["text"],
        QPalette.Mid: t["border_strong"], QPalette.Dark: t["border_strong"],
        QPalette.Midlight: t["border"], QPalette.Light: t["surface"],
        QPalette.Shadow: t["border_strong"],
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(t["text_muted"]))
    app.setPalette(pal)


_manager: Optional[ThemeManager] = None


def manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def color(token: str, alpha: Optional[int] = None) -> QColor:
    """Current-theme colour for ``token`` (optional 0..255 alpha)."""
    c = QColor(manager().tokens[token])
    if alpha is not None:
        c.setAlpha(alpha)
    return c


# ---------------------------------------------------------------- fonts ---
_fonts_loaded = False


def load_fonts() -> bool:
    """Register the bundled Vazirmatn files and make it the application font."""
    global _fonts_loaded
    if _fonts_loaded:
        return True
    ok = 0
    for style in ("Regular", "Medium", "SemiBold", "Bold"):
        path = paths.fonts_dir() / f"Vazirmatn-{style}.ttf"
        if path.is_file() and QFontDatabase.addApplicationFont(str(path)) >= 0:
            ok += 1
    _fonts_loaded = ok > 0
    app = QGuiApplication.instance()
    if app is not None:
        font = QFont(FONT_FAMILY)
        font.setPointSizeF(UI_POINT_SIZE)
        font.setStyleStrategy(QFont.PreferAntialias)
        app.setFont(font)
    return _fonts_loaded
