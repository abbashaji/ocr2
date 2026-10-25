"""Regression tests for defects found during the QA pass (each one failed before its fix)."""

from __future__ import annotations

import pytest

from matnyab.api import HistoryItem

pytestmark = pytest.mark.ui


def _fill_history(store, n: int) -> None:
    for i in range(n):
        store.add(HistoryItem(
            id=f"h{i}", source=f"تصویر شماره {i} با نام خیلی خیلی طولانی برای آزمایش.png",
            created=f"2026-10-{(i % 27) + 1:02d}T10:00:00", mode_used="raw", confidence=85.0,
            text="ایران با نام رسمی جمهوری اسلامی ایران کشوری در غرب آسیا است " * 3))


@pytest.mark.parametrize("count", [3, 12])
def test_history_drawer_has_no_horizontal_scrollbar(real_window, real_stores, count):
    """Defect: the history list showed a horizontal scrollbar (and a corner box) because rows
    were wider than the list viewport, with or without a vertical scrollbar."""
    from PySide6.QtWidgets import QApplication

    _fill_history(real_stores[1], count)
    w = real_window()
    w.toggle_history()
    QApplication.processEvents()
    lst = w.drawer.list
    assert lst.count() == count
    hbar = lst.horizontalScrollBar()
    assert hbar.maximum() == 0 and not hbar.isVisible(), (hbar.maximum(), hbar.isVisible())
    row_w = lst.itemWidget(lst.item(0)).width()
    assert row_w <= lst.viewport().width(), (row_w, lst.viewport().width())
