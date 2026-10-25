"""The main window: wires header, viewer, editor, queue, history, status bar."""

from __future__ import annotations

import base64
import json
import time
import uuid
from collections import OrderedDict
from datetime import datetime
from pathlib import Path
from typing import Optional

from PIL import Image
from PySide6.QtCore import (
    QByteArray, QEasingCurve, QMimeData, QPropertyAnimation, QSize, Qt, QTimer, Signal,
)
from PySide6.QtGui import QAction, QGuiApplication, QImage, QKeySequence, QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMainWindow, QProgressBar,
    QSplitter, QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from matnyab import engine as _engine_pkg  # noqa: F401  (documented dependency)
from matnyab import paths, services
from matnyab.api import AppSettings, HistoryItem, OcrEngine
from matnyab.ui import dialogs, icons, image_io, shortcuts, theme
from matnyab.ui.empty_state import EmptyState
from matnyab.ui.format import fa_clock, fa_digits, fa_percent, wrap_ltr
from matnyab.ui.history_drawer import HistoryDrawer
from matnyab.ui.logging import get_logger
from matnyab.ui.models import ItemState, QueueItem, mean_confidence
from matnyab.ui.queue_panel import QueuePanel
from matnyab.ui.result_pane import ResultPane
from matnyab.ui.runner import EngineHolder, ImageLoader, JobRunner
from matnyab.ui.strings import S
from matnyab.ui.viewer import ViewerPane
from matnyab.ui.widgets import IconLabel, Toast, tool_button, push_button

__all__ = ["MainWindow"]

_log = get_logger("window")
QUEUE_WIDTH_MIN = 264
QUEUE_WIDTH_WIDE = 320
QUEUE_WIDTH = QUEUE_WIDTH_MIN
MIN_FONT, MAX_FONT = 10, 28
_STAGE_TEXT = {
    "preparing": S.stage_preparing, "segmenting": S.stage_segmenting,
    "recognizing": S.stage_recognizing, "correcting": S.stage_correcting,
    "done": S.stage_done,
}


class _Host(QWidget):
    resized = Signal()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.resized.emit()


class MainWindow(QMainWindow):
    idleChanged = Signal(bool)
    itemFinished = Signal(str)

    def __init__(self, engine: Optional[OcrEngine] = None, settings_store=None,
                 history_store=None) -> None:
        super().__init__()
        self.settings_store = settings_store or services.create_settings_store()
        self.history_store = history_store or services.create_history_store()
        self.settings: AppSettings = self.settings_store.load()
        self.items: dict[str, QueueItem] = {}
        self.current: Optional[QueueItem] = None
        self._owner_id: Optional[str] = None  # item whose text the editor holds
        self._qimages: "OrderedDict[str, QImage]" = OrderedDict()
        self._pending_loads = 0
        self._pasted = 0
        self._cancelling = False
        self._job_t0 = 0.0
        self._batch_total = 0
        self._batch_done = 0
        self._last_status = S.stage_idle

        self.runner = JobRunner(EngineHolder(engine), self)
        self.loader = ImageLoader(self)

        self.setWindowTitle(S.window_title)
        self.setWindowIcon(icons.app_icon())
        self.setLayoutDirection(Qt.RightToLeft)
        self.setMinimumSize(960, 640)
        self.setAcceptDrops(True)

        self._build_ui()
        self._build_actions()
        self._connect()
        self._apply_settings_to_ui()
        self._restore_state()
        self._refresh_all()
        self.empty.choose_btn.setFocus()

    # ================================================================= UI
    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- header
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(56)
        hl = QHBoxLayout(header)
        hl.setContentsMargins(theme.SP_4, theme.SP_1, theme.SP_4, theme.SP_1)
        hl.setSpacing(theme.SP_1)
        self.mark = QLabel()
        self.mark.setPixmap(icons.app_pixmap(32, max(self.devicePixelRatioF(), 1.0)))
        self.mark.setFixedSize(32, 32)
        self.mark.setAccessibleName(S.app_name)
        name = QLabel(S.app_name)
        name.setProperty("role", "h2")
        tagline = QLabel(S.app_tagline)
        tagline.setProperty("role", "small")
        self.btn_queue = tool_button("sidebar", S.tt_queue, shortcuts.KEYS["queue"], checkable=True)
        self.btn_open = push_button(S.btn_open, "primary", "image", description=S.tt_open)
        self.btn_open.setToolTip(f"{S.tt_open}  {wrap_ltr('(' + shortcuts.KEYS['open'] + ')')}")
        self.btn_history = tool_button("history", S.tt_history, shortcuts.KEYS["history"])
        self.btn_theme = tool_button("moon", S.tt_theme_to_dark, shortcuts.KEYS["theme"])
        self.btn_settings = tool_button("settings", S.tt_settings, shortcuts.KEYS["settings"])
        self.btn_about = tool_button("info", S.tt_about)
        hl.addWidget(self.mark)
        hl.addSpacing(theme.SP_1)
        title_col = QVBoxLayout()
        title_col.setSpacing(0)
        title_col.addWidget(name)
        title_col.addWidget(tagline)
        hl.addLayout(title_col)
        hl.addSpacing(theme.SP_3)
        hl.addWidget(self.btn_queue)
        hl.addStretch(1)
        hl.addWidget(self.btn_open)
        hl.addSpacing(theme.SP_2)
        for b in (self.btn_history, self.btn_theme, self.btn_settings, self.btn_about):
            hl.addWidget(b)
        root.addWidget(header)
        self.header = header

        # ---- body host (also parent of overlays)
        self.host = _Host()
        root.addWidget(self.host, 1)
        host_lay = QVBoxLayout(self.host)
        host_lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        host_lay.addWidget(self.stack)

        self.empty = EmptyState()
        self.stack.addWidget(self.empty)

        self.workspace = QWidget()
        self.workspace.setObjectName("workspace")
        wl = QHBoxLayout(self.workspace)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        # RTL: first widget sits on the right -> sidebar on the far right.
        self.side_wrap = QFrame()
        self.side_wrap.setObjectName("sideWrap")
        sl = QHBoxLayout(self.side_wrap)
        sl.setContentsMargins(0, 0, 0, 0)
        self.panel = QueuePanel()
        self.panel.setFixedWidth(QUEUE_WIDTH_MIN)
        sl.addWidget(self.panel)
        self.side_wrap.setMaximumWidth(0)
        self.side_wrap.hide()
        self._side_anim = QPropertyAnimation(self.side_wrap, b"maximumWidth", self)
        self._side_anim.setDuration(theme.ANIM_MS + 20)
        self._side_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._side_anim.finished.connect(self._after_side_anim)
        wl.addWidget(self.side_wrap)

        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(10)
        self.viewer = ViewerPane()
        self.result = ResultPane()
        self.splitter.addWidget(self.viewer)
        self.splitter.addWidget(self.result)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 1)
        self.viewer.setMinimumWidth(276)
        self.result.setMinimumWidth(410)
        wl.addWidget(self.splitter, 1)
        self.stack.addWidget(self.workspace)

        # ---- overlays
        self.drawer = HistoryDrawer(self.host)
        self.toast = Toast(self.host)
        self.drop_overlay = QFrame(self.host)
        self.drop_overlay.setObjectName("dropzone")
        self.drop_overlay.setProperty("dragging", "true")
        dl = QVBoxLayout(self.drop_overlay)
        dl.setAlignment(Qt.AlignCenter)
        dl.addWidget(IconLabel("image", "accent_fg", 40), 0, Qt.AlignHCenter)
        dt = QLabel(S.empty_title_drag)
        dt.setProperty("role", "h2")
        dt.setAlignment(Qt.AlignCenter)
        dl.addWidget(dt)
        self.drop_overlay.hide()
        self.drop_overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.drop_overlay.setAccessibleName(S.empty_drop_access)

        # ---- status bar
        sb = QStatusBar()
        sb.setSizeGripEnabled(False)
        self.setStatusBar(sb)
        self.stage_label = QLabel(S.stage_idle)
        self.stage_label.setAccessibleName(S.status_access)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedWidth(200)
        self.progress.setTextVisible(False)
        self.progress.setAccessibleName(S.progress_access)
        self.elapsed_label = QLabel("")
        self.elapsed_label.setAccessibleName(S.elapsed_access)
        self.counter_label = QLabel("")
        self.counter_label.setAccessibleName(S.counter_access)
        sb.addWidget(self.stage_label)
        sb.addWidget(self.progress)
        sb.addWidget(self.elapsed_label)
        sb.addPermanentWidget(self.counter_label)

        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(250)
        self._elapsed_timer.timeout.connect(self._tick)

        self.setTabOrder(self.btn_queue, self.btn_open)
        self.setTabOrder(self.btn_open, self.btn_history)
        self.setTabOrder(self.btn_history, self.btn_theme)
        self.setTabOrder(self.btn_theme, self.btn_settings)
        self.setTabOrder(self.btn_settings, self.btn_about)

    def _add_action(self, key: str, slot, text: str = "", extra: tuple[str, ...] = ()) -> QAction:
        act = QAction(text or key, self)
        seqs = [QKeySequence(shortcuts.KEYS[key])] + [QKeySequence(s) for s in extra]
        act.setShortcuts(seqs)
        act.setShortcutContext(Qt.WindowShortcut)
        act.triggered.connect(lambda _c=False: slot())
        self.addAction(act)
        self.actions_by_key[key] = act
        return act

    def _build_actions(self) -> None:
        self.actions_by_key: dict[str, QAction] = {}
        a = self._add_action
        a("open", self.open_dialog, S.sc_open)
        a("open_folder", self.open_folder_dialog, S.sc_open_folder)
        a("paste", self.paste_from_clipboard, S.sc_paste)
        a("save", self.save_current, S.sc_save)
        a("copy_all", self.copy_all, S.sc_copy_all)
        a("find", self.result.open_find, S.sc_find)
        a("next_unc", self.result.editor.next_uncertain, S.sc_next_unc)
        a("prev_unc", self.result.editor.prev_uncertain, S.sc_prev_unc)
        a("font_inc", lambda: self.change_font(1), S.sc_font_inc)
        a("font_dec", lambda: self.change_font(-1), S.sc_font_dec)
        a("zoom_in", self.viewer.view.zoom_in, S.sc_zoom_in)
        a("zoom_out", self.viewer.view.zoom_out, S.sc_zoom_out)
        a("zoom_fit", self.viewer._on_fit_clicked, S.sc_zoom_fit)
        a("zoom_actual", self.viewer.view.actual_size, S.sc_zoom_actual)
        a("process_all", self.process_all, S.sc_process_all, extra=("Ctrl+Enter",))
        a("cancel", self.escape_pressed, S.sc_cancel)
        a("queue", self.toggle_queue, S.sc_queue)
        a("history", self.toggle_history, S.sc_history)
        a("settings", self.open_settings, S.sc_settings)
        a("theme", self.toggle_theme, S.sc_theme)
        a("shortcuts", self.open_shortcuts, S.sc_shortcuts, extra=(shortcuts.KEYS["shortcuts_alt"],
                                                                   "Ctrl+?"))
        self.actions_by_key["zoom_in"].setShortcuts([QKeySequence("Ctrl+="), QKeySequence("Ctrl++")])

    def _connect(self) -> None:
        self.empty.chooseRequested.connect(self.open_dialog)
        self.empty.pasteRequested.connect(self.paste_from_clipboard)
        self.btn_open.clicked.connect(self.open_dialog)
        self.btn_queue.clicked.connect(lambda: self.toggle_queue())
        self.btn_history.clicked.connect(self.toggle_history)
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_settings.clicked.connect(self.open_settings)
        self.btn_about.clicked.connect(self.open_about)
        self.host.resized.connect(self._relayout_overlays)

        # runner
        r = self.runner
        r.started.connect(self._on_started)
        r.progress.connect(self._on_progress)
        r.finished.connect(self._on_finished)
        r.failed.connect(self._on_failed)
        r.cancelled.connect(self._on_cancelled)
        r.idleChanged.connect(self._on_idle)
        self.loader.thumbReady.connect(self._on_thumb)
        self.loader.fullReady.connect(self._on_full)
        self.loader.failed.connect(self._on_load_failed)

        # queue panel
        p = self.panel
        p.selected.connect(self.select_item)
        p.openRequested.connect(self.select_item)
        p.retryRequested.connect(self.retry_item)
        p.removeRequested.connect(self.remove_item)
        p.processAllRequested.connect(self.process_all)
        p.saveAllRequested.connect(self.save_all)
        p.addRequested.connect(self.open_dialog)

        # result pane
        rp = self.result
        rp.copyAllRequested.connect(self.copy_all)
        rp.copySelectionRequested.connect(self.copy_selection)
        rp.saveRequested.connect(self.save_current)
        rp.rerunRequested.connect(self.rerun)
        rp.clearRequested.connect(self.clear_text)
        rp.fontStepRequested.connect(self.change_font)
        rp.retryRequested.connect(lambda: self.current and self.retry_item(self.current.id))
        rp.removeRequested.connect(lambda: self.current and self.remove_item(self.current.id))
        rp.cancelRequested.connect(self.cancel_processing)
        rp.startRequested.connect(lambda: self.current and self.retry_item(self.current.id))
        ed = rp.editor
        ed.wordSelected.connect(lambda i: self.viewer.view.set_selected_word(i))
        ed.statsChanged.connect(self._on_stats)
        ed.mediaPasted.connect(self.handle_mime)
        ed.fontStep.connect(self.change_font)
        self.viewer.wordClicked.connect(self._on_word_clicked)

        # history drawer
        d = self.drawer
        d.closeRequested.connect(self.close_history)
        d.openRequested.connect(self.open_history_item)
        d.deleteRequested.connect(self.delete_history_item)
        d.clearRequested.connect(self.clear_history)

        theme.manager().changed.connect(self._on_theme_changed)

    # ============================================================ settings
    def _apply_settings_to_ui(self) -> None:
        theme.manager().set_mode(self.settings.theme)
        self.result.editor.set_font_pt(self.settings.editor_font_pt)
        self._update_theme_button()

    def apply_settings(self, new: AppSettings, persist: bool = True) -> None:
        old = self.settings
        # keep fields the dialog does not own
        new.window_geometry = old.window_geometry
        new.last_open_dir = old.last_open_dir
        new.last_save_dir = old.last_save_dir
        self.settings = new
        if persist:
            self._save_settings()
        if theme.manager().mode != new.theme:
            theme.manager().set_mode(new.theme)
        if round(self.result.editor.font().pointSizeF()) != new.editor_font_pt:
            self.result.editor.set_font_pt(new.editor_font_pt)

    def _save_settings(self) -> None:
        try:
            self.settings_store.save(self.settings)
        except Exception:
            _log.exception("saving settings failed")

    def _on_theme_changed(self) -> None:
        icons.refresh_all()
        self.mark.setPixmap(icons.app_pixmap(32, max(self.devicePixelRatioF(), 1.0)))
        self._update_theme_button()

    def _update_theme_button(self) -> None:
        dark = theme.manager().is_dark
        icons.apply(self.btn_theme, "sun" if dark else "moon", "text")
        tip = S.tt_theme_to_light if dark else S.tt_theme_to_dark
        self.btn_theme.setToolTip(f"{tip}  {wrap_ltr('(' + shortcuts.KEYS['theme'] + ')')}")
        self.btn_theme.setAccessibleName(tip)

    def toggle_theme(self) -> None:
        new = AppSettings(**{**self.settings.__dict__})
        new.theme = "light" if theme.manager().is_dark else "dark"
        self.apply_settings(new)

    def change_font(self, step: int) -> None:
        pt = max(MIN_FONT, min(MAX_FONT, self.settings.editor_font_pt + step))
        if pt == self.settings.editor_font_pt:
            return
        new = AppSettings(**{**self.settings.__dict__})
        new.editor_font_pt = pt
        self.apply_settings(new)
        self.show_toast(S.toast_font_size.format(n=fa_digits(pt)))

    def open_settings(self) -> None:
        dlg = dialogs.SettingsDialog(self.settings, self.apply_settings, self)
        self._settings_dialog = dlg
        dlg.exec()

    def open_shortcuts(self) -> None:
        dialogs.ShortcutsDialog(self).exec()

    def open_about(self) -> None:
        dialogs.AboutDialog(self).exec()

    # ======================================================= state persist
    def _state_file(self) -> Path:
        return paths.data_dir() / "ui_state.json"

    def _restore_state(self) -> None:
        restored = False
        if self.settings.window_geometry:
            try:
                data = QByteArray(base64.b64decode(self.settings.window_geometry))
                restored = self.restoreGeometry(data)
            except Exception:
                restored = False
        if not restored:
            self.resize(1280, 800)
            screen = QGuiApplication.primaryScreen()
            if screen is not None:
                geo = screen.availableGeometry()
                self.move(geo.center().x() - self.width() // 2, geo.center().y() - self.height() // 2)
        try:
            state = json.loads(self._state_file().read_text(encoding="utf-8"))
            sizes = state.get("splitter")
            if isinstance(sizes, list) and len(sizes) == 2 and all(isinstance(x, int) for x in sizes):
                self.splitter.setSizes(sizes)
            self._queue_pref_open = bool(state.get("queue_open", False))
        except Exception:
            self._queue_pref_open = False

    def save_state(self) -> None:
        self.settings.window_geometry = base64.b64encode(bytes(self.saveGeometry())).decode("ascii")
        self._save_settings()
        try:
            self._state_file().write_text(
                json.dumps({"splitter": self.splitter.sizes(), "queue_open": self.queue_open}),
                encoding="utf-8")
        except Exception:
            _log.exception("saving ui state failed")

    def closeEvent(self, event) -> None:
        self.save_state()
        self.runner.shutdown()
        self.loader.wait(1500)
        super().closeEvent(event)

    # ============================================================== queue
    @property
    def queue_open(self) -> bool:
        return self.side_wrap.maximumWidth() > 0 and not self.side_wrap.isHidden()

    def toggle_queue(self, show: Optional[bool] = None) -> None:
        want = (not self.queue_open) if show is None else show
        if want == self.queue_open and self._side_anim.state() != QPropertyAnimation.Running:
            self.btn_queue.setChecked(want)
            return
        self.btn_queue.setChecked(want)
        self._side_anim.stop()
        if want:
            self.side_wrap.show()
        self.panel.setFixedWidth(self._queue_width())
        end = self._queue_width() if want else 0
        if not theme.animations_enabled():
            self.side_wrap.setMaximumWidth(end)
            self._after_side_anim()
            return
        self._side_anim.setStartValue(self.side_wrap.maximumWidth())
        self._side_anim.setEndValue(end)
        self._side_anim.start()

    def _queue_width(self) -> int:
        return QUEUE_WIDTH_WIDE if self.width() >= 1180 else QUEUE_WIDTH_MIN

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        width = self._queue_width()
        if self.panel.width() != width and self._side_anim.state() != QPropertyAnimation.Running:
            self.panel.setFixedWidth(width)
            if self.queue_open:
                self.side_wrap.setMaximumWidth(width)

    def _after_side_anim(self) -> None:
        if self.side_wrap.maximumWidth() == 0:
            self.side_wrap.hide()
        else:
            self.side_wrap.setMaximumWidth(self._queue_width())

    # ----------------------------------------------------------- adding
    def open_dialog(self) -> None:
        files = self._ask_open_paths()
        if files:
            self.add_paths(files)

    def open_folder_dialog(self) -> None:
        folder = self._ask_folder()
        if folder:
            self.add_paths([folder])

    def _ask_open_paths(self) -> list[str]:
        files, _flt = QFileDialog.getOpenFileNames(
            self, S.dlg_open_title, self.settings.last_open_dir, S.dlg_open_filter)
        if files:
            self.settings.last_open_dir = str(Path(files[0]).parent)
            self._save_settings()
        return list(files)

    def _ask_folder(self) -> str:
        folder = QFileDialog.getExistingDirectory(self, S.dlg_folder_title, self.settings.last_open_dir)
        if folder:
            self.settings.last_open_dir = folder
            self._save_settings()
        return folder

    def add_paths(self, raw_paths, select: bool = True) -> list[QueueItem]:
        files = image_io.expand_paths(raw_paths)
        if not files:
            self.show_toast(S.toast_no_supported)
            return []
        new: list[QueueItem] = []
        for p in files:
            item = QueueItem(name=p.name, path=p)
            try:
                item.size = image_io.probe_image(p)
            except image_io.ImageLoadError as exc:
                self._mark_error(item, exc.kind, str(exc), str(exc))
            new.append(item)
        big = [i for i in new if i.megapixels > image_io.MAX_MEGAPIXELS]
        if big:
            mp = fa_digits(int(round(big[0].megapixels)))
            msg = (S.big_msg.format(mp=mp, limit=fa_digits(image_io.MAX_MEGAPIXELS))
                   if len(big) == 1 else
                   S.big_msg_many.format(n=fa_digits(len(big)), limit=fa_digits(image_io.MAX_MEGAPIXELS)))
            if not dialogs.ask_yes_no(self, S.big_title, msg, S.dlg_yes_continue, S.dlg_no_skip):
                new = [i for i in new if i not in big]
        return self._register_many(new, select)

    def add_image(self, image: Image.Image, name: Optional[str] = None, select: bool = True) -> QueueItem:
        if name is None:
            self._pasted += 1
            name = S.pasted_image_name.format(n=fa_digits(self._pasted))
        item = QueueItem(name=name, image=image, size=image.size)
        self._register_many([item], select)
        return item

    def _register_many(self, new: list[QueueItem], select: bool) -> list[QueueItem]:
        if not new:
            return []
        for item in new:
            self.items[item.id] = item
            self.panel.add_item(item)
            if item.state != ItemState.ERROR:
                self._pending_loads += 1
                self.loader.load_thumbnail(item.id, item.path or item.image)
        if len(self.items) > 1 and not self.queue_open:
            self.toggle_queue(True)
        if len(new) > 1:
            self.show_toast(S.toast_added.format(n=fa_digits(len(new))))
        if select:
            self.select_item(new[0].id)
        self._submit([i for i in new if i.state == ItemState.QUEUED])
        self._refresh_all()
        return new

    def _mark_error(self, item: QueueItem, kind: str, message: str, detail: str) -> None:
        item.state = ItemState.ERROR
        item.submitted = False
        item.error_kind, item.error_message, item.error_detail = kind, message, detail

    def _error_texts(self, item: QueueItem) -> tuple[str, str]:
        return {
            "missing": (S.err_missing_title, S.err_missing_msg),
            "unreadable": (S.err_unreadable_title, S.err_unreadable_msg),
            "unavailable": (S.err_unavailable_title, S.err_unavailable_msg),
        }.get(item.error_kind, (S.err_engine_title, S.err_engine_msg))

    def _submit(self, items: list[QueueItem]) -> None:
        for item in items:
            if item.state == ItemState.ERROR or item.from_history or not item.has_image:
                continue
            if self.runner.is_idle:
                self._batch_total = 0
                self._batch_done = 0
            item.state = ItemState.QUEUED
            item.submitted = True
            item.progress = 0.0
            item.result = None
            item.text = None
            item.ranges = None
            mode = item.mode_override or self.settings.mode
            item.mode_override = None
            self._batch_total += 1
            self.runner.submit(item.id, item.path or item.image, mode)
            self.panel.update_item(item)
        self._refresh_all()

    def process_all(self) -> None:
        todo = [i for i in self.items.values() if i.state == ItemState.QUEUED and not i.submitted]
        self._submit(todo)

    def retry_item(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None:
            return
        if item.state == ItemState.ERROR:
            # an unreadable file may have been fixed: probe again
            item.error_kind = item.error_message = item.error_detail = ""
            item.state = ItemState.QUEUED
            if item.path is not None:
                try:
                    item.size = image_io.probe_image(item.path)
                except image_io.ImageLoadError as exc:
                    self._mark_error(item, exc.kind, str(exc), str(exc))
        if self.current is not item:
            self.select_item(item_id)
        if item.state == ItemState.DONE and self._owner_id == item.id:
            self._owner_id = None
        self._submit([item])
        if self.current is item:
            self._show_current()

    def remove_item(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None:
            return
        order = self.panel.order()
        self.runner.remove_waiting(item_id)
        self.panel.remove_item(item_id)
        del self.items[item_id]
        self._qimages.pop(item_id, None)
        if self.current is item:
            self.current = None
            self._owner_id = None
            idx = order.index(item_id) if item_id in order else 0
            rest = [i for i in order if i != item_id]
            if rest:
                self.select_item(rest[min(idx, len(rest) - 1)])
            else:
                self._show_current()
        self._refresh_all()

    # --------------------------------------------------------- selection
    def select_item(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None or item is self.current:
            return
        self._store_edits()
        self.current = item
        self.panel.select(item_id)
        self._show_current()

    def item_text(self, item: QueueItem) -> str:
        if self._owner_id == item.id and item is self.current:
            return self.result.editor.toPlainText()
        if item.text is not None:
            return item.text
        if item.result is not None:
            return item.result.text
        return item.history_text

    def _store_edits(self) -> None:
        item = self.items.get(self._owner_id) if self._owner_id else None
        if item is None:
            return
        text = self.result.editor.toPlainText()
        if item.result is not None:
            if text != item.result.text:
                item.text = text
                item.ranges = self.result.editor.export_state()
            else:
                item.text, item.ranges = None, None
        else:
            item.history_text = text

    def _show_current(self) -> None:
        item = self.current
        if item is None:
            self._owner_id = None
            self.stack.setCurrentWidget(self.workspace if self.items else self.empty)
            self.result.editor.clear_all()
            self.viewer.show_placeholder(S.viewer_no_image, "", "photo_off")
            self.viewer.set_enabled_tools(False)
            self.result.show_editor()
            self.result.set_actions_enabled(False)
            self.result.set_summary(None)
            self._refresh_all()
            return
        self.stack.setCurrentWidget(self.workspace)
        self._show_viewer(item)
        self._show_result(item)
        self._refresh_all()

    def _show_viewer(self, item: QueueItem) -> None:
        if not item.has_image or item.state == ItemState.ERROR and item.error_kind in ("missing", "unreadable"):
            self.viewer.show_placeholder(
                S.viewer_no_image if not item.has_image else S.err_unreadable_title,
                S.viewer_no_image_hint if not item.has_image else "",
                "photo_off")
            self.viewer.set_enabled_tools(False)
            return
        cached = self._qimages.get(item.id)
        if cached is not None:
            self._qimages.move_to_end(item.id)
            self.viewer.show_image(cached)
            self.viewer.set_enabled_tools(True)
            self._apply_overlays()
        else:
            self.viewer.show_placeholder(S.viewer_loading, "", "image")
            self.viewer.set_enabled_tools(False)
            self._pending_loads += 1
            self.loader.load_full(item.id, item.path or item.image)

    def _apply_overlays(self) -> None:
        item = self.current
        if item is None or not self.viewer.view.has_image:
            return
        self.viewer.view.set_result(item.result if item.state == ItemState.DONE else None)

    def _show_result(self, item: QueueItem) -> None:
        rp = self.result
        self._owner_id = None
        if item.from_history:
            rp.editor.load_plain(item.history_text)
            rp.show_editor()
            rp.set_history_summary(item.history_mode, item.confidence)
            rp.set_actions_enabled(True)
            rp.set_rerun_enabled(False)
            self._owner_id = item.id
        elif item.state == ItemState.DONE and item.result is not None:
            rp.editor.load_result(item.result, item.text, item.ranges)
            rp.show_editor()
            rp.set_summary(item.result, item.confidence)
            rp.set_actions_enabled(True)
            rp.set_rerun_enabled(item.has_image)
            self._owner_id = item.id
        elif item.state == ItemState.ERROR:
            title, msg = self._error_texts(item)
            rp.set_summary(None)
            rp.editor.clear_all()
            rp.show_error(title, msg, item.error_detail or item.error_message)
            rp.set_actions_enabled(False)
        else:
            rp.set_summary(None)
            rp.editor.clear_all()
            if item.state == ItemState.PROCESSING:
                rp.processing.show_running(_STAGE_TEXT.get(item.stage, S.stage_preparing), item.progress)
            else:
                rp.processing.show_queued(waiting_for_start=not item.submitted)
            rp.show_processing()
            rp.set_actions_enabled(False)

    # ---------------------------------------------------------- loaders
    def _on_thumb(self, item_id: str, thumb: QImage, size) -> None:
        self._pending_loads = max(0, self._pending_loads - 1)
        item = self.items.get(item_id)
        if item is None:
            return
        item.thumb = thumb
        if item.size is None:
            item.size = tuple(size)
        self.panel.update_item(item)

    def _on_full(self, item_id: str, qimg: QImage) -> None:
        self._pending_loads = max(0, self._pending_loads - 1)
        item = self.items.get(item_id)
        if item is None:
            return
        self._qimages[item_id] = qimg
        while len(self._qimages) > 4:
            self._qimages.popitem(last=False)
        if self.current is item:
            self.viewer.show_image(qimg)
            self.viewer.set_enabled_tools(True)
            self._apply_overlays()
            idx = self.result.editor._word_at_caret()
            if idx >= 0:
                self.viewer.view.set_selected_word(idx, ensure_visible=False)

    def _on_load_failed(self, item_id: str, kind: str, message: str) -> None:
        self._pending_loads = max(0, self._pending_loads - 1)
        item = self.items.get(item_id)
        if item is None or item.state == ItemState.ERROR:
            return
        if item.state == ItemState.DONE:
            return  # text exists; only the picture is unavailable
        self.runner.remove_waiting(item_id)
        self._mark_error(item, kind, message, message)
        self.panel.update_item(item)
        if self.current is item:
            self._show_current()
        self._refresh_all()

    # ------------------------------------------------------- runner slots
    def _on_started(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None:
            return
        item.state = ItemState.PROCESSING
        item.progress = 0.0
        item.stage = "preparing"
        self._job_t0 = time.perf_counter()
        self._elapsed_timer.start()
        self.panel.update_item(item)
        if self.current is item:
            self._show_result(item)
        self._refresh_all()

    def _on_progress(self, item_id: str, fraction: float, stage: str) -> None:
        item = self.items.get(item_id)
        if item is None or item.state != ItemState.PROCESSING:
            return
        item.progress, item.stage = fraction, stage
        row = self.panel.row_widget(item_id)
        if row:
            row.update_from(item)
        if self.current is item:
            self.result.processing.show_running(_STAGE_TEXT.get(stage, stage), fraction)
        self._refresh_status()

    def _on_finished(self, item_id: str, result) -> None:
        item = self.items.get(item_id)
        self._batch_done += 1
        if item is None:
            return
        item.result = result
        item.state = ItemState.DONE
        item.submitted = False
        item.progress = 1.0
        item.confidence = mean_confidence(result)
        item.text, item.ranges = None, None
        self._add_history(item)
        self.panel.update_item(item)
        if self.current is item:
            self._show_result(item)
            self._apply_overlays()
        self.itemFinished.emit(item_id)
        self._refresh_all()

    def _on_failed(self, item_id: str, kind: str, message: str, detail: str) -> None:
        item = self.items.get(item_id)
        self._batch_done += 1
        if item is None:
            return
        self._mark_error(item, kind, message, detail)
        self.panel.update_item(item)
        if self.current is item:
            self._show_current()
        self._refresh_all()

    def _on_cancelled(self, item_id: str) -> None:
        item = self.items.get(item_id)
        if item is None:
            return
        item.state = ItemState.QUEUED
        item.submitted = False
        item.progress = 0.0
        self.panel.update_item(item)
        if self.current is item:
            self._show_result(item)
        self._refresh_all()

    def _on_idle(self, idle: bool) -> None:
        if idle:
            self._elapsed_timer.stop()
            if self._cancelling:
                self._cancelling = False
                self._last_status = S.stage_cancelled
                self.show_toast(S.toast_cancelled)
            else:
                self._last_status = S.stage_done if self._batch_total else S.stage_idle
        self._refresh_all()
        self.idleChanged.emit(idle)

    def cancel_processing(self) -> bool:
        if self.runner.is_idle:
            return False
        self._cancelling = True
        self.runner.cancel_all()
        self._refresh_all()
        return True

    def escape_pressed(self) -> None:
        if self.result.find_open:
            self.result.close_find()
        elif self.drawer.is_open:
            self.close_history()
        elif not self.runner.is_idle:
            self.cancel_processing()

    # --------------------------------------------------------- history
    def _add_history(self, item: QueueItem) -> None:
        if item.result is None:
            return
        try:
            self.history_store.add(HistoryItem(
                id=uuid.uuid4().hex, source=item.name,
                created=datetime.now().astimezone().isoformat(timespec="seconds"),
                text=item.result.text, mode_used=item.result.mode_used,
                confidence=item.confidence))
            if self.drawer.is_open:
                self.drawer.set_items(self.history_store.list())
        except Exception:
            _log.exception("history add failed")

    def toggle_history(self) -> None:
        if self.drawer.is_open:
            self.close_history()
        else:
            self.drawer.set_items(self.history_store.list())
            self.drawer.reposition()
            self.drawer.open()

    def close_history(self) -> None:
        self.drawer.close_drawer()
        self.btn_history.setFocus()

    def open_history_item(self, hid: str) -> None:
        found = next((h for h in self.history_store.list() if h.id == hid), None)
        if found is None:
            return
        item = QueueItem(name=found.source, from_history=True, state=ItemState.DONE,
                         history_text=found.text, history_mode=found.mode_used,
                         confidence=found.confidence)
        self.items[item.id] = item
        self.panel.add_item(item)
        self.select_item(item.id)
        self.close_history()
        if not self.queue_open and len(self.items) > 1:
            self.toggle_queue(True)
        self._refresh_all()

    def delete_history_item(self, hid: str) -> None:
        self.history_store.delete(hid)
        self.drawer.set_items(self.history_store.list())

    def clear_history(self) -> None:
        if dialogs.ask_yes_no(self, S.history_clear, S.history_confirm_clear, S.history_clear, S.dlg_cancel):
            self.history_store.clear()
            self.drawer.set_items([])

    # ------------------------------------------------------ text actions
    def final_text(self, text: str) -> str:
        if self.settings.normalize_text:
            text = services.normalize_text(text)
        return services.convert_digits(text, self.settings.digit_style)

    def copy_all(self) -> None:
        text = self.result.editor.toPlainText() if self._owner_id else ""
        if not text.strip():
            self.show_toast(S.toast_nothing_to_copy)
            return
        QApplication.clipboard().setText(self.final_text(text))
        self.show_toast(S.toast_copied)

    def copy_selection(self) -> None:
        sel = self.result.editor.textCursor().selectedText().replace(" ", "\n")
        if not sel:
            self.show_toast(S.toast_nothing_to_copy)
            return
        QApplication.clipboard().setText(self.final_text(sel))
        self.show_toast(S.toast_copied_sel)

    def clear_text(self) -> None:
        ed = self.result.editor
        if not ed.toPlainText():
            return
        cur = ed.textCursor()
        cur.select(QTextCursor.Document)
        cur.removeSelectedText()
        ed.setTextCursor(cur)
        self.show_toast(S.toast_cleared, S.toast_undo, ed.undo)

    def _ask_save_path(self, default_name: str) -> Optional[tuple[str, str]]:
        start = str(Path(self.settings.last_save_dir or str(Path.home())) / default_name)
        flt = f"{S.dlg_save_filter_txt};;{S.dlg_save_filter_docx}"
        path, chosen = QFileDialog.getSaveFileName(self, S.dlg_save_title, start, flt)
        if not path:
            return None
        fmt = "docx" if (path.lower().endswith(".docx") or "docx" in chosen) and not path.lower().endswith(".txt") else "txt"
        if not path.lower().endswith("." + fmt):
            path += "." + fmt
        return path, fmt

    def save_current(self) -> None:
        item = self.current
        if item is None or not self._owner_id:
            return
        text = self.result.editor.toPlainText()
        picked = self._ask_save_path(Path(item.name).stem + ".txt")
        if not picked:
            return
        path, fmt = picked
        try:
            services.export_text(self.final_text(text), path, fmt)
        except NotImplementedError:
            dialogs.show_info(self, S.save, S.toast_docx_unavailable)
            return
        except OSError:
            _log.exception("save failed")
            self.show_toast(S.toast_save_failed)
            return
        self.settings.last_save_dir = str(Path(path).parent)
        self._save_settings()
        self.show_toast(S.toast_saved.format(name=wrap_ltr(Path(path).name)))

    def _ask_save_dir(self) -> str:
        d = QFileDialog.getExistingDirectory(self, S.save_all_choose_dir, self.settings.last_save_dir)
        return d

    @staticmethod
    def unique_path(folder: Path, stem: str, ext: str) -> Path:
        cand = folder / f"{stem}{ext}"
        n = 2
        while cand.exists():
            cand = folder / f"{stem} ({n}){ext}"
            n += 1
        return cand

    def save_all(self) -> None:
        self._store_edits() if self._owner_id else None
        done = [i for i in self.items.values()
                if i.state == ItemState.DONE and (i.result is not None or i.from_history)]
        if not done:
            self.show_toast(S.save_all_none)
            return
        folder = self._ask_save_dir()
        if not folder:
            return
        out = Path(folder)
        saved = 0
        for item in done:
            text = self.item_text(item)
            target = self.unique_path(out, Path(item.name).stem, ".txt")
            try:
                services.export_text(self.final_text(text), target, "txt")
                saved += 1
            except OSError:
                _log.exception("save_all failed for %s", item.name)
        self.settings.last_save_dir = folder
        self._save_settings()
        self.show_toast(S.save_all_done.format(n=fa_digits(saved)))

    def rerun(self, mode: str) -> None:
        item = self.current
        if item is None or not item.has_image or item.from_history:
            return
        if self._owner_id == item.id:
            ed_text = self.result.editor.toPlainText()
            if item.result is not None and ed_text != item.result.text:
                if not dialogs.ask_yes_no(self, S.confirm_rerun_title, S.confirm_rerun_msg):
                    return
        self._owner_id = None
        item.mode_override = mode  # type: ignore[assignment]
        self._submit([item])
        self._show_current()

    # --------------------------------------------------- paste / drop
    def paste_from_clipboard(self) -> None:
        if not self.handle_mime(QApplication.clipboard().mimeData()):
            self.show_toast(S.toast_no_image_in_clipboard)

    def handle_mime(self, mime: Optional[QMimeData]) -> bool:
        if mime is None:
            return False
        files = image_io.paths_from_mime(mime)
        if files:
            return bool(self.add_paths(files))
        if mime.hasImage():
            data = mime.imageData()
            qimg = QImage(data) if not isinstance(data, QImage) else data
            if isinstance(data, QPixmap):
                qimg = data.toImage()
            if qimg.isNull():
                return False
            self.add_image(image_io.qimage_to_pil(qimg))
            return True
        return False

    @staticmethod
    def _acceptable(mime: QMimeData) -> bool:
        return mime.hasImage() or bool(image_io.paths_from_mime(mime))

    def dragEnterEvent(self, event) -> None:
        if self._acceptable(event.mimeData()):
            event.acceptProposedAction()
            self._set_dragging(True)
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if self._acceptable(event.mimeData()):
            event.acceptProposedAction()

    def dragLeaveEvent(self, event) -> None:
        self._set_dragging(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event) -> None:
        self._set_dragging(False)
        if self.handle_mime(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _set_dragging(self, on: bool) -> None:
        if self.stack.currentWidget() is self.empty:
            self.empty.set_dragging(on)
            self.drop_overlay.hide()
        else:
            self.empty.set_dragging(False)
            self.drop_overlay.setGeometry(self.host.rect().adjusted(16, 16, -16, -16))
            self.drop_overlay.setVisible(on)
            if on:
                self.drop_overlay.raise_()

    # ----------------------------------------------------------- misc
    def _on_word_clicked(self, idx: int) -> None:
        self.result.editor.select_word(idx)

    def _on_stats(self, words: int, chars: int) -> None:
        if self.result.page == 0 and self._owner_id:
            self.counter_label.setText(S.counter_words_chars.format(w=fa_digits(words), c=fa_digits(chars)))
        else:
            self.counter_label.setText("")

    def show_toast(self, text: str, action: Optional[str] = None, callback=None) -> None:
        self.toast.show_message(text, action, callback)

    def _relayout_overlays(self) -> None:
        self.drawer.reposition()
        self.toast.place()
        if self.drop_overlay.isVisible():
            self.drop_overlay.setGeometry(self.host.rect().adjusted(16, 16, -16, -16))

    def _tick(self) -> None:
        self._refresh_status()

    def _refresh_all(self) -> None:
        self._refresh_status()
        done = sum(1 for i in self.items.values() if i.state == ItemState.DONE and not i.from_history)
        total = sum(1 for i in self.items.values() if not i.from_history)
        running = next((i for i in self.items.values() if i.state == ItemState.PROCESSING), None)
        frac = (done + (running.progress if running else 0.0)) / total if total else 0.0
        self.panel.set_overall(done, total, frac)
        has_todo = any(i.state == ItemState.QUEUED and not i.submitted for i in self.items.values())
        can_save = any(i.state == ItemState.DONE for i in self.items.values())
        self.panel.set_actions_state(has_todo, can_save, not self.runner.is_idle)
        if not self.items and self.stack.currentWidget() is not self.empty:
            self.stack.setCurrentWidget(self.empty)
        elif self.items and self.stack.currentWidget() is self.empty and self.current is not None:
            self.stack.setCurrentWidget(self.workspace)
        self._on_stats(*self.result.editor.stats())

    def _refresh_status(self) -> None:
        running = next((i for i in self.items.values() if i.state == ItemState.PROCESSING), None)
        if self._cancelling and not self.runner.is_idle:
            self.stage_label.setText(S.stage_cancelling)
            self.progress.setValue(0)
            self.elapsed_label.setText("")
            return
        if running is not None and not self.runner.is_idle:
            text = _STAGE_TEXT.get(running.stage, S.stage_preparing)
            if self._batch_total > 1:
                text = S.stage_with_queue.format(
                    stage=text, i=fa_digits(min(self._batch_done + 1, self._batch_total)),
                    n=fa_digits(self._batch_total))
            self.stage_label.setText(text)
            self.progress.setValue(int(running.progress * 1000))
            self.elapsed_label.setText(fa_clock(time.perf_counter() - self._job_t0))
        else:
            self.stage_label.setText(self._last_status)
            self.progress.setValue(0)
            cur = self.current
            if cur is not None and cur.result is not None and cur.state == ItemState.DONE:
                self.elapsed_label.setText(fa_clock(cur.result.elapsed_s))
            else:
                self.elapsed_label.setText("")

    # -------------------------------------------------- test / smoke helpers
    def is_busy(self) -> bool:
        return (not self.runner.is_idle) or self._pending_loads > 0

    def wait_idle(self, timeout_ms: int = 20000) -> bool:
        """Spin the event loop until all work and image loads have finished."""
        deadline = time.perf_counter() + timeout_ms / 1000
        while time.perf_counter() < deadline:
            QApplication.processEvents()
            if not self.is_busy():
                QApplication.processEvents()
                return True
            time.sleep(0.005)
        return False
