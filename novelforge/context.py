from __future__ import annotations

import json
from typing import Any

from .project import NovelProject


class ContextBuilder:
    def __init__(self, project: NovelProject):
        self.project = project

    def build(self, user_direction: str, chapter_number: int) -> dict[str, Any]:
        cfg = self.project.config.get("generation", {})
        recent_n = int(cfg.get("recent_chapters", 3))
        retrieval_limit = int(cfg.get("retrieval_limit", 12))
        recent = list(reversed(self.project.chapters(limit=recent_n)))
        arcs = self.project.db.query("SELECT * FROM arcs WHERE status IN ('planned','active') ORDER BY position")
        threads = self.project.db.query("SELECT * FROM threads WHERE status='open' ORDER BY importance DESC,id")
        facts = self.project.db.query("SELECT * FROM facts WHERE canon_status='established' ORDER BY id DESC LIMIT 80")
        entities = self.project.db.query("SELECT type,name,summary,static_json,dynamic_json,status FROM entities WHERE status='active' ORDER BY type,name")
        retrieved = self.project.search(user_direction, retrieval_limit) if user_direction.strip() else []
        return {
            "chapter_number": chapter_number,
            "foundation": self.project.foundation,
            "active_arcs": arcs,
            "open_threads": threads,
            "canon_facts": facts,
            "entities": entities,
            "recent_chapters": [
                {"number": c["number"], "title": c["title"], "summary": c["summary"], "pov": c["pov"]}
                for c in recent
            ],
            "retrieved_memory": retrieved,
            "user_direction": user_direction,
        }

    @staticmethod
    def compact(context: dict[str, Any]) -> str:
        return json.dumps(context, ensure_ascii=False, indent=2)
