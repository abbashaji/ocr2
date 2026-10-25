"""SQLite history storage (new connection per call, rollback journal)."""

from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional

from matnyab import paths
from matnyab.api import HistoryItem

MAX_ITEMS = 200
MAX_TEXT_BYTES = 1_000_000  # 1 MB of UTF-8 text per item

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS history("
    "id TEXT PRIMARY KEY, source TEXT, created TEXT, text TEXT, "
    "mode_used TEXT, confidence REAL)"
)


def _truncate(text: str) -> str:
    """Cut ``text`` to MAX_TEXT_BYTES of UTF-8 at a character boundary, no marker."""
    if len(text) * 4 <= MAX_TEXT_BYTES:
        return text
    raw = text.encode("utf-8", "surrogatepass")
    if len(raw) <= MAX_TEXT_BYTES:
        return text
    return raw[:MAX_TEXT_BYTES].decode("utf-8", "ignore")


class SqliteHistoryStore:
    def __init__(self, path: Optional[str | os.PathLike[str]] = None) -> None:
        self._path = Path(path) if path is not None else None
        self._lock = threading.RLock()
        self._ready = False

    @property
    def path(self) -> Path:
        return self._path if self._path is not None else paths.data_dir() / "history.db"

    # -- connection handling -------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), timeout=30.0)
        conn.execute("PRAGMA journal_mode=DELETE")
        return conn

    def _open(self) -> sqlite3.Connection:
        """Open a connection with the schema in place; recover from corruption."""
        with self._lock:
            try:
                conn = self._connect()
                try:
                    conn.execute(_SCHEMA)
                    conn.commit()
                    if not self._ready:
                        conn.execute("SELECT COUNT(*) FROM history").fetchone()
                        self._ready = True
                    return conn
                except Exception:
                    conn.close()
                    raise
            except sqlite3.DatabaseError as exc:
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    raise
                self._quarantine()
                conn = self._connect()
                conn.execute(_SCHEMA)
                conn.commit()
                self._ready = True
                return conn

    def _quarantine(self) -> None:
        path = self.path
        bad = path.with_name(path.name + ".bad")
        try:
            os.replace(path, bad)
        except OSError:
            pass
        for suffix in ("-journal", "-wal", "-shm"):
            try:
                os.unlink(str(path) + suffix)
            except OSError:
                pass

    # -- API ---------------------------------------------------------------
    def add(self, item: HistoryItem) -> None:
        text = _truncate(item.text)
        with self._lock:
            conn = self._open()
            try:
                with conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO history(id, source, created, text, mode_used, confidence) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (item.id, item.source, item.created, text, item.mode_used, float(item.confidence)),
                    )
                    conn.execute(
                        "DELETE FROM history WHERE rowid NOT IN ("
                        "SELECT rowid FROM history ORDER BY created DESC, rowid DESC LIMIT ?)",
                        (MAX_ITEMS,),
                    )
            finally:
                conn.close()

    def list(self, limit: Optional[int] = None) -> list[HistoryItem]:
        sql = ("SELECT id, source, created, text, mode_used, confidence FROM history "
               "ORDER BY created DESC, rowid DESC")
        params: tuple = ()
        if limit is not None:
            if limit <= 0:
                return []
            sql += " LIMIT ?"
            params = (int(limit),)
        with self._lock:
            conn = self._open()
            try:
                rows = conn.execute(sql, params).fetchall()
            finally:
                conn.close()
        return [HistoryItem(r[0], r[1], r[2], r[3], r[4], float(r[5])) for r in rows]

    def delete(self, item_id: str) -> None:
        with self._lock:
            conn = self._open()
            try:
                with conn:
                    conn.execute("DELETE FROM history WHERE id = ?", (item_id,))
            finally:
                conn.close()

    def clear(self) -> None:
        with self._lock:
            conn = self._open()
            try:
                with conn:
                    conn.execute("DELETE FROM history")
            finally:
                conn.close()


def create_history_store(path: Optional[str | os.PathLike[str]] = None) -> SqliteHistoryStore:
    return SqliteHistoryStore(path)
