"""Queue sidebar: rows with thumbnail, status chip, actions; overall progress."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QFontMetrics, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QProgressBar, QSizePolicy,
    QVBoxLayout, QWidget,
)

from matnyab.ui import icons, theme
from matnyab.ui.format import fa_digits, fa_percent
from matnyab.ui.models import ItemState, QueueItem
from matnyab.ui.result_pane import confidence_chip_spec
from matnyab.ui.strings import S
from matnyab.ui.widgets import Chip, IconLabel, ProgressRing, push_button, tool_button

__all__ = ["QueuePanel", "QueueRow", "status_text", "confidence_short_label"]


def confidence_short_label(confidence: float) -> str:
    """Short quality word for the narrow queue chip (never a percentage)."""
    spec_label = confidence_chip_spec(confidence)[0]
    return {S.conf_high: S.conf_high_short, S.conf_mid: S.conf_mid_short}.get(spec_label, S.conf_low_short)


THUMB = 48
ROW_H = 68


def status_text(item: QueueItem) -> str:
    if item.from_history:
        return S.st_history
    if item.state == ItemState.DONE:
        return confidence_short_label(item.confidence)
    if item.state == ItemState.PROCESSING:
        return S.st_processing
    if item.state == ItemState.ERROR:
        return S.st_error
    return S.st_queued


def rounded_thumb(image: Optional[QImage], size: int, dpr: float = 2.0) -> QPixmap:
    px = int(size * dpr)
    pm = QPixmap(px, px)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, px, px), 8 * dpr, 8 * dpr)
    p.setClipPath(path)
    p.fillRect(0, 0, px, px, theme.color("surface_alt"))
    if image is not None and not image.isNull():
        scaled = image.scaled(px, px, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        p.drawImage((px - scaled.width()) // 2, (px - scaled.height()) // 2, scaled)
    else:
        ic = icons.icon_pixmap("image", "text_muted", size // 2, dpr)
        p.drawPixmap(int((px - ic.width()) / 2), int((px - ic.height()) / 2), ic)
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


class QueueRow(QWidget):
    openRequested = Signal(str)
    retryRequested = Signal(str)
    removeRequested = Signal(str)

    def __init__(self, item: QueueItem, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("itemRow")
        self.item_id = item.id
        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SP_2, theme.SP_1, theme.SP_1, theme.SP_1)
        lay.setSpacing(theme.SP_2)
        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB, THUMB)
        lay.addWidget(self.thumb)

        col = QVBoxLayout()
        col.setSpacing(2)
        col.setContentsMargins(0, 0, 0, 0)
        self.name = QLabel()
        self.name.setProperty("role", "h3")
        self.name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.status = QHBoxLayout()
        self.status.setSpacing(theme.SP_1)
        self.ring = ProgressRing(20)
        self.chip = Chip("", "neutral", "queue")
        self.stage = QLabel()
        self.stage.setProperty("role", "small")
        self.status.addWidget(self.ring)
        self.status.addWidget(self.chip)
        self.status.addWidget(self.stage)
        self.status.addStretch(1)
        col.addWidget(self.name)
        col.addLayout(self.status)
        lay.addLayout(col, 1)

        self.btn_open = tool_button("eye", S.item_open, "Enter", size=18, parent=self)
        self.btn_open.hide()  # "open" lives in the row's context menu, double click and Enter
        self.btn_retry = tool_button("retry", S.item_retry, size=18)
        self.btn_remove = tool_button("close", S.item_remove, "Delete", size=18)
        for b in (self.btn_retry, self.btn_remove):
            b.setMinimumSize(28, 28)
            b.setMaximumSize(28, 28)
            lay.addWidget(b)
        self.btn_open.clicked.connect(lambda: self.openRequested.emit(self.item_id))
        self.btn_retry.clicked.connect(lambda: self.retryRequested.emit(self.item_id))
        self.btn_remove.clicked.connect(lambda: self.removeRequested.emit(self.item_id))
        self._full_name = ""
        self.update_from(item)
        self._item = item
        theme.manager().changed.connect(self._on_theme)

    def _on_theme(self) -> None:
        self.refresh_thumb(self._item)

    def refresh_thumb(self, item: QueueItem) -> None:
        self.thumb.setPixmap(rounded_thumb(item.thumb, THUMB, max(self.devicePixelRatioF(), 1.0)))

    def update_from(self, item: QueueItem) -> None:
        self._full_name = item.name
        self.refresh_thumb(item)
        self.setMinimumHeight(ROW_H)
        st = item.state
        txt = status_text(item)
        self.chip.setToolTip("")  # only the "done" chip explains what the confidence label means
        if item.from_history:
            self.chip.set(txt, "neutral", "history")
        elif st == ItemState.DONE:
            _, kind, icon = confidence_chip_spec(item.confidence)
            self.chip.set(txt, kind, icon)
            self.chip.setToolTip(S.conf_tip)
        elif st == ItemState.ERROR:
            self.chip.set(txt, "error", "error")
        elif st == ItemState.PROCESSING:
            self.chip.set(txt, "accent", None)
        else:
            self.chip.set(txt, "neutral", "queue")
        processing = st == ItemState.PROCESSING
        self.ring.setVisible(processing)
        self.ring.set_value(item.progress)
        self.chip.setVisible(not processing)
        self.stage.setVisible(processing)
        self.stage.setText(
            f"{S.st_processing} {fa_percent(item.progress * 100)}" if processing else "")
        self.btn_retry.setVisible(not item.from_history and st in (ItemState.DONE, ItemState.ERROR))
        self._elide()
        label = S.queue_item_access.format(name=item.name, status=txt)
        self.setAccessibleName(label)
        self.setToolTip(item.name)

    def _elide(self) -> None:
        w = max(40, self.name.width() or 120)
        fm = QFontMetrics(self.name.font())
        self.name.setText(fm.elidedText(self._full_name, Qt.ElideMiddle, w))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide()

    def contextMenuEvent(self, event) -> None:
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        menu.addAction(S.item_open, lambda: self.openRequested.emit(self.item_id))
        if self.btn_retry.isVisibleTo(self):
            menu.addAction(S.item_retry, lambda: self.retryRequested.emit(self.item_id))
        menu.addAction(S.item_remove, lambda: self.removeRequested.emit(self.item_id))
        menu.exec(event.globalPos())


class _List(QListWidget):
    deleteRequested = Signal()
    activated_current = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            self.deleteRequested.emit()
            event.accept()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.activated_current.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class QueuePanel(QFrame):
    selected = Signal(str)
    openRequested = Signal(str)
    retryRequested = Signal(str)
    removeRequested = Signal(str)
    processAllRequested = Signal()
    saveAllRequested = Signal()
    addRequested = Signal()
    removeFinishedRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("sidebar")
        self.setMinimumWidth(0)
        root = QVBoxLayout(self)
        root.setContentsMargins(theme.SP_3, theme.SP_3, theme.SP_3, theme.SP_3)
        root.setSpacing(theme.SP_2)

        head = QHBoxLayout()
        self.title = QLabel(S.queue_title)
        self.title.setProperty("role", "h2")
        self.count = QLabel("")
        self.count.setProperty("role", "muted")
        self.btn_add = tool_button("plus", S.queue_add, "Ctrl+O")
        head.addWidget(self.title)
        head.addWidget(self.count)
        head.addStretch(1)
        head.addWidget(self.btn_add)
        root.addLayout(head)

        actions = QHBoxLayout()
        actions.setSpacing(theme.SP_2)
        self.btn_all = push_button(S.queue_process_all, "primary", "play")
        self.btn_save_all = push_button(S.queue_save_all, None, "folder_save")
        self.btn_save_all.setToolTip(S.queue_save_all_tip)
        actions.addWidget(self.btn_all)
        actions.addWidget(self.btn_save_all)
        root.addLayout(actions)

        self.overall_label = QLabel("")
        self.overall_label.setProperty("role", "small")
        self.overall_label.setAccessibleName(S.progress_access)
        self.overall = QProgressBar()
        self.overall.setRange(0, 1000)
        self.overall.setTextVisible(False)
        self.overall.setAccessibleName(S.progress_access)
        root.addWidget(self.overall_label)
        root.addWidget(self.overall)

        self.list = _List()
        self.list.setObjectName("queueList")
        self.list.setSelectionMode(QListWidget.SingleSelection)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setUniformItemSizes(True)
        self.list.setFocusPolicy(Qt.StrongFocus)
        self.list.setAccessibleName(S.queue_list_access)
        self.list.setAccessibleDescription(S.queue_list_access)
        self.list.setAcceptDrops(False)
        root.addWidget(self.list, 1)
        self.empty = QLabel(S.queue_empty)
        self.empty.setProperty("role", "muted")
        self.empty.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty, 1)

        self._rows: dict[str, tuple[QListWidgetItem, QueueRow]] = {}
        self.list.currentItemChanged.connect(self._on_current)
        self.list.deleteRequested.connect(self._delete_current)
        self.list.activated_current.connect(self._open_current)
        self.list.itemDoubleClicked.connect(lambda it: self.openRequested.emit(it.data(Qt.UserRole)))
        self.btn_all.clicked.connect(self.processAllRequested)
        self.btn_save_all.clicked.connect(self.saveAllRequested)
        self.btn_add.clicked.connect(self.addRequested)
        self.setTabOrder(self.btn_add, self.btn_all)
        self.setTabOrder(self.btn_all, self.btn_save_all)
        self.setTabOrder(self.btn_save_all, self.list)
        self._refresh_empty()

    # -- model sync
    def add_item(self, item: QueueItem) -> None:
        lw = QListWidgetItem()
        lw.setData(Qt.UserRole, item.id)
        lw.setSizeHint(QSize(100, ROW_H + 6))
        row = QueueRow(item)
        row.openRequested.connect(self.openRequested)
        row.retryRequested.connect(self.retryRequested)
        row.removeRequested.connect(self.removeRequested)
        self.list.addItem(lw)
        self.list.setItemWidget(lw, row)
        self._rows[item.id] = (lw, row)
        self._refresh_empty()

    def update_item(self, item: QueueItem) -> None:
        pair = self._rows.get(item.id)
        if pair:
            pair[1].update_from(item)

    def remove_item(self, item_id: str) -> None:
        pair = self._rows.pop(item_id, None)
        if pair:
            row = self.list.row(pair[0])
            self.list.blockSignals(True)
            self.list.takeItem(row)
            self.list.blockSignals(False)
        self._refresh_empty()

    def select(self, item_id: Optional[str]) -> None:
        self.list.blockSignals(True)
        pair = self._rows.get(item_id) if item_id else None
        if pair:
            self.list.setCurrentItem(pair[0])
        else:
            self.list.setCurrentItem(None)
        self.list.blockSignals(False)

    def order(self) -> list[str]:
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())]

    def row_widget(self, item_id: str) -> Optional[QueueRow]:
        pair = self._rows.get(item_id)
        return pair[1] if pair else None

    def set_overall(self, done: int, total: int, fraction: float) -> None:
        self.count.setText(f"({fa_digits(total)})" if total else "")
        if total == 0:
            self.overall_label.setText("")
            self.overall.setValue(0)
        else:
            self.overall_label.setText(S.queue_overall.format(done=fa_digits(done), total=fa_digits(total)))
            self.overall.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.overall_label.setVisible(total > 0)
        self.overall.setVisible(total > 0)

    def set_actions_state(self, can_process: bool, can_save: bool, busy: bool) -> None:
        self.btn_all.setEnabled(can_process)
        self.btn_save_all.setEnabled(can_save)

    def _refresh_empty(self) -> None:
        has = bool(self._rows)
        self.list.setVisible(has)
        self.empty.setVisible(not has)

    def _on_current(self, cur: Optional[QListWidgetItem], _prev) -> None:
        if cur is not None:
            self.selected.emit(cur.data(Qt.UserRole))

    def _delete_current(self) -> None:
        cur = self.list.currentItem()
        if cur is not None:
            self.removeRequested.emit(cur.data(Qt.UserRole))

    def _open_current(self) -> None:
        cur = self.list.currentItem()
        if cur is not None:
            self.openRequested.emit(cur.data(Qt.UserRole))
