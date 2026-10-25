"""Right-hand (editor) pane: actions, summary chips, find bar, editor / processing / error."""

from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QStackedLayout, QToolButton, QVBoxLayout, QWidget,
)

from matnyab.api import OcrResult
from matnyab.ui import icons, theme
from matnyab.ui.cards import ErrorCard, ProcessingCard
from matnyab.ui.editor import FindBar, ResultEditor
from matnyab.ui.format import fa_digits, fa_percent, fa_seconds
from matnyab.ui.models import mean_confidence
from matnyab.ui.strings import S
from matnyab.ui.widgets import Chip, push_button, tool_button

__all__ = ["ResultPane", "mode_label", "confidence_chip_spec"]

PAGE_EDITOR, PAGE_PROCESSING, PAGE_ERROR = 0, 1, 2


def mode_label(mode: str) -> str:
    return {"auto": S.mode_auto, "raw": S.mode_raw, "lex": S.mode_lex}.get(mode, mode)


def confidence_chip_spec(confidence: float) -> tuple[str, str, str]:
    """(label, chip kind, icon name): always text + icon, never colour only."""
    if confidence >= 90:
        return S.conf_high, "success", "check_circle"
    if confidence >= 80:
        return S.conf_mid, "accent", "info"
    if confidence >= 60:
        return S.conf_low, "warning", "warning"
    return S.conf_low, "error", "error"


class ResultPane(QWidget):
    copyAllRequested = Signal()
    copySelectionRequested = Signal()
    saveRequested = Signal()
    rerunRequested = Signal(str)
    clearRequested = Signal()
    fontStepRequested = Signal(int)
    retryRequested = Signal()
    removeRequested = Signal()
    cancelRequested = Signal()
    startRequested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("resultPane")
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- action toolbar
        bar = QFrame()
        bar.setObjectName("toolbar")
        bar.setFixedHeight(48)
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(theme.SP_2, theme.SP_1, theme.SP_2, theme.SP_1)
        bl.setSpacing(2)
        self.btn_copy = tool_button("copy", S.copy_all, "Ctrl+Shift+C", label=S.copy_all)
        self.btn_copy_sel = tool_button(None, S.copy_sel, "Ctrl+C", checkable=False)
        icons.apply(self.btn_copy_sel, "copy", "text_muted")
        self.btn_save = tool_button("save", S.save.rstrip("…"), "Ctrl+S", label=S.save)
        self.btn_rerun = QToolButton()
        self.btn_rerun.setPopupMode(QToolButton.InstantPopup)
        self.btn_rerun.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.btn_rerun.setMinimumSize(36, 36)
        self.btn_rerun.setCursor(Qt.PointingHandCursor)
        icons.apply(self.btn_rerun, "retry", "text")
        self.btn_rerun.setIconSize(QSize(20, 20))
        self.btn_rerun.setToolTip(S.rerun_other)
        self.btn_rerun.setAccessibleName(S.rerun_other)
        self.btn_rerun.setAccessibleDescription(S.rerun_other)
        self.rerun_menu = QMenu(self.btn_rerun)
        self._rerun_actions: dict[str, QAction] = {}
        for key in ("auto", "raw", "lex"):
            act = self.rerun_menu.addAction(mode_label(key))
            act.setToolTip({"auto": S.mode_auto_desc, "raw": S.mode_raw_desc, "lex": S.mode_lex_desc}[key])
            act.triggered.connect(lambda _c=False, k=key: self.rerunRequested.emit(k))
            self._rerun_actions[key] = act
        self.btn_rerun.setMenu(self.rerun_menu)
        self.btn_clear = tool_button("clear", S.clear)
        self.btn_undo = tool_button("undo", S.undo, "Ctrl+Z")
        self.btn_redo = tool_button("redo", S.redo, "Ctrl+Y")
        self.btn_find = tool_button("search", S.find, "Ctrl+F", checkable=True)
        self.btn_font_dec = tool_button("font_dec", S.font_dec, "Ctrl+Alt+-")
        self.btn_font_inc = tool_button("font_inc", S.font_inc, "Ctrl+Alt+=")
        self.btn_copy_sel.setToolTip(S.copy_sel)
        for w in (self.btn_copy, self.btn_save):
            bl.addWidget(w)
        bl.addWidget(self.btn_copy_sel)
        bl.addWidget(self.btn_rerun)
        bl.addWidget(self.btn_clear)
        bl.addSpacing(theme.SP_2)
        for w in (self.btn_undo, self.btn_redo, self.btn_find):
            bl.addWidget(w)
        bl.addStretch(1)
        root.addWidget(bar)

        # ---- summary row
        meta = QFrame()
        meta.setObjectName("toolbar")
        ml = QHBoxLayout(meta)
        ml.setContentsMargins(theme.SP_3, 0, theme.SP_3, theme.SP_2)
        ml.setSpacing(theme.SP_2)
        self.chip_conf = Chip("", "neutral", "info")
        self.chip_mode = Chip("", "neutral", "wand")
        self.chip_time = Chip("", "neutral", "history")
        for c in (self.chip_conf, self.chip_mode, self.chip_time):
            ml.addWidget(c)
            c.hide()
        ml.addStretch(1)
        root.addWidget(meta)
        self.meta_row = meta

        nav = QFrame()
        nav.setObjectName("toolbar")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(theme.SP_3, 0, theme.SP_3, theme.SP_1)
        nl.setSpacing(theme.SP_1)
        self.btn_prev_unc = tool_button("chevron_up", S.prev_uncertain, "Shift+F3", size=18)
        self.btn_next_unc = tool_button("chevron_down", S.next_uncertain, "F3", size=18)
        self.unc_label = QLabel("")
        self.unc_label.setProperty("role", "muted")
        self.unc_label.setAlignment(Qt.AlignCenter)
        self.unc_label.setMinimumWidth(110)
        self.unc_label.setAccessibleName(S.uncertain_counter_access)
        nl.addWidget(self.unc_label)
        nl.addWidget(self.btn_next_unc)
        nl.addWidget(self.btn_prev_unc)
        nl.addStretch(1)
        nl.addWidget(self.btn_font_dec)
        nl.addWidget(self.btn_font_inc)
        root.addWidget(nav)

        # ---- find bar
        self.find_bar = FindBar()
        root.addWidget(self.find_bar)

        # ---- body
        body = QFrame()
        body.setObjectName("card")
        host = QStackedLayout(body)
        host.setContentsMargins(1, 1, 1, 1)
        self.editor = ResultEditor()
        self.processing = ProcessingCard()
        self.error = ErrorCard()
        host.addWidget(self.editor)
        host.addWidget(self.processing)
        host.addWidget(self.error)
        self._stack = host
        wrap = QVBoxLayout()
        wrap.setContentsMargins(theme.SP_3, 0, theme.SP_3, theme.SP_3)
        wrap.addWidget(body)
        root.addLayout(wrap, 1)

        # ---- wiring
        self.btn_copy.clicked.connect(self.copyAllRequested)
        self.btn_copy_sel.clicked.connect(self.copySelectionRequested)
        self.btn_save.clicked.connect(self.saveRequested)
        self.btn_clear.clicked.connect(self.clearRequested)
        self.btn_undo.clicked.connect(self.editor.undo)
        self.btn_redo.clicked.connect(self.editor.redo)
        self.btn_font_inc.clicked.connect(lambda: self.fontStepRequested.emit(1))
        self.btn_font_dec.clicked.connect(lambda: self.fontStepRequested.emit(-1))
        self.btn_find.toggled.connect(self._on_find_toggled)
        self.btn_next_unc.clicked.connect(self.editor.next_uncertain)
        self.btn_prev_unc.clicked.connect(self.editor.prev_uncertain)
        self.editor.uncertainChanged.connect(self._on_uncertain)
        self.editor.undoAvailable.connect(self.btn_undo.setEnabled)
        self.editor.redoAvailable.connect(self.btn_redo.setEnabled)
        self.editor.copySelectionRequested.connect(self.copySelectionRequested)
        self.editor.selectionChanged.connect(self._on_selection)
        self.find_bar.queryChanged.connect(self.editor.find_set_query)
        self.find_bar.nextRequested.connect(self.editor.find_next)
        self.find_bar.prevRequested.connect(self.editor.find_prev)
        self.find_bar.closed.connect(self.close_find)
        self.editor.findChanged.connect(self.find_bar.set_counts)
        self.error.retryRequested.connect(self.retryRequested)
        self.error.removeRequested.connect(self.removeRequested)
        self.processing.cancelRequested.connect(self.cancelRequested)
        self.processing.startRequested.connect(self.startRequested)
        self.btn_undo.setEnabled(False)
        self.btn_redo.setEnabled(False)
        self.btn_copy_sel.setEnabled(False)
        self._on_uncertain(0, 0)

        self._action_buttons = (
            self.btn_copy, self.btn_save, self.btn_rerun, self.btn_clear, self.btn_find,
            self.btn_prev_unc, self.btn_next_unc,
        )
        order = (self.btn_copy, self.btn_save, self.btn_copy_sel, self.btn_rerun, self.btn_clear,
                 self.btn_undo, self.btn_redo, self.btn_find, self.btn_font_dec,
                 self.btn_font_inc, self.btn_prev_unc, self.btn_next_unc, self.editor)
        for a, b in zip(order, order[1:]):
            self.setTabOrder(a, b)

    # ----------------------------------------------------------- pages ---
    def show_editor(self) -> None:
        self._stack.setCurrentIndex(PAGE_EDITOR)

    def show_processing(self) -> None:
        self._stack.setCurrentIndex(PAGE_PROCESSING)

    def show_error(self, title: str, message: str, detail: str, can_retry: bool = True) -> None:
        self.error.set_error(title, message, detail, can_retry)
        self._stack.setCurrentIndex(PAGE_ERROR)

    @property
    def page(self) -> int:
        return self._stack.currentIndex()

    def set_actions_enabled(self, on: bool) -> None:
        for b in self._action_buttons:
            b.setEnabled(on)
        self.btn_font_dec.setEnabled(True)
        self.btn_font_inc.setEnabled(True)
        if not on:
            self.btn_undo.setEnabled(False)
            self.btn_redo.setEnabled(False)
            self.btn_copy_sel.setEnabled(False)
        else:
            self.btn_undo.setEnabled(self.editor.document().isUndoAvailable())
            self.btn_redo.setEnabled(self.editor.document().isRedoAvailable())
            self.btn_copy_sel.setEnabled(self.editor.textCursor().hasSelection())
            self._on_uncertain(*self._last_unc)

    def set_rerun_enabled(self, on: bool) -> None:
        self.btn_rerun.setEnabled(on)

    # ----------------------------------------------------------- chips ---
    def set_summary(self, result: Optional[OcrResult], confidence: Optional[float] = None) -> None:
        if result is None:
            for c in (self.chip_conf, self.chip_mode, self.chip_time):
                c.hide()
            return
        conf = mean_confidence(result) if confidence is None else confidence
        label, kind, icon_name = confidence_chip_spec(conf)
        self.chip_conf.set(S.chip_confidence.format(label=label, pct=fa_percent(conf)), kind, icon_name)
        self.chip_mode.set(S.chip_mode.format(mode=mode_label(result.mode_used)), "neutral", "wand")
        self.chip_time.set(S.chip_time.format(s=fa_seconds(result.elapsed_s)), "neutral", "history")
        for c in (self.chip_conf, self.chip_mode, self.chip_time):
            c.show()

    def set_history_summary(self, mode: str, confidence: float) -> None:
        label, kind, icon_name = confidence_chip_spec(confidence)
        self.chip_conf.set(S.chip_confidence.format(label=label, pct=fa_percent(confidence)), kind, icon_name)
        self.chip_mode.set(S.chip_mode.format(mode=mode_label(mode)), "neutral", "wand")
        self.chip_conf.show()
        self.chip_mode.show()
        self.chip_time.hide()

    # ------------------------------------------------------ uncertain ---
    _last_unc = (0, 0)

    def _on_uncertain(self, i: int, n: int) -> None:
        self._last_unc = (i, n)
        if n == 0:
            text = S.uncertain_none
        elif i > 0:
            text = S.uncertain_counter.format(i=fa_digits(i), n=fa_digits(n))
        else:
            text = S.uncertain_total.format(n=fa_digits(n))
        self.unc_label.setText(text)
        can_step = n > 0 and self._stack.currentIndex() == PAGE_EDITOR
        self.btn_next_unc.setEnabled(can_step)
        self.btn_prev_unc.setEnabled(can_step)

    def _on_selection(self) -> None:
        self.btn_copy_sel.setEnabled(self.editor.textCursor().hasSelection() and self.page == PAGE_EDITOR)

    # ------------------------------------------------------------ find ---
    def _on_find_toggled(self, on: bool) -> None:
        if on:
            self.find_bar.open()
        else:
            self.find_bar.hide()
            self.editor.find_clear()

    def open_find(self) -> None:
        self.btn_find.setChecked(True)
        self.find_bar.open()

    def close_find(self) -> None:
        was_open = self.find_bar.isVisible()
        self.btn_find.setChecked(False)
        self.find_bar.hide()
        self.editor.find_clear()
        if was_open:
            self.editor.setFocus()

    @property
    def find_open(self) -> bool:
        return self.find_bar.isVisible()
