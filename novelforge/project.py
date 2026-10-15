from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import load_env, read_config, write_default_config
from .db import Database, now_iso
from .models import StoryFoundation


class NovelProject:
    def __init__(self, root: str | Path):
        self.root = Path(root).expanduser().resolve()
        self.db = Database(self.root / "novelforge.db")
        load_env(self.root)
        self.config = read_config(self.root)

    @classmethod
    def create(cls, root: str | Path, foundation: StoryFoundation) -> "NovelProject":
        root_path = Path(root).expanduser().resolve()
        root_path.mkdir(parents=True, exist_ok=True)
        (root_path / "exports").mkdir(exist_ok=True)
        write_default_config(root_path)
        project = cls(root_path)
        project.db.set_meta("foundation", foundation.to_dict())
        project.db.set_meta("project_version", "0.1.0")
        project.db.set_meta("title", foundation.title)
        project._index("foundation", "foundation", foundation.title, json.dumps(foundation.to_dict(), ensure_ascii=False))
        return project

    @property
    def foundation(self) -> dict[str, Any]:
        return self.db.get_meta("foundation", {})

    def update_foundation(self, data: dict[str, Any]) -> None:
        current = self.foundation
        current.update(data)
        self.db.set_meta("foundation", current)
        self._index("foundation", "foundation", current.get("title", "Story Foundation"), json.dumps(current, ensure_ascii=False))

    def add_entity(self, entity_type: str, name: str, summary: str = "", static: dict[str, Any] | None = None, dynamic: dict[str, Any] | None = None) -> int:
        stamp = now_iso()
        static_s = json.dumps(static or {}, ensure_ascii=False)
        dynamic_s = json.dumps(dynamic or {}, ensure_ascii=False)
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO entities(type,name,summary,static_json,dynamic_json,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?)
                ON CONFLICT(type,name) DO UPDATE SET summary=excluded.summary, static_json=excluded.static_json,
                dynamic_json=excluded.dynamic_json, updated_at=excluded.updated_at""",
                (entity_type, name, summary, static_s, dynamic_s, stamp, stamp),
            )
            row = con.execute("SELECT id FROM entities WHERE type=? AND name=?", (entity_type, name)).fetchone()
            entity_id = int(row["id"])
        self._index("entity", f"{entity_type}:{name}", f"{entity_type}: {name}", f"{summary}\n{static_s}\n{dynamic_s}")
        return entity_id

    def list_entities(self, entity_type: str | None = None) -> list[dict[str, Any]]:
        if entity_type:
            return self.db.query("SELECT * FROM entities WHERE type=? ORDER BY name", (entity_type,))
        return self.db.query("SELECT * FROM entities ORDER BY type,name")

    def add_arc(self, title: str, summary: str = "", goal: str = "", stakes: str = "", status: str = "planned", notes: str = "") -> int:
        pos = self.db.query("SELECT COALESCE(MAX(position),0)+1 AS p FROM arcs")[0]["p"]
        arc_id = self.db.execute(
            "INSERT INTO arcs(title,status,position,summary,goal,stakes,notes) VALUES(?,?,?,?,?,?,?)",
            (title, status, pos, summary, goal, stakes, notes),
        )
        self._index("arc", str(arc_id), title, f"{summary}\nGoal: {goal}\nStakes: {stakes}\n{notes}")
        return arc_id

    def add_thread(self, title: str, description: str = "", importance: int = 5, opened_chapter: int | None = None, target_payoff: str = "") -> int:
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO threads(title,description,importance,opened_chapter,last_mentioned_chapter,target_payoff)
                VALUES(?,?,?,?,?,?) ON CONFLICT(title) DO UPDATE SET description=excluded.description,
                importance=excluded.importance,target_payoff=excluded.target_payoff""",
                (title, description, importance, opened_chapter, opened_chapter, target_payoff),
            )
            row = con.execute("SELECT id FROM threads WHERE title=?", (title,)).fetchone()
            thread_id = int(row["id"])
        self._index("thread", str(thread_id), title, f"{description}\nPayoff: {target_payoff}")
        return thread_id

    def add_fact(self, subject_type: str, subject_name: str, predicate: str, value: str, source_chapter: int | None = None, confidence: float = 1.0, canon_status: str = "established") -> int:
        fact_id = self.db.execute(
            """INSERT INTO facts(subject_type,subject_name,predicate,value,source_chapter,confidence,canon_status,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (subject_type, subject_name, predicate, value, source_chapter, confidence, canon_status, now_iso()),
        )
        if canon_status == "established":
            self._index("fact", str(fact_id), f"{subject_name} — {predicate}", value)
        return fact_id

    def list_facts(self, canon_only: bool = True) -> list[dict[str, Any]]:
        if canon_only:
            return self.db.query("SELECT * FROM facts WHERE canon_status='established' ORDER BY id DESC")
        return self.db.query("SELECT * FROM facts ORDER BY id DESC")

    def add_timeline_event(self, chapter_number: int, event: str, *, event_order: int = 0, story_time: str = "", location: str = "", participants: list[str] | None = None, consequence: str = "") -> int:
        return self.db.execute(
            """INSERT INTO timeline(chapter_number,event_order,story_time,location,participants_json,event,consequence)
            VALUES(?,?,?,?,?,?,?)""",
            (chapter_number, event_order, story_time, location, json.dumps(participants or [], ensure_ascii=False), event, consequence),
        )

    def save_plan(self, chapter_number: int, kind: str, content: dict[str, Any]) -> int:
        return self.db.execute(
            "INSERT INTO plans(chapter_number,kind,content_json,created_at) VALUES(?,?,?,?)",
            (chapter_number, kind, json.dumps(content, ensure_ascii=False), now_iso()),
        )

    def commit_chapter(self, number: int, title: str, content: str, summary: str, pov: str = "") -> int:
        stamp = now_iso()
        wc = len(content.split())
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO chapters(number,title,pov,summary,content,word_count,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(number) DO UPDATE SET title=excluded.title,pov=excluded.pov,summary=excluded.summary,
                content=excluded.content,word_count=excluded.word_count,updated_at=excluded.updated_at""",
                (number, title, pov, summary, content, wc, stamp, stamp),
            )
            row = con.execute("SELECT id FROM chapters WHERE number=?", (number,)).fetchone()
            chapter_id = int(row["id"])
        self._index("chapter", str(number), f"Chapter {number}: {title}", f"{summary}\n\n{content}")
        self._write_chapter_markdown(number, title, content)
        return chapter_id

    def next_chapter_number(self) -> int:
        rows = self.db.query("SELECT COALESCE(MAX(number),0)+1 AS n FROM chapters")
        return int(rows[0]["n"])

    def chapters(self, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM chapters ORDER BY number DESC"
        params: tuple[Any, ...] = ()
        if limit:
            sql += " LIMIT ?"
            params = (limit,)
        return self.db.query(sql, params)

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        try:
            rows = self.db.query(
                """SELECT d.kind,d.ref_key,d.title,d.body,bm25(memory_fts) AS score
                FROM memory_fts JOIN memory_docs d ON d.id=memory_fts.rowid
                WHERE memory_fts MATCH ? ORDER BY score LIMIT ?""",
                (query, limit),
            )
            return rows
        except Exception:
            pattern = f"%{query}%"
            return self.db.query(
                "SELECT kind,ref_key,title,body,0 AS score FROM memory_docs WHERE title LIKE ? OR body LIKE ? LIMIT ?",
                (pattern, pattern, limit),
            )

    def export_markdown(self) -> Path:
        chapters = list(reversed(self.chapters()))
        title = self.foundation.get("title", "Novel")
        out = self.root / "exports" / "manuscript.md"
        parts = [f"# {title}\n"]
        for ch in chapters:
            parts.append(f"\n## Chapter {ch['number']}: {ch['title']}\n\n{ch['content']}\n")
        out.write_text("\n".join(parts), encoding="utf-8")
        return out

    def _index(self, kind: str, ref_key: str, title: str, body: str) -> None:
        with self.db.connect() as con:
            con.execute(
                """INSERT INTO memory_docs(kind,ref_key,title,body,updated_at) VALUES(?,?,?,?,?)
                ON CONFLICT(kind,ref_key) DO UPDATE SET title=excluded.title,body=excluded.body,updated_at=excluded.updated_at""",
                (kind, ref_key, title, body, now_iso()),
            )

    def _write_chapter_markdown(self, number: int, title: str, content: str) -> None:
        folder = self.root / "chapters"
        folder.mkdir(exist_ok=True)
        (folder / f"chapter_{number:04d}.md").write_text(f"# Chapter {number}: {title}\n\n{content}\n", encoding="utf-8")
