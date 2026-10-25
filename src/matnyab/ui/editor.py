"""Result editor: RTL text with wavy marks on uncertain words, navigation and find."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import (
    QFont, QKeySequence, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextOption,
)
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QTextEdit, QWidget,
)

from matnyab.api import LOW_CONFIDENCE_THRESHOLD, OcrResult
from matnyab.ui import theme
from matnyab.ui.format import fa_digits
from matnyab.ui.image_io import paths_from_mime
from matnyab.ui.models import uncertain_level
from matnyab.ui.strings import S
from matnyab.ui.widgets import tool_button

__all__ = ["ResultEditor", "FindBar", "fold_for_search"]

# (variant, canonical) code points: Arabic yeh/kaf/heh/alef forms -> Persian forms.
_FOLD = {
    0x064A: "\u06cc", 0x0649: "\u06cc", 0x0643: "\u06a9", 0x0629: "\u0647",
    0x0623: "\u0627", 0x0625: "\u0627", 0x0671: "\u0627",
}
_FOLD.update({0x06F0 + i: 0x30 + i for i in range(10)})
_FOLD.update({0x0660 + i: 0x30 + i for i in range(10)})


def fold_for_search(text: str) -> str:
    """Length-preserving fold: Arabic/Persian letter and digit variants compare equal."""
    folded = text.translate(_FOLD)
    lowered = folded.lower()
    return lowered if len(lowered) == len(folded) else folded


def _u16(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


@dataclass
class _Word:
    index: int
    text: str
    confidence: float
    start: int  # UTF-16 offsets, as QTextDocument positions
    end: int
    alive: bool = True
    o_start: int = 0  # position in the untouched OCR text
    o_end: int = 0

    @property
    def uncertain(self) -> bool:
        return self.confidence < LOW_CONFIDENCE_THRESHOLD


class ResultEditor(QPlainTextEdit):
    wordSelected = Signal(int)            # word index under the caret (-1 = none)
    uncertainChanged = Signal(int, int)   # (1-based index of the caret word or 0, total)
    statsChanged = Signal(int, int)       # words, characters
    mediaPasted = Signal(object)          # QMimeData with an image or files
    fontStep = Signal(int)
    copySelectionRequested = Signal()
    findChanged = Signal(int, int)        # (1-based current match or 0, total)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._words: list[_Word] = []
        self._original = ""
        self._loading = False
        self._last_word = -1
        self._query = ""
        self._matches: list[tuple[int, int]] = []
        self._match_i = -1
        self.setAcceptDrops(True)
        self.setLayoutDirection(Qt.RightToLeft)
        opt = QTextOption()
        opt.setTextDirection(Qt.RightToLeft)
        # Qt's default alignment is AlignLeft; RTL text must be flush right.
        opt.setAlignment(Qt.AlignRight)
        opt.setWrapMode(QTextOption.WordWrap)
        self.document().setDefaultTextOption(opt)
        self.setPlaceholderText(S.editor_placeholder)
        self.setTabChangesFocus(True)
        self.setAccessibleName(S.editor_access)
        self.setAccessibleDescription(S.editor_access_desc)
        self.document().contentsChange.connect(self._on_contents_change)
        self.cursorPositionChanged.connect(self._on_cursor)
        self.textChanged.connect(self._emit_stats)
        theme.manager().changed.connect(self.refresh_marks)

    # ------------------------------------------------------------- font ---
    def set_font_pt(self, pt: int) -> None:
        font = QFont(theme.FONT_FAMILY)
        font.setPointSizeF(float(pt))
        font.setStyleStrategy(QFont.PreferAntialias)
        self.setFont(font)
        self.document().setDefaultFont(font)

    # ---------------------------------------------------------- loading ---
    def load_result(self, result: OcrResult, text: Optional[str] = None,
                    ranges: Optional[list] = None) -> None:
        """Show ``result.text`` (or the user's edited ``text`` with saved ``ranges``)."""
        self._loading = True
        try:
            self._original = result.text
            self._build_words(result)
            self._set_text(result.text if text is None else text)
            if text is not None and text != result.text and ranges is not None:
                for w, (start, end, alive) in zip(self._words, ranges):
                    w.start, w.end, w.alive = start, end, alive
            elif text is not None and text != result.text:
                for w in self._words:
                    w.alive = False
        finally:
            self._loading = False
        self._after_load()

    def load_plain(self, text: str) -> None:
        self._loading = True
        try:
            self._original = text
            self._words = []
            self._set_text(text)
        finally:
            self._loading = False
        self._after_load()

    def clear_all(self) -> None:
        self.load_plain("")

    def _set_text(self, text: str) -> None:
        self.setPlainText(text)
        cur = QTextCursor(self.document())
        cur.select(QTextCursor.Document)
        fmt = QTextBlockFormat()
        fmt.setLineHeight(150.0, QTextBlockFormat.ProportionalHeight.value)
        fmt.setLayoutDirection(Qt.RightToLeft)
        fmt.setAlignment(Qt.AlignRight)
        cur.mergeBlockFormat(fmt)
        self.document().clearUndoRedoStacks()
        self.moveCursor(QTextCursor.Start)

    def _after_load(self) -> None:
        self._last_word = -1
        self._query = ""
        self._matches = []
        self._match_i = -1
        self.refresh_marks()
        self._emit_stats()
        self._emit_uncertain()
        self.findChanged.emit(0, 0)

    def _build_words(self, result: OcrResult) -> None:
        self._words = []
        offset, idx = 0, 0
        for line in result.lines:
            for w in line.words:
                end = offset + _u16(w.text)
                self._words.append(_Word(idx, w.text, w.confidence, offset, end, True, offset, end))
                idx += 1
                offset = end + 1  # a space, or the newline after the last word
            if not line.words:
                offset += _u16(line.text) + 1

    def export_state(self) -> list:
        """Word ranges to restore together with an edited text."""
        return [(w.start, w.end, w.alive) for w in self._words]

    # ------------------------------------------------------------ marks ---
    def marked_words(self) -> list[_Word]:
        return sorted((w for w in self._words if w.alive and w.uncertain), key=lambda w: w.start)

    def marked_word_count(self) -> int:
        return len(self.marked_words())

    def refresh_marks(self) -> None:
        sels: list[QTextEdit.ExtraSelection] = []
        c = theme.color
        doc = self.document()
        for w in self.marked_words():
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(doc)
            cur.setPosition(w.start)
            cur.setPosition(w.end, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            poor = uncertain_level(w.confidence) == 2
            fmt.setUnderlineStyle(QTextCharFormat.WaveUnderline)
            fmt.setUnderlineColor(c("error_line" if poor else "warning_line"))
            fmt.setBackground(c("error_bg" if poor else "warning_bg"))
            sel.cursor, sel.format = cur, fmt
            sels.append(sel)
        for i, (s, e) in enumerate(self._matches):
            sel = QTextEdit.ExtraSelection()
            cur = QTextCursor(doc)
            cur.setPosition(s)
            cur.setPosition(e, QTextCursor.KeepAnchor)
            fmt = QTextCharFormat()
            if i == self._match_i:
                fmt.setBackground(c("accent"))
                fmt.setForeground(c("text_on_accent"))
            else:
                fmt.setBackground(c("accent_soft"))
            sel.cursor, sel.format = cur, fmt
            sels.append(sel)
        self.setExtraSelections(sels)

    def _on_contents_change(self, pos: int, removed: int, added: int) -> None:
        if self._loading:
            return
        if self._words:
            if self.toPlainText() == self._original:
                self._restore_pristine()
            else:
                self._shift_words(pos, removed, added)
        if self._query:
            self._recompute_matches(keep_position=True)
        self.refresh_marks()
        self._emit_uncertain()

    def _restore_pristine(self) -> None:
        for w in self._words:
            w.start, w.end, w.alive = w.o_start, w.o_end, True

    def _shift_words(self, pos: int, removed: int, added: int) -> None:
        inserted = ""
        if added:
            cur = QTextCursor(self.document())
            cur.setPosition(pos)
            cur.setPosition(min(pos + added, self.document().characterCount() - 1),
                            QTextCursor.KeepAnchor)
            inserted = cur.selectedText()
        delta = added - removed
        glued = bool(inserted) and not inserted[0].isspace() and inserted[0] != " "
        for w in self._words:
            if not w.alive:
                continue
            if pos > w.end:
                continue
            if pos == w.end:
                if removed == 0 and glued:
                    w.alive = False
                continue
            if pos + removed <= w.start:
                if pos == w.start and removed == 0 and glued:
                    w.alive = False
                    continue
                w.start += delta
                w.end += delta
                continue
            w.alive = False

    # ------------------------------------------------------- navigation ---
    def _word_at_caret(self) -> int:
        cur = self.textCursor()
        pos = cur.selectionStart() if cur.hasSelection() else cur.position()
        for w in self._words:
            if w.alive and w.start <= pos < w.end:
                return w.index
        for w in self._words:
            if w.alive and pos == w.end and not cur.hasSelection():
                return w.index
        return -1

    def _on_cursor(self) -> None:
        idx = self._word_at_caret()
        if idx != self._last_word:
            self._last_word = idx
            self.wordSelected.emit(idx)
        self._emit_uncertain()

    def select_word(self, index: int) -> bool:
        for w in self._words:
            if w.index == index and w.alive:
                cur = QTextCursor(self.document())
                cur.setPosition(w.start)
                cur.setPosition(w.end, QTextCursor.KeepAnchor)
                self.setTextCursor(cur)
                self.ensureCursorVisible()
                return True
        return False

    def _emit_uncertain(self) -> None:
        marks = self.marked_words()
        cur_i = 0
        idx = self._word_at_caret()
        for i, w in enumerate(marks, 1):
            if w.index == idx:
                cur_i = i
                break
        self.uncertainChanged.emit(cur_i, len(marks))

    def go_to_uncertain(self, forward: bool = True) -> bool:
        marks = self.marked_words()
        if not marks:
            return False
        cur = self.textCursor()
        sel_idx = self._word_at_caret() if cur.hasSelection() else -1
        pos = cur.selectionStart() if cur.hasSelection() else cur.position()
        target: Optional[_Word] = None
        if forward:
            for w in marks:
                if (w.start > pos) if sel_idx >= 0 else (w.start >= pos):
                    target = w
                    break
            target = target or marks[0]
        else:
            for w in reversed(marks):
                if w.start < pos:
                    target = w
                    break
            target = target or marks[-1]
        return self.select_word(target.index)

    def next_uncertain(self) -> bool:
        return self.go_to_uncertain(True)

    def prev_uncertain(self) -> bool:
        return self.go_to_uncertain(False)

    # ------------------------------------------------------------- stats ---
    def stats(self) -> tuple[int, int]:
        text = self.toPlainText()
        return len(text.split()), len(text.replace("\n", ""))

    def _emit_stats(self) -> None:
        w, c = self.stats()
        self.statsChanged.emit(w, c)

    # -------------------------------------------------------------- find ---
    def find_set_query(self, query: str) -> None:
        self._query = query
        self._match_i = -1
        self._recompute_matches(keep_position=False)
        if self._matches:
            self._go_to_match(self._nearest_match(self.textCursor().selectionStart()))
        self.refresh_marks()

    def _recompute_matches(self, keep_position: bool) -> None:
        prev = self._matches[self._match_i] if keep_position and 0 <= self._match_i < len(self._matches) else None
        self._matches = []
        q = fold_for_search(self._query)
        if q:
            text = self.toPlainText()
            hay = fold_for_search(text)
            bmp = all(ord(ch) < 0x10000 for ch in text)
            start = 0
            while True:
                i = hay.find(q, start)
                if i < 0:
                    break
                s = i if bmp else _u16(text[:i])
                e = s + (len(q) if bmp else _u16(text[i:i + len(q)]))
                self._matches.append((s, e))
                start = i + max(1, len(q))
        if prev is not None and prev in self._matches:
            self._match_i = self._matches.index(prev)
        elif keep_position and self._matches:
            self._match_i = min(max(self._match_i, 0), len(self._matches) - 1)
        else:
            self._match_i = -1
        self.findChanged.emit(self._match_i + 1 if self._match_i >= 0 else 0, len(self._matches))

    def _nearest_match(self, pos: int) -> int:
        for i, (s, _e) in enumerate(self._matches):
            if s >= pos:
                return i
        return 0

    def _go_to_match(self, i: int) -> None:
        if not self._matches:
            return
        self._match_i = i % len(self._matches)
        s, e = self._matches[self._match_i]
        cur = QTextCursor(self.document())
        cur.setPosition(s)
        cur.setPosition(e, QTextCursor.KeepAnchor)
        self.setTextCursor(cur)
        self.ensureCursorVisible()
        self.findChanged.emit(self._match_i + 1, len(self._matches))
        self.refresh_marks()

    def find_next(self) -> None:
        if self._matches:
            self._go_to_match(self._match_i + 1)

    def find_prev(self) -> None:
        if self._matches:
            self._go_to_match(self._match_i - 1 if self._match_i > 0 else len(self._matches) - 1)

    def find_clear(self) -> None:
        self._query = ""
        self._matches = []
        self._match_i = -1
        self.findChanged.emit(0, 0)
        self.refresh_marks()

    @property
    def match_count(self) -> int:
        return len(self._matches)

    # ------------------------------------------------------------ events ---
    def keyPressEvent(self, event) -> None:
        if event.matches(QKeySequence.Copy) and self.textCursor().hasSelection():
            self.copySelectionRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.ControlModifier:
            step = 1 if event.angleDelta().y() > 0 else -1
            self.fontStep.emit(step)
            event.accept()
            return
        super().wheelEvent(event)

    @staticmethod
    def _carries_media(mime: QMimeData) -> bool:
        return mime.hasImage() or bool(paths_from_mime(mime))

    def canInsertFromMimeData(self, source: QMimeData) -> bool:
        if self._carries_media(source):
            return True
        return super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source: QMimeData) -> None:
        if self._carries_media(source):
            self.mediaPasted.emit(source)
            return
        super().insertFromMimeData(source)

    def dragEnterEvent(self, event) -> None:
        if self._carries_media(event.mimeData()):
            event.ignore()  # let the main window handle files and images
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:
        if self._carries_media(event.mimeData()):
            event.ignore()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:
        if self._carries_media(event.mimeData()):
            event.ignore()
            return
        super().dropEvent(event)


class FindBar(QFrame):
    queryChanged = Signal(str)
    nextRequested = Signal()
    prevRequested = Signal()
    closed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("panelFlat")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(theme.SP_2, theme.SP_1, theme.SP_2, theme.SP_1)
        lay.setSpacing(theme.SP_1)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(S.find_placeholder)
        self.edit.setClearButtonEnabled(False)
        self.edit.setAccessibleName(S.find_placeholder)
        self.edit.setAccessibleDescription(S.find)
        self.count = QLabel("")
        self.count.setProperty("role", "muted")
        self.count.setMinimumWidth(64)
        self.count.setAlignment(Qt.AlignCenter)
        self.count.setAccessibleName(S.find)
        self.btn_prev = tool_button("chevron_up", S.find_prev, "Shift+Enter")
        self.btn_next = tool_button("chevron_down", S.find_next, "Enter")
        self.btn_close = tool_button("close", S.find_close, "Esc")
        lay.addWidget(self.edit, 1)
        lay.addWidget(self.count)
        lay.addWidget(self.btn_prev)
        lay.addWidget(self.btn_next)
        lay.addWidget(self.btn_close)
        self.edit.textChanged.connect(self.queryChanged)
        self.edit.returnPressed.connect(self._enter)
        self.btn_next.clicked.connect(self.nextRequested)
        self.btn_prev.clicked.connect(self.prevRequested)
        self.btn_close.clicked.connect(self.closed)
        self.setTabOrder(self.edit, self.btn_prev)
        self.setTabOrder(self.btn_prev, self.btn_next)
        self.setTabOrder(self.btn_next, self.btn_close)
        self.hide()

    def _enter(self) -> None:
        from PySide6.QtWidgets import QApplication

        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            self.prevRequested.emit()
        else:
            self.nextRequested.emit()

    def set_counts(self, current: int, total: int) -> None:
        if not self.edit.text():
            self.count.setText("")
        elif total == 0:
            self.count.setText(S.find_none)
        else:
            self.count.setText(S.find_count.format(i=fa_digits(current), n=fa_digits(total)))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.closed.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def open(self) -> None:
        self.show()
        self.edit.setFocus()
        self.edit.selectAll()
