"""In-memory placeholder services. The services branch replaces these."""

from __future__ import annotations

import dataclasses
import os
from typing import Literal, Optional

from matnyab.api import AppSettings, ExportFormat, HistoryItem


class _MemorySettingsStore:
    def __init__(self) -> None:
        self._settings = AppSettings()

    def load(self) -> AppSettings:
        return dataclasses.replace(self._settings)

    def save(self, settings: AppSettings) -> None:
        self._settings = dataclasses.replace(settings)


class _MemoryHistoryStore:
    def __init__(self) -> None:
        self._items: list[HistoryItem] = []

    def add(self, item: HistoryItem) -> None:
        self._items.insert(0, item)

    def list(self) -> list[HistoryItem]:
        return list(self._items)

    def delete(self, item_id: str) -> None:
        self._items = [i for i in self._items if i.id != item_id]

    def clear(self) -> None:
        self._items = []


def create_settings_store(path: Optional[str | os.PathLike[str]] = None) -> _MemorySettingsStore:
    return _MemorySettingsStore()


def create_history_store(path: Optional[str | os.PathLike[str]] = None) -> _MemoryHistoryStore:
    return _MemoryHistoryStore()


def export_text(text: str, path: str | os.PathLike[str], fmt: ExportFormat) -> None:
    if fmt == "txt":
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    elif fmt == "docx":
        raise NotImplementedError("docx export is not implemented yet")
    else:
        raise ValueError(f"unknown export format: {fmt!r}")


def convert_digits(text: str, style: Literal["keep", "fa", "en"]) -> str:
    return text


def normalize_text(text: str) -> str:
    return text
