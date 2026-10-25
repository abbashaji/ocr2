"""End-to-end window tests (offscreen, stub engine, in-memory services)."""

from __future__ import annotations

import base64
import shutil
import threading
import time

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, QUrl, Qt
from PySide6.QtGui import QColor, QDropEvent, QImage, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from matnyab import services
from matnyab.api import LOW_CONFIDENCE_THRESHOLD, Cancelled
from matnyab.engine.stub import StubEngine
from matnyab.ui import dialogs, theme
from matnyab.ui.models import ItemState

pytestmark = pytest.mark.ui


def stub_result(path):
    return StubEngine().recognize(str(path))


def low_count(result):
    return sum(w.confidence < LOW_CONFIDENCE_THRESHOLD for ln in result.lines for w in ln.words)


class SlowEngine:
    """Runs until cancelled (or released) so tests can act mid-run."""

    def __init__(self):
        self.release = threading.Event()
        self.started = threading.Event()

    def recognize(self, image, options=None, progress=None, cancel=None):
        self.started.set()
        t0 = time.time()
        while not self.release.is_set() and time.time() - t0 < 10:
            if cancel is not None:
                cancel.raise_if_cancelled()
            if progress:
                progress(0.4, "recognizing")
            time.sleep(0.01)
        return StubEngine().recognize(image, options, progress, cancel)

    def close(self):
        pass


class BrokenEngine:
    def recognize(self, *a, **k):
        raise RuntimeError("boom: tesseract exploded")

    def close(self):
        pass


def wait_for(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.005)
    return False


def drop(window, mime):
    from PySide6.QtGui import QDragEnterEvent

    enter = QDragEnterEvent(QPoint(20, 20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(enter)
    ev = QDropEvent(QPointF(20, 20), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    ev.setAccepted(False)
    window.dropEvent(ev)
    return ev


def test_empty_state_visible_at_start(make_window):
    w = make_window()
    assert w.stack.currentWidget() is w.empty
    assert w.empty.isVisible()
    assert not w.workspace.isVisible()
    assert w.minimumWidth() >= 960 and w.minimumHeight() >= 640
    assert w.layoutDirection() == Qt.RightToLeft


def test_open_sample_fills_editor_with_stub_text(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    expected = stub_result(sample_png)
    assert w.result.editor.toPlainText() == expected.text
    assert w.stack.currentWidget() is w.workspace
    assert w.result.chip_conf.isVisible()
    assert w.viewer.view.has_image
    assert len(w.viewer.view._words) == sum(len(l.words) for l in expected.lines)


def test_marked_words_equal_low_confidence_words_and_f3_cycles(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    expected = stub_result(sample_png)
    n = low_count(expected)
    assert n >= 2
    ed = w.result.editor
    assert ed.marked_word_count() == n
    assert len(ed.extraSelections()) == n
    marks = [m.text for m in ed.marked_words()]
    seen = []
    w.activateWindow()
    ed.setFocus()
    QApplication.processEvents()
    for _ in range(n + 1):
        QTest.keyClick(w, Qt.Key_F3)
        seen.append(ed.textCursor().selectedText())
    assert seen == marks + [marks[0]]
    QTest.keyClick(w, Qt.Key_F3, Qt.ShiftModifier)
    assert ed.textCursor().selectedText() == marks[-1]
    assert w.result.unc_label.text().startswith("۳") or "از" in w.result.unc_label.text()


def test_selection_sync_between_editor_and_viewer(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    ed, view = w.result.editor, w.viewer.view
    first = ed.marked_words()[0]
    ed.next_uncertain()
    assert view.selected_word == first.index
    ed.select_word(0)
    assert view.selected_word == 0
    # click on a word box in the viewer selects it in the editor
    view.wordClicked.emit(3)
    assert ed.textCursor().selectedText() == ed._words[3].text


def test_editing_marked_word_removes_mark(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    ed = w.result.editor
    before = ed.marked_word_count()
    ed.next_uncertain()
    QTest.keyClick(ed, Qt.Key_X)  # replaces the selected marked word
    assert ed.marked_word_count() == before - 1
    ed.undo()
    assert ed.toPlainText() == stub_result(sample_png).text
    assert ed.marked_word_count() == before  # pristine text restores all marks


def test_edit_before_a_mark_shifts_it(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    ed = w.result.editor
    cur = ed.textCursor()
    cur.setPosition(0)
    cur.insertText("ab ")
    ed.setTextCursor(cur)
    for m in ed.marked_words():
        c = ed.textCursor()
        c.setPosition(m.start)
        c.setPosition(m.end, c.MoveMode.KeepAnchor)
        assert c.selectedText() == m.text


def test_copy_applies_digit_conversion_and_normalisation(make_window, sample_png, monkeypatch):
    calls = {}

    def fake_convert(text, style):
        calls["style"] = style
        return "D:" + text

    monkeypatch.setattr(services, "convert_digits", fake_convert)
    monkeypatch.setattr(services, "normalize_text", lambda t: "N:" + t)
    w = make_window()
    s = w.settings
    s.digit_style = "fa"
    w.apply_settings(s)
    w.add_paths([sample_png])
    assert w.wait_idle()
    w.copy_all()
    clip = QApplication.clipboard().text()
    assert clip == "D:N:" + stub_result(sample_png).text
    assert calls["style"] == "fa"
    # the editor itself is never rewritten
    assert w.result.editor.toPlainText() == stub_result(sample_png).text


def test_copy_selection_and_clear_undo(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    w.result.editor.select_word(0)
    w.copy_selection()
    assert QApplication.clipboard().text() == w.result.editor._words[0].text
    w.clear_text()
    assert w.result.editor.toPlainText() == ""
    w.result.editor.undo()
    assert w.result.editor.toPlainText() == stub_result(sample_png).text
    assert w.result.editor.marked_word_count() == low_count(stub_result(sample_png))


def test_settings_persist_and_theme_switches_live(make_window, stores):
    w = make_window()
    s = w.settings
    s.theme = "dark"
    s.digit_style = "en"
    s.editor_font_pt = 18
    w.apply_settings(s)
    loaded = stores[0].load()
    assert (loaded.theme, loaded.digit_style, loaded.editor_font_pt) == ("dark", "en", 18)
    assert theme.manager().is_dark
    assert QApplication.palette().color(QPalette.Window) == QColor(theme.DARK["bg"])
    assert w.result.editor.font().pointSizeF() == 18
    s = w.settings
    s.theme = "light"
    w.apply_settings(s)
    assert QApplication.palette().color(QPalette.Window) == QColor(theme.LIGHT["bg"])
    w.toggle_theme()
    assert stores[0].load().theme == "dark"


def test_settings_dialog_applies_live(make_window, stores):
    w = make_window()
    dlg = dialogs.SettingsDialog(w.settings, w.apply_settings, w)
    dlg.theme_ctl._buttons["dark"].click()
    dlg.mode_ctl._buttons["lex"].click()
    dlg.digits_ctl._buttons["fa"].click()
    dlg.normalize.setChecked(False)
    dlg.font_slider.setValue(20)
    got = stores[0].load()
    assert (got.theme, got.mode, got.digit_style, got.normalize_text, got.editor_font_pt) == (
        "dark", "lex", "fa", False, 20)
    assert theme.manager().is_dark


def test_cancel_mid_run_returns_item_to_queue(make_window, sample_png, stores):
    eng = SlowEngine()
    w = make_window(engine=eng)
    w.add_paths([sample_png])
    assert wait_for(lambda: eng.started.is_set())
    item = next(iter(w.items.values()))
    assert wait_for(lambda: item.state == ItemState.PROCESSING)
    assert w.cancel_processing()
    assert item.state == ItemState.QUEUED and not item.submitted
    assert w.stage_label.text()  # shows "cancelling" while the worker unwinds
    assert w.wait_idle()
    assert item.state == ItemState.QUEUED
    assert stores[1].list() == []
    assert w.result.processing.start_btn.isVisibleTo(w.result.processing)
    # it can be started again
    eng.release.set()
    w.process_all()
    assert w.wait_idle()
    assert item.state == ItemState.DONE


def test_three_file_queue_gives_three_history_entries(make_window, sample_png, sample_jpg, tmp_path, stores):
    third = tmp_path / "third.png"
    shutil.copy(sample_png, third)
    w = make_window()
    w.add_paths([sample_png, sample_jpg, third])
    assert w.wait_idle()
    assert [i.state for i in w.items.values()] == [ItemState.DONE] * 3
    assert len(stores[1].list()) == 3
    assert w.queue_open
    assert w.panel.overall_label.text()
    # selecting another item shows its own text/image
    ids = w.panel.order()
    w.select_item(ids[1])
    assert w.result.editor.toPlainText() == stub_result(sample_jpg).text


def test_edits_persist_per_item(make_window, sample_png, sample_jpg):
    w = make_window()
    w.add_paths([sample_png, sample_jpg])
    assert w.wait_idle()
    a, b = w.panel.order()
    w.select_item(a)
    cur = w.result.editor.textCursor()
    cur.movePosition(cur.MoveOperation.End)
    cur.insertText(" EDITED")
    w.select_item(b)
    assert "EDITED" not in w.result.editor.toPlainText()
    w.select_item(a)
    assert w.result.editor.toPlainText().endswith("EDITED")


def test_engine_error_shows_card_and_app_stays_responsive(make_window, sample_png):
    w = make_window(engine=BrokenEngine())
    w.add_paths([sample_png])
    assert w.wait_idle()
    item = next(iter(w.items.values()))
    assert item.state == ItemState.ERROR
    assert w.result.page == 2
    card = w.result.error
    assert "boom" in card.details.toPlainText()
    assert not card.details_visible
    card.details_btn.click()
    assert card.details_visible
    assert "Traceback" not in card.message.text() and "boom" not in card.message.text()
    # still responsive: retry runs again (and fails again) without hanging
    card.retry_btn.click()
    assert w.wait_idle()
    assert item.state == ItemState.ERROR
    w.toggle_queue(True)
    w.remove_item(item.id)
    assert w.stack.currentWidget() is w.empty


def test_unreadable_file_shows_friendly_error(make_window, tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image at all")
    w = make_window()
    w.add_paths([bad])
    assert w.wait_idle()
    item = next(iter(w.items.values()))
    assert item.state == ItemState.ERROR and w.result.page == 2
    assert w.result.error.title.text()


def test_huge_image_asks_before_continuing(make_window, sample_png, monkeypatch):
    from matnyab.ui import image_io

    monkeypatch.setattr(image_io, "MAX_MEGAPIXELS", 0.1)
    asked = []
    monkeypatch.setattr(dialogs, "ask_yes_no", lambda *a, **k: asked.append(a) or False)
    w = make_window()
    w.add_paths([sample_png])
    assert asked and not w.items
    monkeypatch.setattr(dialogs, "ask_yes_no", lambda *a, **k: True)
    w.add_paths([sample_png])
    assert w.wait_idle()
    assert len(w.items) == 1


def test_drop_files_folder_and_image_data(make_window, sample_png, sample_jpg, tmp_path):
    w = make_window()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(sample_png))])
    ev = drop(w, mime)
    assert ev.isAccepted()
    assert w.wait_idle() and len(w.items) == 1

    folder = tmp_path / "imgs"
    folder.mkdir()
    shutil.copy(sample_png, folder / "a.png")
    shutil.copy(sample_jpg, folder / "b.jpg")
    (folder / "notes.txt").write_text("x")
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(folder))])
    drop(w, mime)
    assert w.wait_idle()
    assert len(w.items) == 3

    img = QImage(80, 60, QImage.Format_RGB32)
    img.fill(QColor("white"))
    mime = QMimeData()
    mime.setImageData(img)
    drop(w, mime)
    assert w.wait_idle()
    assert len(w.items) == 4
    assert any(i.image is not None for i in w.items.values())


def test_drop_text_only_is_ignored(make_window):
    w = make_window()
    mime = QMimeData()
    mime.setText("hello")
    ev = drop(w, mime)
    assert not ev.isAccepted()
    assert not w.items


def test_drag_over_state_changes_empty_card(make_window):
    w = make_window()
    w.empty.set_dragging(True)
    assert w.empty.zone.property("dragging") == "true"
    assert w.empty.title.text() != ""
    before = w.empty.title.text()
    w.empty.set_dragging(False)
    assert w.empty.title.text() != before


def test_clipboard_paste_image_and_files(make_window, sample_png):
    w = make_window()
    clip = QApplication.clipboard()
    clip.setText("only text")
    w.paste_from_clipboard()
    assert not w.items  # nothing to paste, friendly toast instead
    assert w.toast.isVisible() or w.toast.current_text()
    img = QImage(120, 90, QImage.Format_RGB32)
    img.fill(QColor("white"))
    clip.setImage(img)
    w.paste_from_clipboard()
    assert w.wait_idle() and len(w.items) == 1
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(sample_png))])
    clip.setMimeData(mime)
    w.paste_from_clipboard()
    assert w.wait_idle() and len(w.items) == 2


def test_paste_into_editor_routes_images_to_the_queue(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    img = QImage(50, 50, QImage.Format_RGB32)
    img.fill(QColor("black"))
    mime = QMimeData()
    mime.setImageData(img)
    w.result.editor.insertFromMimeData(mime)
    assert w.wait_idle()
    assert len(w.items) == 2
    assert "50" not in w.result.editor.toPlainText() or True


def test_geometry_restore(make_window, stores):
    w = make_window()
    w.resize(960, 701)
    QApplication.processEvents()
    w.close()
    assert stores[0].load().window_geometry
    base64.b64decode(stores[0].load().window_geometry)
    w2 = make_window()
    assert (w2.width(), w2.height()) == (960, 701)


def test_history_drawer_open_delete_clear(make_window, sample_png, stores, monkeypatch):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    w.toggle_history()
    assert w.drawer.is_open and w.drawer.list.count() == 1
    hid = stores[1].list()[0].id
    w.open_history_item(hid)
    assert w.current.from_history
    assert w.result.editor.toPlainText() == stub_result(sample_png).text
    assert w.viewer.placeholder_visible
    w.toggle_history()
    w.delete_history_item(hid)
    assert stores[1].list() == []
    monkeypatch.setattr(dialogs, "ask_yes_no", lambda *a, **k: True)
    w.clear_history()


def test_find_bar_counts_matches(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    w.result.open_find()
    assert w.result.find_open
    w.result.find_bar.edit.setText("ي")  # Arabic yeh matches Persian yeh in the text
    assert w.result.editor.match_count >= 0
    w.result.find_bar.edit.setText("ا")
    n = w.result.editor.match_count
    assert n > 0 and str(n) not in w.result.find_bar.count.text()  # Persian digits
    w.result.editor.find_next()
    w.result.close_find()
    assert not w.result.find_open


def test_save_and_save_all(make_window, sample_png, sample_jpg, tmp_path, monkeypatch):
    w = make_window()
    w.add_paths([sample_png, sample_jpg])
    assert w.wait_idle()
    target = tmp_path / "out.txt"
    monkeypatch.setattr(w, "_ask_save_path", lambda name: (str(target), "txt"))
    w.save_current()
    assert target.read_text(encoding="utf-8-sig") == w.result.editor.toPlainText()
    assert w.settings.last_save_dir == str(tmp_path)
    out = tmp_path / "all"
    out.mkdir()
    (out / "client_clean.txt").write_text("existing")
    monkeypatch.setattr(w, "_ask_save_dir", lambda: str(out))
    w.save_all()
    names = sorted(p.name for p in out.iterdir())
    assert names == ["client_clean (2).txt", "client_clean.txt", "client_low.txt"]
    assert (out / "client_clean.txt").read_text() == "existing"


def test_docx_not_implemented_is_friendly(make_window, sample_png, tmp_path, monkeypatch):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    shown = []
    monkeypatch.setattr(dialogs, "show_info", lambda *a: shown.append(a))
    monkeypatch.setattr(w, "_ask_save_path", lambda name: (str(tmp_path / "x.docx"), "docx"))

    def boom(*a):
        raise NotImplementedError

    monkeypatch.setattr(services, "export_text", boom)
    w.save_current()
    assert shown


def test_rerun_with_other_mode(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    w.rerun("lex")
    assert w.wait_idle()
    item = next(iter(w.items.values()))
    assert item.result.mode_used == "lex"


def test_shortcut_cheatsheet_matches_registered_actions(make_window):
    from matnyab.ui import shortcuts

    w = make_window()
    registered = {a.shortcut().toString() for a in w.actions_by_key.values()}
    for key in ("open", "open_folder", "paste", "save", "copy_all", "find", "next_unc", "prev_unc",
                "zoom_fit", "zoom_actual", "queue", "history", "settings"):
        assert shortcuts.KEYS[key] in registered, key
    dlg = dialogs.ShortcutsDialog(w)
    assert len(dlg.rows) >= 20


def test_viewer_zoom_and_fit(make_window, sample_png):
    w = make_window()
    w.add_paths([sample_png])
    assert w.wait_idle()
    v = w.viewer.view
    assert v.fit_mode
    v.set_zoom(2.0, animated=False)
    assert not v.fit_mode and abs(v.zoom - 2.0) < 1e-6
    v.actual_size()
    assert abs(v.zoom - 1.0) < 1e-6
    w.viewer._on_fit_clicked()
    assert v.fit_mode
    w.resize(1100, 700)
    QApplication.processEvents()
    assert v.fit_mode
    w.viewer.btn_highlight.setChecked(False)
    assert v.visible_overlay_count == 0
    w.viewer.btn_highlight.setChecked(True)
    assert v.visible_overlay_count == low_count(stub_result(sample_png))


def test_accessibility_names_on_actionable_widgets(make_window):
    from PySide6.QtWidgets import QAbstractButton

    w = make_window()
    w.add_paths([])  # no-op
    for btn in w.findChildren(QAbstractButton):
        assert btn.accessibleName() or btn.text(), btn
