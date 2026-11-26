"""Warstwa SQLite biblioteki PhotoSort.

Każdy wątek otwiera własne połączenie (klasa Database jest lekka). Baza działa
w trybie WAL, dzięki czemu wątki tła (import, metadane) mogą pisać, a interfejs
w tym czasie czytać.
"""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS media (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    rel_path      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    folder        TEXT NOT NULL COLLATE NOCASE,
    filename      TEXT NOT NULL,
    kind          TEXT NOT NULL,
    ext           TEXT,
    size          INTEGER,
    file_created  REAL,
    file_modified REAL,
    imported_at   REAL,
    source_path   TEXT,
    hash          TEXT,
    taken_at      TEXT,
    taken_source  TEXT,
    sort_date     TEXT,
    width         INTEGER,
    height        INTEGER,
    duration      REAL,
    fps           REAL,
    make          TEXT,
    model         TEXT,
    lat           REAL,
    lon           REAL,
    place         TEXT,
    orientation   INTEGER,
    meta_status   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_media_folder ON media(folder);
CREATE INDEX IF NOT EXISTS ix_media_sort ON media(sort_date);
CREATE INDEX IF NOT EXISTS ix_media_hash ON media(hash);
CREATE INDEX IF NOT EXISTS ix_media_size ON media(size);
CREATE INDEX IF NOT EXISTS ix_media_meta ON media(meta_status);

-- Dziennik przeniesień: zapis "pending" przed fizycznym przeniesieniem pozwala
-- dokończyć lub wycofać operację po awarii/przerwaniu programu.
CREATE TABLE IF NOT EXISTS moves (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    batch     INTEGER NOT NULL,
    media_id  INTEGER NOT NULL,
    src_rel   TEXT NOT NULL,
    dst_rel   TEXT NOT NULL,
    ts        REAL NOT NULL,
    state     TEXT NOT NULL      -- pending | done | undone | failed
);
CREATE INDEX IF NOT EXISTS ix_moves_batch ON moves(batch);

CREATE TABLE IF NOT EXISTS bookmarks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    media_id  INTEGER NOT NULL UNIQUE REFERENCES media(id) ON DELETE CASCADE,
    label     TEXT,
    created   REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS state (
    key   TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS imports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    started    REAL NOT NULL,
    finished   REAL,
    source     TEXT,
    copied     INTEGER DEFAULT 0,
    duplicates INTEGER DEFAULT 0,
    errors     INTEGER DEFAULT 0
);

-- Zapamiętane źródła importu: pozwala pominąć pliki już zaimportowane
-- bez ponownego kopiowania (np. drugi import z tego samego telefonu).
CREATE TABLE IF NOT EXISTS import_sources (
    source_key TEXT PRIMARY KEY,
    hash       TEXT,
    ts         REAL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None,
                                    check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=30000")

    # -- schemat ---------------------------------------------------------
    def init_schema(self) -> None:
        with self._lock:
            self.conn.executescript(SCHEMA)
            self.conn.execute("INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
                              (str(SCHEMA_VERSION),))

    # -- podstawowe operacje ---------------------------------------------
    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, tuple(params))

    def executemany(self, sql: str, seq: Iterable[Iterable[Any]]) -> None:
        with self._lock:
            self.conn.executemany(sql, seq)

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, tuple(params)).fetchone()

    def scalar(self, sql: str, params: Iterable[Any] = ()) -> Any:
        row = self.query_one(sql, params)
        return row[0] if row else None

    def transaction(self) -> "_Tx":
        return _Tx(self)

    # -- stan sesji ---------------------------------------------------------
    def get_state(self, key: str, default: str | None = None) -> str | None:
        row = self.query_one("SELECT value FROM state WHERE key=?", (key,))
        return row[0] if row else default

    def set_state(self, key: str, value: str | None) -> None:
        self.execute("INSERT INTO state(key, value) VALUES(?, ?) "
                     "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass


class _Tx:
    def __init__(self, db: Database):
        self.db = db

    def __enter__(self) -> Database:
        self.db._lock.acquire()
        self.db.conn.execute("BEGIN IMMEDIATE")
        return self.db

    def __exit__(self, exc_type, exc, tb) -> None:
        try:
            if exc_type is None:
                self.db.conn.execute("COMMIT")
            else:
                self.db.conn.execute("ROLLBACK")
        finally:
            self.db._lock.release()
