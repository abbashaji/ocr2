"""Frozen-friendly GUI launcher: delegates to matnyab.ui.app.main."""

from __future__ import annotations

from matnyab.ui.app import main as _ui_main


def main() -> int:
    return _ui_main()


if __name__ == "__main__":
    raise SystemExit(main())
