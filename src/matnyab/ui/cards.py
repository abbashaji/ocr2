"""Cards shown in place of the editor: processing/queued state and error state."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QSizePolicy, QVBoxLayout,
    QWidget,
)

from matnyab.ui import theme
from matnyab.ui.strings import S
from matnyab.ui.widgets import IconLabel, push_button

__all__ = ["ProcessingCard", "ErrorCard"]


class ProcessingCard(QWidget):
    cancelRequested = Signal()
    startRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SP_5, theme.SP_5, theme.SP_5, theme.SP_5)
        outer.addStretch(1)
        card = QFrame()
        card.setObjectName("card")
        card.setMaximumWidth(460)
        card.setMinimumWidth(300)
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        row_c = QHBoxLayout()
        row_c.addStretch(1)
        row_c.addWidget(card, 10)
        row_c.addStretch(1)
        outer.addLayout(row_c)
        outer.addStretch(2)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(theme.SP_5, theme.SP_5, theme.SP_5, theme.SP_5)
        lay.setSpacing(theme.SP_3)
        self.icon = IconLabel("wand", "accent_fg", 32)
        self.title = QLabel(S.proc_title)
        self.title.setProperty("role", "h2")
        self.title.setAlignment(Qt.AlignCenter)
        self.stage = QLabel(S.stage_idle)
        self.stage.setAlignment(Qt.AlignCenter)
        self.stage.setAccessibleName(S.status_access)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.setTextVisible(False)
        self.bar.setAccessibleName(S.progress_access)
        self.hint = QLabel(S.proc_hint)
        self.hint.setProperty("role", "muted")
        self.hint.setWordWrap(True)
        self.hint.setAlignment(Qt.AlignCenter)
        self.cancel_btn = push_button(S.btn_cancel, None, "stop")
        self.start_btn = push_button(S.btn_start, "primary", "play")
        self.cancel_btn.clicked.connect(self.cancelRequested)
        self.start_btn.clicked.connect(self.startRequested)
        lay.addWidget(self.icon, 0, Qt.AlignHCenter)
        lay.addWidget(self.title)
        lay.addWidget(self.stage)
        lay.addWidget(self.bar)
        lay.addWidget(self.hint)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.cancel_btn)
        row.addWidget(self.start_btn)
        row.addStretch(1)
        lay.addLayout(row)

    def show_running(self, stage_text: str, fraction: float) -> None:
        self.title.setText(S.proc_title)
        self.hint.setText(S.proc_hint)
        self.stage.setText(stage_text)
        self.bar.setValue(int(max(0.0, min(1.0, fraction)) * 1000))
        self.bar.setVisible(True)
        self.cancel_btn.setVisible(True)
        self.start_btn.setVisible(False)

    def show_queued(self, waiting_for_start: bool) -> None:
        """Item is in the queue: either waiting its turn or waiting for the user."""
        self.title.setText(S.proc_title_queued)
        self.stage.setText(S.stage_queued if not waiting_for_start else S.st_queued)
        self.bar.setValue(0)
        self.bar.setVisible(False)
        self.hint.setText(S.proc_hint_queued if waiting_for_start else S.proc_hint)
        self.start_btn.setVisible(waiting_for_start)
        self.cancel_btn.setVisible(not waiting_for_start)


class ErrorCard(QWidget):
    retryRequested = Signal()
    removeRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(theme.SP_5, theme.SP_5, theme.SP_5, theme.SP_5)
        outer.addStretch(1)
        self.card = QFrame()
        self.card.setObjectName("errorCard")
        self.card.setMaximumWidth(560)
        self.card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.card.setAccessibleName(S.stage_error)
        self.card.setMinimumWidth(300)
        row_c = QHBoxLayout()
        row_c.addStretch(1)
        row_c.addWidget(self.card, 10)
        row_c.addStretch(1)
        outer.addLayout(row_c)
        outer.addStretch(2)
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(theme.SP_4, theme.SP_4, theme.SP_4, theme.SP_4)
        lay.setSpacing(theme.SP_3)

        head = QHBoxLayout()
        head.setSpacing(theme.SP_3)
        self.icon = IconLabel("error", "error", 28)
        self.title = QLabel()
        self.title.setProperty("role", "h2")
        self.title.setWordWrap(True)
        head.addWidget(self.icon, 0, Qt.AlignTop)
        head.addWidget(self.title, 1)
        lay.addLayout(head)

        self.message = QLabel()
        self.message.setWordWrap(True)
        lay.addWidget(self.message)

        self.details_btn = push_button(S.err_details, "ghost", "chevron_down", token="accent_fg")
        self.details_btn.setCheckable(True)
        self.details_btn.toggled.connect(self._toggle_details)
        lay.addWidget(self.details_btn, 0, Qt.AlignLeading)

        self.details = QPlainTextEdit()
        self.details.setReadOnly(True)
        self.details.setLayoutDirection(Qt.LeftToRight)
        self.details.setMinimumHeight(110)
        self.details.setMaximumHeight(200)
        self.details.setAccessibleName(S.err_details_access)
        self.details.hide()
        lay.addWidget(self.details)

        row = QHBoxLayout()
        row.setSpacing(theme.SP_2)
        self.retry_btn = push_button(S.err_retry, "primary", "retry")
        self.remove_btn = push_button(S.err_remove, None, "trash")
        self.retry_btn.clicked.connect(self.retryRequested)
        self.remove_btn.clicked.connect(self.removeRequested)
        row.addWidget(self.retry_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        lay.addLayout(row)

    def set_error(self, title: str, message: str, detail: str, can_retry: bool = True) -> None:
        self.title.setText(title)
        self.message.setText(message)
        self.details.setPlainText(detail)
        self.details_btn.setVisible(bool(detail))
        self.details_btn.setChecked(False)
        self.details.hide()
        self.retry_btn.setVisible(can_retry)
        self.card.setAccessibleDescription(f"{title}. {message}")

    def _toggle_details(self, on: bool) -> None:
        self.details.setVisible(on)
        self.details_btn.setText(S.err_details_hide if on else S.err_details)
        from matnyab.ui import icons

        icons.apply(self.details_btn, "chevron_up" if on else "chevron_down", "accent_fg")

    @property
    def details_visible(self) -> bool:
        return not self.details.isHidden()
