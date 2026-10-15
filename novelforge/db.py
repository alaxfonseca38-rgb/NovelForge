from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCHEMA = """
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS metadata (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  type TEXT NOT NULL,
  name TEXT NOT NULL,
  summary TEXT DEFAULT '',
  static_json TEXT NOT NULL DEFAULT '{}',
  dynamic_json TEXT NOT NULL DEFAULT '{}',
  status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(type, name)
);

CREATE TABLE IF NOT EXISTS facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_type TEXT NOT NULL,
  subject_name TEXT NOT NULL,
  predicate TEXT NOT NULL,
  value TEXT NOT NULL,
  source_chapter INTEGER,
  confidence REAL NOT NULL DEFAULT 1.0,
  canon_status TEXT NOT NULL DEFAULT 'established',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS arcs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL DEFAULT 'planned',
  position INTEGER NOT NULL DEFAULT 0,
  summary TEXT DEFAULT '',
  goal TEXT DEFAULT '',
  stakes TEXT DEFAULT '',
  start_chapter INTEGER,
  end_chapter INTEGER,
  notes TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS threads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL UNIQUE,
  description TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open',
  importance INTEGER NOT NULL DEFAULT 5,
  opened_chapter INTEGER,
  last_mentioned_chapter INTEGER,
  target_payoff TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chapters (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  number INTEGER NOT NULL UNIQUE,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'final',
  pov TEXT DEFAULT '',
  summary TEXT DEFAULT '',
  content TEXT NOT NULL,
  word_count INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS timeline (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter_number INTEGER NOT NULL,
  event_order INTEGER NOT NULL DEFAULT 0,
  story_time TEXT DEFAULT '',
  location TEXT DEFAULT '',
  participants_json TEXT NOT NULL DEFAULT '[]',
  event TEXT NOT NULL,
  consequence TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS plans (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  chapter_number INTEGER NOT NULL,
  kind TEXT NOT NULL,
  content_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS memory_docs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  kind TEXT NOT NULL,
  ref_key TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(kind, ref_key)
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
  title,
  body,
  content='memory_docs',
  content_rowid='id'
);

CREATE TRIGGER IF NOT EXISTS memory_ai AFTER INSERT ON memory_docs BEGIN
  INSERT INTO memory_fts(rowid,title,body) VALUES (new.id,new.title,new.body);
END;
CREATE TRIGGER IF NOT EXISTS memory_ad AFTER DELETE ON memory_docs BEGIN
  INSERT INTO memory_fts(memory_fts,rowid,title,body) VALUES('delete',old.id,old.title,old.body);
END;
CREATE TRIGGER IF NOT EXISTS memory_au AFTER UPDATE ON memory_docs BEGIN
  INSERT INTO memory_fts(memory_fts,rowid,title,body) VALUES('delete',old.id,old.title,old.body);
  INSERT INTO memory_fts(rowid,title,body) VALUES (new.id,new.title,new.body);
END;
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(SCHEMA)

    def set_meta(self, key: str, value: Any) -> None:
        payload = json.dumps(value, ensure_ascii=False)
        with self.connect() as con:
            con.execute(
                "INSERT INTO metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, payload),
            )

    def get_meta(self, key: str, default: Any = None) -> Any:
        with self.connect() as con:
            row = con.execute("SELECT value FROM metadata WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        with self.connect() as con:
            rows = con.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        with self.connect() as con:
            cur = con.execute(sql, params)
            return int(cur.lastrowid or 0)
