from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor

from matnyab.ui.editor import ResultEditor


def test_persian_text_is_right_aligned_rtl(qapp):
    """Regression: Qt defaults to AlignLeft, which left-aligned (and ragged) Persian text."""
    ed = ResultEditor()
    ed.resize(520, 200)
    ed.load_plain("این یک متن آزمایشی است\nبرای بررسی رابط کاربری")
    block = ed.document().firstBlock()
    while block.isValid():
        fmt = block.blockFormat()
        assert fmt.layoutDirection() == Qt.RightToLeft
        assert fmt.alignment() & Qt.AlignRight
        block = block.next()
    ed.show()
    qapp.processEvents()
    ed.moveCursor(QTextCursor.Start)
    # Caret at the start of an RTL line sits at the right edge, not mid-widget.
    assert ed.cursorRect().x() > ed.viewport().width() * 0.9
    assert ed.document().defaultTextOption().alignment() & Qt.AlignRight
