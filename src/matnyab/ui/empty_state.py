"""Empty state: large drop-zone card with a code-drawn illustration."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QSpacerItem, QVBoxLayout, QWidget,
)

from matnyab.ui import theme
from matnyab.ui.strings import S
from matnyab.ui.widgets import IconLabel, push_button, repolish

__all__ = ["EmptyState", "Illustration"]


class Illustration(QWidget):
    """A photo card flowing into a text card; ``lift`` (0..1) animates on drag-over."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lift = 0.0
        self.setFixedSize(300, 150)
        theme.manager().changed.connect(self.update)

    def sizeHint(self) -> QSize:
        return QSize(300, 150)

    def get_lift(self) -> float:
        return self._lift

    def set_lift(self, v: float) -> None:
        self._lift = float(v)
        self.update()

    lift = property(get_lift, set_lift)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        c = theme.color
        lift = self._lift
        w, h = self.width(), self.height()
        # --- photo card (right side in RTL)
        p.save()
        p.translate(w * 0.70 - lift * 8, h * 0.50 - lift * 4)
        p.rotate(4 - lift * 4)
        p.scale(1 + lift * 0.06, 1 + lift * 0.06)
        photo = QRectF(-52, -48, 104, 96)
        p.setPen(QPen(c("accent"), 2))
        p.setBrush(c("accent_soft"))
        p.drawRoundedRect(photo, 12, 12)
        p.setPen(Qt.NoPen)
        p.setBrush(c("warning_line"))
        p.drawEllipse(QPointF(24, -22), 8, 8)
        hills = QPainterPath()
        hills.moveTo(-52 + 2, 48 - 2)
        hills.lineTo(-52 + 2, 14)
        hills.lineTo(-22, -10)
        hills.lineTo(2, 20)
        hills.lineTo(18, 6)
        hills.lineTo(52 - 2, 30)
        hills.lineTo(52 - 2, 48 - 2)
        hills.closeSubpath()
        p.setBrush(c("accent"))
        p.setClipPath(self._rounded(photo.adjusted(1, 1, -1, -1), 11))
        p.drawPath(hills)
        p.restore()
        # --- text card (left side)
        p.save()
        p.translate(w * 0.30 + lift * 8, h * 0.50 - lift * 4)
        p.rotate(-3 + lift * 3)
        p.scale(1 + lift * 0.06, 1 + lift * 0.06)
        doc = QRectF(-48, -52, 96, 104)
        p.setPen(QPen(c("border_strong"), 2))
        p.setBrush(c("surface"))
        p.drawRoundedRect(doc, 12, 12)
        p.setPen(Qt.NoPen)
        lengths = (66, 54, 70, 40, 60, 30)
        for i, ln in enumerate(lengths):
            y = -36 + i * 13
            right = 36
            col = c("accent") if i in (0, 3) else c("text_muted", 150)
            p.setBrush(col)
            p.drawRoundedRect(QRectF(right - ln, y, ln, 5), 2.5, 2.5)
        p.restore()
        # --- arrow between them (points to the text card, i.e. leftwards)
        p.save()
        p.translate(w * 0.50, h * 0.50 + 4)
        pen = QPen(c("accent"), 3.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawLine(QPointF(10, 0), QPointF(-10, 0))
        p.drawLine(QPointF(-10, 0), QPointF(-3, -7))
        p.drawLine(QPointF(-10, 0), QPointF(-3, 7))
        p.restore()

    @staticmethod
    def _rounded(rect: QRectF, r: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, r, r)
        return path


class EmptyState(QWidget):
    chooseRequested = Signal()
    pasteRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("emptyState")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SP_6, theme.SP_5, theme.SP_6, theme.SP_5)
        outer.addStretch(1)

        row = QHBoxLayout()
        row.addStretch(1)
        self.zone = QFrame()
        self.zone.setObjectName("dropzone")
        self.zone.setMaximumWidth(680)
        self.zone.setMinimumWidth(520)
        self.zone.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.zone.setAccessibleName(S.empty_drop_access)
        self.zone.setAccessibleDescription(S.empty_hint)
        row.addWidget(self.zone, 10)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

        lay = QVBoxLayout(self.zone)
        lay.setContentsMargins(theme.SP_6, theme.SP_5, theme.SP_6, theme.SP_5)
        lay.setSpacing(theme.SP_3)

        self.illustration = Illustration()
        lay.addWidget(self.illustration, 0, Qt.AlignHCenter)

        self.title = QLabel(S.empty_title)
        self.title.setProperty("role", "title")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        lay.addWidget(self.title)

        self.hint = QLabel(S.empty_hint)
        self.hint.setProperty("role", "muted")
        self.hint.setAlignment(Qt.AlignCenter)
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        lay.addSpacing(theme.SP_2)
        buttons = QHBoxLayout()
        buttons.setSpacing(theme.SP_3)
        buttons.addStretch(1)
        self.choose_btn = push_button(S.btn_choose, "primary", "folder",
                                      description=S.tt_open)
        self.paste_btn = push_button(S.btn_paste, None, "clipboard",
                                     description=S.btn_paste)
        self.choose_btn.clicked.connect(self.chooseRequested)
        self.paste_btn.clicked.connect(self.pasteRequested)
        buttons.addWidget(self.choose_btn)
        buttons.addWidget(self.paste_btn)
        buttons.addStretch(1)
        lay.addLayout(buttons)

        lay.addSpacing(theme.SP_2)
        self.formats = QLabel(S.empty_formats)
        self.formats.setProperty("role", "small")
        self.formats.setAlignment(Qt.AlignCenter)
        self.formats.setWordWrap(True)
        lay.addWidget(self.formats)

        privacy = QHBoxLayout()
        privacy.setSpacing(theme.SP_2)
        self.lock = IconLabel("lock", "success", 16)
        self.privacy = QLabel(S.empty_privacy)
        self.privacy.setProperty("role", "small")
        self.privacy.setWordWrap(True)
        self.privacy.setAlignment(Qt.AlignCenter)
        privacy.addWidget(self.lock, 0, Qt.AlignTop)
        privacy.addWidget(self.privacy, 1)
        lay.addLayout(privacy)

        self.setTabOrder(self.choose_btn, self.paste_btn)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(theme.ANIM_MS)
        self._anim.valueChanged.connect(lambda v: self.illustration.set_lift(float(v)))
        self._dragging = False

    @property
    def dragging(self) -> bool:
        return self._dragging

    def set_dragging(self, on: bool) -> None:
        if on == self._dragging:
            return
        self._dragging = on
        self.zone.setProperty("dragging", "true" if on else "false")
        repolish(self.zone)
        self.title.setText(S.empty_title_drag if on else S.empty_title)
        target = 1.0 if on else 0.0
        self._anim.stop()
        if theme.animations_enabled():
            self._anim.setStartValue(self.illustration.lift)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.illustration.set_lift(target)
