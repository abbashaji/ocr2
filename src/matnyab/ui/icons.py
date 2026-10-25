"""Inline SVG icons (24x24 grid, stroked), tinted with the theme and the app icon."""

from __future__ import annotations

import weakref
from typing import Any

from PySide6.QtCore import QByteArray, QPoint, QPointF, QRect, QRectF, QSize, Qt
from PySide6.QtGui import (
    QColor, QFont, QIcon, QIconEngine, QLinearGradient, QPainter, QPainterPath, QPixmap,
)
from PySide6.QtSvg import QSvgRenderer

from matnyab.ui import theme
from matnyab.ui.strings import S

__all__ = ["icon", "apply", "refresh_all", "app_icon", "app_pixmap", "ICON_NAMES"]

# Directional icons are drawn for a right-to-left layout (the app is always RTL).
_PATHS: dict[str, str] = {
    "image": '<rect x="3" y="4.5" width="18" height="15" rx="3"/><circle cx="9" cy="10" r="1.6"/><path d="M21 16l-5-5-9 8.5"/>',
    "clipboard": '<rect x="5.5" y="4.5" width="13" height="16" rx="2.5"/><path d="M9 4.5V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v.5"/><path d="M9 11h6M9 15h4"/>',
    "folder": '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.5h7.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/>',
    "folder_save": '<path d="M3 7.5A2.5 2.5 0 0 1 5.5 5H9l2 2.5h7.5A2.5 2.5 0 0 1 21 10v7.5a2.5 2.5 0 0 1-2.5 2.5h-13A2.5 2.5 0 0 1 3 17.5z"/><path d="M12 11v5M9.8 14l2.2 2.2 2.2-2.2"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2.5"/><path d="M15 9V6.5A2.5 2.5 0 0 0 12.5 4h-6A2.5 2.5 0 0 0 4 6.5v6A2.5 2.5 0 0 0 6.5 15H9"/>',
    "save": '<path d="M12 4v11"/><path d="M7.5 10.5L12 15l4.5-4.5"/><path d="M5 19.5h14"/>',
    "undo": '<path d="M15 8h-5.5a4.5 4.5 0 0 0 0 9H14"/><path d="M12.5 4.5L16 8l-3.5 3.5" transform="translate(0 0)"/>',
    "redo": '<path d="M9 8h5.5a4.5 4.5 0 0 1 0 9H10"/><path d="M11.5 4.5L8 8l3.5 3.5"/>',
    "zoom_in": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20 20M10.5 8v5M8 10.5h5"/>',
    "zoom_out": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20 20M8 10.5h5"/>',
    "fit": '<path d="M4 9V6a2 2 0 0 1 2-2h3M15 4h3a2 2 0 0 1 2 2v3M20 15v3a2 2 0 0 1-2 2h-3M9 20H6a2 2 0 0 1-2-2v-3"/><rect x="8.5" y="8.5" width="7" height="7" rx="1.5"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5L20 20"/>',
    "chevron_up": '<path d="M6 14.5l6-6 6 6"/>',
    "chevron_down": '<path d="M6 9.5l6 6 6-6"/>',
    "chevron_start": '<path d="M14.5 6l-6 6 6 6"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "trash": '<path d="M4.5 7h15M10 7V5a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v2"/><path d="M6.5 7l.8 11.2A2 2 0 0 0 9.3 20h5.4a2 2 0 0 0 2-1.8L17.5 7M10 11v6M14 11v6"/>',
    "retry": '<path d="M19.5 12a7.5 7.5 0 1 1-2.4-5.5"/><path d="M19.5 4.5v4h-4"/>',
    "play": '<path d="M8 5.5v13l10.5-6.5z" fill="currentColor"/>',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2.5" fill="currentColor"/>',
    "history": '<path d="M4 12a8 8 0 1 0 2.5-5.8"/><path d="M4 4.5v4h4"/><path d="M12 8v4.2l2.8 1.8"/>',
    "queue": '<path d="M9 7h11M9 12h11M9 17h11"/><circle cx="4.8" cy="7" r="1" fill="currentColor"/><circle cx="4.8" cy="12" r="1" fill="currentColor"/><circle cx="4.8" cy="17" r="1" fill="currentColor"/>',
    "sidebar": '<rect x="3.5" y="4.5" width="17" height="15" rx="3"/><path d="M15 4.5v15"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6L7 7M17 17l1.4 1.4M5.6 18.4L7 17M17 7l1.4-1.4"/>',
    "moon": '<path d="M19.5 14.5A7.5 7.5 0 0 1 9.5 4.5a7.5 7.5 0 1 0 10 10z"/>',
    "settings": '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2.2"/><circle cx="9" cy="17" r="2.2"/>',
    "info": '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5"/><circle cx="12" cy="7.8" r=".6" fill="currentColor"/>',
    "warning": '<path d="M12 4.2L3.4 18.6a1 1 0 0 0 .9 1.5h15.4a1 1 0 0 0 .9-1.5z"/><path d="M12 10v4.2"/><circle cx="12" cy="16.9" r=".6" fill="currentColor"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "check_circle": '<circle cx="12" cy="12" r="8.5"/><path d="M8.2 12.4l2.7 2.7 5-5.4"/>',
    "error": '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5v5"/><circle cx="12" cy="16.2" r=".6" fill="currentColor"/>',
    "highlight": '<path d="M4 20l4-1 10-10-3-3L5 16z"/><path d="M14 7l3 3M4 20h6" />',
    "boxes": '<rect x="4" y="5" width="7" height="5" rx="1.2"/><rect x="13" y="5" width="7" height="5" rx="1.2"/><rect x="4" y="14" width="16" height="5" rx="1.2"/>',
    "font_inc": '<path d="M4 18l5-12 5 12M5.8 14h6.4"/><path d="M18 8v6M15 11h6"/>',
    "font_dec": '<path d="M4 18l5-12 5 12M5.8 14h6.4"/><path d="M15 11h6"/>',
    "more": '<circle cx="5.5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="18.5" cy="12" r="1.4" fill="currentColor"/>',
    "eye": '<path d="M2.8 12S6.2 5.8 12 5.8 21.2 12 21.2 12 17.8 18.2 12 18.2 2.8 12 2.8 12z"/><circle cx="12" cy="12" r="2.8"/>',
    "wand": '<path d="M5 19L16 8"/><path d="M14.5 5.5l4 4"/><path d="M6 6v3M4.5 7.5h3M18 15v3M16.5 16.5h3"/>',
    "lock": '<rect x="5" y="10.5" width="14" height="9.5" rx="2.5"/><path d="M8.5 10.5V8a3.5 3.5 0 0 1 7 0v2.5"/>',
    "keyboard": '<rect x="3" y="6" width="18" height="12" rx="2.5"/><path d="M7 10h.01M11 10h.01M15 10h.01M7 14h10"/>',
    "clear": '<path d="M5 8h14"/><path d="M7.5 8l.7 9.5A2 2 0 0 0 10.2 19h3.6a2 2 0 0 0 2-1.5L16.5 8"/><path d="M10 8V6.5A1.5 1.5 0 0 1 11.5 5h1A1.5 1.5 0 0 1 14 6.5V8"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "text": '<path d="M5 6h14M12 6v13M9 19h6"/>',
    "list_check": '<path d="M9 7h11M9 12h11M9 17h11"/><path d="M3.8 7l1 1 1.8-2M3.8 12l1 1 1.8-2M3.8 17l1 1 1.8-2"/>',
    "photo_off": '<rect x="3" y="4.5" width="18" height="15" rx="3"/><path d="M4 20L20 4"/>',
}
ICON_NAMES = tuple(sorted(_PATHS))

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
    'stroke="{c}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def _svg_bytes(name: str, color: str, stroke: float) -> QByteArray:
    body = _PATHS[name].replace("currentColor", color)
    return QByteArray(_SVG.format(c=color, w=stroke, body=body).encode("utf-8"))


class _SvgIconEngine(QIconEngine):
    """Paints the SVG on demand at the requested size: crisp on any DPI."""

    def __init__(self, name: str, color: str, stroke: float = 1.8) -> None:
        super().__init__()
        self._name, self._color, self._stroke = name, color, stroke
        self._renderer: QSvgRenderer | None = None

    def _get_renderer(self) -> QSvgRenderer:
        if self._renderer is None:
            self._renderer = QSvgRenderer(_svg_bytes(self._name, self._color, self._stroke))
        return self._renderer

    def paint(self, painter: QPainter, rect: QRect, mode: QIcon.Mode, state: QIcon.State) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if mode == QIcon.Disabled:
            painter.setOpacity(0.38)
        self._get_renderer().render(painter, QRectF(rect))
        painter.restore()

    def pixmap(self, size: QSize, mode: QIcon.Mode, state: QIcon.State) -> QPixmap:
        pm = QPixmap(size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        self.paint(painter, QRect(QPoint(0, 0), size), mode, state)
        painter.end()
        return pm

    def clone(self) -> "_SvgIconEngine":
        return _SvgIconEngine(self._name, self._color, self._stroke)

    def key(self) -> str:
        return "matnyab-svg"


def icon(name: str, token: str = "text", stroke: float = 1.8) -> QIcon:
    """Icon ``name`` tinted with the current colour of theme token ``token``."""
    if name not in _PATHS:
        raise KeyError(f"unknown icon: {name}")
    return QIcon(_SvgIconEngine(name, theme.manager().tokens[token], stroke))


_bound: list[tuple[Any, str, str, float]] = []


def apply(target: Any, name: str, token: str = "text", stroke: float = 1.8) -> None:
    """Set the icon on ``target`` (button/action/label-less widget) and keep it
    tinted when the theme changes."""
    target.setIcon(icon(name, token, stroke))
    _bound.append((weakref.ref(target), name, token, stroke))  # type: ignore[arg-type]


def refresh_all() -> None:
    alive = []
    for ref, name, token, stroke in _bound:
        obj = ref()
        if obj is None:
            continue
        try:
            obj.setIcon(icon(name, token, stroke))
        except RuntimeError:  # underlying C++ object already deleted
            continue
        alive.append((ref, name, token, stroke))
    _bound[:] = alive


def icon_pixmap(name: str, token: str, size: int, dpr: float = 1.0, stroke: float = 1.8) -> QPixmap:
    """Pixmap of an icon for custom painting."""
    px = int(round(size * dpr))
    engine = _SvgIconEngine(name, theme.manager().tokens[token], stroke)
    pm = engine.pixmap(QSize(px, px), QIcon.Normal, QIcon.Off)
    pm.setDevicePixelRatio(dpr)
    return pm


# ------------------------------------------------------------- app icon ---
def _draw_app_mark(painter: QPainter, size: int) -> None:
    """Monogram on a rounded square (always the light-theme accent)."""
    t = theme.LIGHT
    painter.setRenderHint(QPainter.Antialiasing, True)
    rect = QRectF(0, 0, size, size).adjusted(size * 0.04, size * 0.04, -size * 0.04, -size * 0.04)
    grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
    grad.setColorAt(0.0, QColor(t["accent"]))
    grad.setColorAt(1.0, QColor(t["accent_pressed"]))
    path = QPainterPath()
    path.addRoundedRect(rect, size * 0.24, size * 0.24)
    painter.fillPath(path, grad)
    font = QFont(theme.FONT_FAMILY)
    font.setWeight(QFont.Bold)
    font.setPixelSize(max(6, int(size * 0.62)))
    painter.setFont(font)
    painter.setPen(QColor(t["text_on_accent"]))
    painter.drawText(rect.adjusted(0, -size * 0.02, 0, size * 0.04), Qt.AlignCenter, S.app_monogram)


def app_pixmap(size: int, dpr: float = 1.0) -> QPixmap:
    px = int(round(size * dpr))
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    painter = QPainter(pm)
    _draw_app_mark(painter, px)
    painter.end()
    pm.setDevicePixelRatio(dpr)
    return pm


_app_icon: QIcon | None = None


def app_icon() -> QIcon:
    """Application icon drawn in code (no image files)."""
    global _app_icon
    if _app_icon is None:
        ic = QIcon()
        for size in (16, 24, 32, 48, 64, 128, 256):
            ic.addPixmap(app_pixmap(size))
        _app_icon = ic
    return _app_icon


def reset_app_icon_cache() -> None:
    """Drop the cached icon (used after the font is loaded)."""
    global _app_icon
    _app_icon = None
