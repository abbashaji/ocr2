from PySide6.QtCore import Qt

from matnyab.ui.widgets import SegmentedControl, push_button, tool_button


def test_buttons_take_focus_from_keyboard_only(qapp):
    """Mouse clicks must not leave the blue focus ring; Tab navigation still shows it."""
    assert tool_button(None, "x", checkable=True).focusPolicy() == Qt.TabFocus
    assert push_button("x").focusPolicy() == Qt.TabFocus
    seg = SegmentedControl([("a", "A"), ("b", "B")])
    for b in seg.findChildren(type(tool_button(None, "x"))):
        assert b.focusPolicy() == Qt.TabFocus
