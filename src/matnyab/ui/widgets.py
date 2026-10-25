"""Small reusable widgets: icon label, chip, progress ring, segmented control, toast."""

from __future__ import annotations

from typing import Callable, Optional

from PySide6.QtCore import (
    QEasingCurve, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QToolButton, QWidget,
)

from matnyab.ui import icons, theme
from matnyab.ui.format import wrap_ltr
from matnyab.ui.strings import S

__all__ = [
    "set_tip", "tool_button", "push_button", "repolish", "IconLabel", "Chip",
    "ProgressRing", "SegmentedControl", "Toast", "hline",
]


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_tip(widget: QWidget, text: str, shortcut: Optional[str] = None,
            description: Optional[str] = None) -> None:
    """Tooltip with the shortcut, plus accessible name/description."""
    tip = f"{text}  {wrap_ltr('(' + shortcut + ')')}" if shortcut else text
    widget.setToolTip(tip)
    if not widget.accessibleName():
        widget.setAccessibleName(text)
    desc = description or (f"{text} ({shortcut})" if shortcut else text)
    widget.setAccessibleDescription(desc)


def tool_button(
    icon_name: Optional[str], text: str, shortcut: Optional[str] = None, *,
    checkable: bool = False, token: str = "text", size: int = 20, label: Optional[str] = None,
    description: Optional[str] = None, parent: Optional[QWidget] = None,
) -> QToolButton:
    btn = QToolButton(parent)
    btn.setCheckable(checkable)
    btn.setCursor(Qt.PointingHandCursor)
    btn.setFocusPolicy(Qt.StrongFocus)
    btn.setAutoRaise(True)
    if icon_name:
        icons.apply(btn, icon_name, token)
        btn.setIconSize(QSize(size, size))
    if label:
        btn.setText(label)
        btn.setProperty("text-button", True)
        btn.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if icon_name else Qt.ToolButtonTextOnly)
    else:
        btn.setToolButtonStyle(Qt.ToolButtonIconOnly)
        btn.setMinimumSize(34, 34)
    set_tip(btn, text, shortcut, description)
    return btn


def push_button(text: str, variant: Optional[str] = None, icon_name: Optional[str] = None,
                token: Optional[str] = None, description: Optional[str] = None) -> QPushButton:
    btn = QPushButton(("\u2002" + text) if icon_name else text)
    btn.setCursor(Qt.PointingHandCursor)
    if variant:
        btn.setProperty("variant", variant)
    if icon_name:
        tok = token or ("text_on_accent" if variant == "primary" else "text")
        icons.apply(btn, icon_name, tok)
        btn.setIconSize(QSize(18, 18))
    btn.setAccessibleName(text)
    btn.setAccessibleDescription(description or text)
    return btn


def hline() -> QFrame:
    line = QFrame()
    line.setObjectName("hline")
    line.setFixedHeight(1)
    return line


class IconLabel(QLabel):
    """A label showing a themed icon; re-tints itself when the theme changes."""

    def __init__(self, name: str, token: str = "text_muted", size: int = 18,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._name, self._token, self._size = name, token, size
        self.setFixedSize(size, size)
        self.setAlignment(Qt.AlignCenter)
        self.setAccessibleName("")
        theme.manager().changed.connect(self._refresh)
        self._refresh()

    def set_icon(self, name: str, token: Optional[str] = None) -> None:
        self._name = name
        if token:
            self._token = token
        self._refresh()

    def _refresh(self) -> None:
        dpr = self.devicePixelRatioF() if self.window() else 1.0
        self.setPixmap(icons.icon_pixmap(self._name, self._token, self._size, max(dpr, 1.0)))


_CHIP_TOKEN = {
    "neutral": "text_muted", "accent": "accent_fg", "success": "success",
    "warning": "warning", "error": "error",
}


class Chip(QFrame):
    """Rounded status chip: icon + text (never colour alone)."""

    def __init__(self, text: str = "", kind: str = "neutral", icon_name: Optional[str] = None,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setProperty("chip", kind)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 3, 10, 3)
        lay.setSpacing(6)
        self._icon = IconLabel(icon_name or "info", _CHIP_TOKEN[kind], 15)
        self._icon.setVisible(bool(icon_name))
        self._label = QLabel(text)
        lay.addWidget(self._icon)
        lay.addWidget(self._label)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def set(self, text: str, kind: Optional[str] = None, icon_name: Optional[str] = None) -> None:
        self._label.setText(text)
        self.setAccessibleName(text)
        if kind is not None and kind != self.property("chip"):
            self.setProperty("chip", kind)
            repolish(self)
            repolish(self._label)
            self._icon._token = _CHIP_TOKEN[kind]
        if icon_name is not None:
            self._icon.set_icon(icon_name, _CHIP_TOKEN[self.property("chip")])
            self._icon.setVisible(True)
        elif icon_name is None and kind is not None:
            self._icon._refresh()

    def text(self) -> str:
        return self._label.text()

    @property
    def kind(self) -> str:
        return str(self.property("chip"))


class ProgressRing(QWidget):
    """Small determinate ring for queue rows."""

    def __init__(self, size: int = 22, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._value = 0.0
        self.setFixedSize(size, size)
        theme.manager().changed.connect(self.update)

    def set_value(self, value: float) -> None:
        self._value = max(0.0, min(1.0, value))
        self.update()

    def value(self) -> float:
        return self._value

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = 2.6
        rect = QRectF(self.rect()).adjusted(w, w, -w, -w)
        pen = QPen(theme.color("surface_hover"), w)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawEllipse(rect)
        pen.setColor(theme.color("accent"))
        p.setPen(pen)
        span = int(-self._value * 360 * 16)
        p.drawArc(rect, 90 * 16, span if span != 0 else -1)


class SegmentedControl(QFrame):
    """Exclusive row of text buttons; emits the selected key."""

    valueChanged = Signal(str)

    def __init__(self, options: list[tuple[str, str]], parent: Optional[QWidget] = None,
                 access_name: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("segmented")
        self._buttons: dict[str, QToolButton] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(3, 3, 3, 3)
        lay.setSpacing(2)
        for key, label in options:
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setProperty("segment", True)
            b.setCursor(Qt.PointingHandCursor)
            b.setToolButtonStyle(Qt.ToolButtonTextOnly)
            b.setAccessibleName(label)
            b.setMinimumWidth(92)
            b.setMinimumHeight(34)
            self._group.addButton(b)
            self._buttons[key] = b
            b.clicked.connect(lambda _c=False, k=key: self.valueChanged.emit(k))
            lay.addWidget(b)
        self.setAccessibleName(access_name)

    def value(self) -> str:
        for k, b in self._buttons.items():
            if b.isChecked():
                return k
        return ""

    def set_value(self, key: str) -> None:
        b = self._buttons.get(key)
        if b is not None:
            b.setChecked(True)


class Toast(QFrame):
    """Non-blocking message at the bottom centre of its parent."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 10, 8, 10)
        lay.setSpacing(12)
        self._label = QLabel()
        self._label.setWordWrap(False)
        self._action = QPushButton()
        self._action.setProperty("variant", "ghost")
        self._action.setCursor(Qt.PointingHandCursor)
        self._action.setAccessibleName(S.toast_undo)
        self._action.hide()
        self._action.clicked.connect(self._on_action)
        lay.addWidget(self._label)
        lay.addWidget(self._action)
        self._callback: Optional[Callable[[], None]] = None
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.dismiss)
        self._effect = QGraphicsOpacityEffect(self)
        self._effect.setOpacity(1.0)
        self.setGraphicsEffect(self._effect)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after_anim)
        self._hiding = False
        self.setAccessibleName(S.status_access)
        self.hide()

    def show_message(self, text: str, action_text: Optional[str] = None,
                     callback: Optional[Callable[[], None]] = None, timeout_ms: int = 3200) -> None:
        self._label.setText(text)
        self.setAccessibleDescription(text)
        self._callback = callback
        self._action.setVisible(bool(action_text))
        if action_text:
            self._action.setText(action_text)
            self._action.setAccessibleName(action_text)
        self.adjustSize()
        self.place()
        self._hiding = False
        self.show()
        self.raise_()
        self._fade(0.0 if not self.isVisible() else self._effect.opacity(), 1.0)
        self._timer.start(timeout_ms + (2000 if action_text else 0))

    def place(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.adjustSize()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - theme.SP_5
        self.move(max(0, x), max(0, y))

    def dismiss(self) -> None:
        if not self.isVisible():
            return
        self._hiding = True
        self._fade(self._effect.opacity(), 0.0)

    def _on_action(self) -> None:
        cb, self._callback = self._callback, None
        self.dismiss()
        if cb:
            cb()

    def _fade(self, start: float, end: float) -> None:
        self._anim.stop()
        if not theme.animations_enabled():
            self._effect.setOpacity(end)
            self._after_anim()
            return
        self._anim.setDuration(theme.ANIM_MS)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _after_anim(self) -> None:
        if self._hiding:
            self.hide()
            self._hiding = False

    def current_text(self) -> str:
        return self._label.text()
