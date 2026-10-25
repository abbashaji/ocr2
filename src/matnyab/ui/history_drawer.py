"""History drawer: slides in over the left edge of the workspace."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QEasingCurve, QEvent, QPropertyAnimation, QRect, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from matnyab.api import HistoryItem
from matnyab.ui import theme
from matnyab.ui.format import fa_datetime
from matnyab.ui.result_pane import confidence_chip_spec
from matnyab.ui.strings import S
from matnyab.ui.widgets import Chip, push_button, tool_button

__all__ = ["HistoryDrawer", "HistoryRow", "DRAWER_WIDTH"]

DRAWER_WIDTH = 380
ROW_H = 92


def first_words(text: str, count: int = 9) -> str:
    words = text.split()
    snippet = " ".join(words[:count])
    return snippet + (" " + S.ellipsis_words if len(words) > count else "")


class HistoryRow(QWidget):
    openRequested = Signal(str)
    deleteRequested = Signal(str)

    def __init__(self, item: HistoryItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("itemRow")
        self.item_id = item.id
        lay = QVBoxLayout(self)
        lay.setContentsMargins(theme.SP_3, theme.SP_2, theme.SP_2, theme.SP_2)
        lay.setSpacing(2)
        top = QHBoxLayout()
        top.setSpacing(theme.SP_2)
        self.source = QLabel()
        self.source.setProperty("role", "h3")
        self.source.setToolTip(item.source)
        fm = QFontMetrics(self.source.font())
        self.source.setText(fm.elidedText(item.source, Qt.ElideMiddle, 190))
        label, kind, icon = confidence_chip_spec(item.confidence)
        self.chip = Chip(label, kind, icon)
        self.chip.setAccessibleName(S.chip_confidence.format(label=label))
        self.chip.setToolTip(S.conf_tip)
        self.btn_open = tool_button("eye", S.history_open, size=18)
        self.btn_delete = tool_button("trash", S.history_delete, size=18)
        for b in (self.btn_open, self.btn_delete):
            b.setFixedSize(30, 30)
        top.addWidget(self.source, 1)
        top.addWidget(self.chip)
        top.addWidget(self.btn_open)
        top.addWidget(self.btn_delete)
        lay.addLayout(top)
        self.when = QLabel(fa_datetime(item.created))
        self.when.setProperty("role", "small")
        lay.addWidget(self.when)
        self.snippet = QLabel(first_words(item.text))
        self.snippet.setProperty("role", "muted")
        self.snippet.setWordWrap(False)
        fm2 = QFontMetrics(self.snippet.font())
        self.snippet.setText(fm2.elidedText(first_words(item.text), Qt.ElideRight, DRAWER_WIDTH - 70))
        lay.addWidget(self.snippet)
        self.btn_open.clicked.connect(lambda: self.openRequested.emit(self.item_id))
        self.btn_delete.clicked.connect(lambda: self.deleteRequested.emit(self.item_id))
        self.setAccessibleName(S.history_item_access.format(source=item.source, when=fa_datetime(item.created)))
        self.setAccessibleDescription(first_words(item.text))


class HistoryDrawer(QFrame):
    openRequested = Signal(str)
    deleteRequested = Signal(str)
    clearRequested = Signal()
    closeRequested = Signal()

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("drawer")
        self.setFixedWidth(DRAWER_WIDTH)
        self._open = False
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_3, theme.SP_3, theme.SP_3, theme.SP_3)
        root.setSpacing(theme.SP_2)
        head = QHBoxLayout()
        title = QLabel(S.history_title)
        title.setProperty("role", "h2")
        self.btn_close = tool_button("close", S.history_close, "Esc")
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.btn_close)
        root.addLayout(head)
        self.btn_clear = push_button(S.history_clear, "danger", "trash", token="error")
        root.addWidget(self.btn_clear, 0, Qt.AlignLeading)

        self.list = QListWidget()
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setAccessibleName(S.history_list_access)
        self.list.setAccessibleDescription(S.history_list_access)
        self.list.setAcceptDrops(False)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.viewport().installEventFilter(self)
        root.addWidget(self.list, 1)
        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.setAlignment(Qt.AlignCenter)
        t = QLabel(S.history_empty)
        t.setProperty("role", "h3")
        t.setAlignment(Qt.AlignCenter)
        h = QLabel(S.history_empty_hint)
        h.setProperty("role", "muted")
        h.setAlignment(Qt.AlignCenter)
        h.setWordWrap(True)
        el.addWidget(t)
        el.addWidget(h)
        root.addWidget(self.empty, 1)

        self.btn_close.clicked.connect(self.closeRequested)
        self.btn_clear.clicked.connect(self.clearRequested)
        self.list.itemDoubleClicked.connect(lambda it: self.openRequested.emit(it.data(Qt.UserRole)))
        self.setTabOrder(self.btn_close, self.btn_clear)
        self.setTabOrder(self.btn_clear, self.list)
        self._anim = QPropertyAnimation(self, b"geometry", self)
        self._anim.setDuration(theme.ANIM_MS + 20)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.finished.connect(self._after)
        self.hide()
        self.set_items([])

    def eventFilter(self, obj, event) -> bool:
        # Rows follow the viewport width (it shrinks when the vertical scrollbar appears).
        if obj is self.list.viewport() and event.type() == QEvent.Resize:
            self._fit_rows()
        return super().eventFilter(obj, event)

    def _fit_rows(self) -> None:
        width = max(1, self.list.viewport().width())
        for i in range(self.list.count()):
            lw = self.list.item(i)
            if lw.sizeHint().width() != width:
                lw.setSizeHint(QSize(width, ROW_H))

    def set_items(self, items: list[HistoryItem]) -> None:
        self.list.clear()
        for it in items:
            lw = QListWidgetItem()
            lw.setData(Qt.UserRole, it.id)
            lw.setSizeHint(QSize(DRAWER_WIDTH - 40, ROW_H))
            row = HistoryRow(it)
            row.openRequested.connect(self.openRequested)
            row.deleteRequested.connect(self.deleteRequested)
            self.list.addItem(lw)
            self.list.setItemWidget(lw, row)
        has = bool(items)
        self.list.setVisible(has)
        self.empty.setVisible(not has)
        self.btn_clear.setEnabled(has)
        self._fit_rows()

    @property
    def is_open(self) -> bool:
        return self._open

    def _target_rect(self, shown: bool) -> QRect:
        parent = self.parentWidget()
        h = parent.height() if parent else self.height()
        x = 0 if shown else -DRAWER_WIDTH
        return QRect(x, 0, DRAWER_WIDTH, h)

    def reposition(self) -> None:
        if self._open:
            self.setGeometry(self._target_rect(True))

    def open(self) -> None:
        if self._open:
            return
        self._open = True
        self.show()
        self.raise_()
        self._animate(True)
        self.list.setFocus() if self.list.isVisible() else self.btn_close.setFocus()

    def close_drawer(self) -> None:
        if not self._open:
            return
        self._open = False
        self._animate(False)

    def _animate(self, shown: bool) -> None:
        self._anim.stop()
        end = self._target_rect(shown)
        if not theme.animations_enabled():
            self.setGeometry(end)
            self._after()
            return
        start = self.geometry() if self.isVisible() else self._target_rect(not shown)
        self.setGeometry(start)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _after(self) -> None:
        if not self._open:
            self.hide()
