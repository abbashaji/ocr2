"""Single source of truth for keyboard shortcuts (window actions and the cheat-sheet)."""

from __future__ import annotations

from matnyab.ui.strings import S

__all__ = ["KEYS", "groups"]

KEYS: dict[str, str] = {
    "open": "Ctrl+O",
    "open_folder": "Ctrl+Shift+O",
    "paste": "Ctrl+V",
    "save": "Ctrl+S",
    "copy_all": "Ctrl+Shift+C",
    "copy_sel": "Ctrl+C",
    "find": "Ctrl+F",
    "next_unc": "F3",
    "prev_unc": "Shift+F3",
    "font_inc": "Ctrl+Alt+=",
    "font_dec": "Ctrl+Alt+-",
    "zoom_in": "Ctrl+=",
    "zoom_out": "Ctrl+-",
    "zoom_fit": "Ctrl+0",
    "zoom_actual": "Ctrl+1",
    "zoom_wheel": "Ctrl+Wheel",
    "process_all": "Ctrl+Return",
    "cancel": "Esc",
    "queue": "Ctrl+B",
    "history": "Ctrl+H",
    "settings": "Ctrl+,",
    "theme": "Ctrl+Shift+T",
    "shortcuts": "Ctrl+/",
    "shortcuts_alt": "F1",
}


def groups() -> list[tuple[str, list[tuple[str, list[str]]]]]:
    """Cheat-sheet content: (group title, [(description, [key sequences])])."""
    k = KEYS
    return [
        (S.sc_group_files, [
            (S.sc_open, [k["open"]]),
            (S.sc_open_folder, [k["open_folder"]]),
            (S.sc_paste, [k["paste"]]),
            (S.sc_save, [k["save"]]),
            (S.sc_process_all, [k["process_all"]]),
            (S.sc_cancel, [k["cancel"]]),
        ]),
        (S.sc_group_text, [
            (S.sc_copy_all, [k["copy_all"]]),
            (S.sc_copy_sel, [k["copy_sel"]]),
            (S.sc_find, [k["find"]]),
            (S.sc_next_unc, [k["next_unc"]]),
            (S.sc_prev_unc, [k["prev_unc"]]),
            (S.sc_font_inc, [k["font_inc"]]),
            (S.sc_font_dec, [k["font_dec"]]),
        ]),
        (S.sc_group_view, [
            (S.sc_zoom_in, [k["zoom_in"]]),
            (S.sc_zoom_out, [k["zoom_out"]]),
            (S.sc_zoom_fit, [k["zoom_fit"]]),
            (S.sc_zoom_actual, [k["zoom_actual"]]),
            (S.sc_zoom_wheel, [k["zoom_wheel"]]),
        ]),
        (S.sc_group_app, [
            (S.sc_queue, [k["queue"]]),
            (S.sc_history, [k["history"]]),
            (S.sc_settings, [k["settings"]]),
            (S.sc_theme, [k["theme"]]),
            (S.sc_shortcuts, [k["shortcuts"], k["shortcuts_alt"]]),
        ]),
    ]
