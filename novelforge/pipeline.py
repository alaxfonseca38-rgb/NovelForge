from __future__ import annotations

import json
from typing import Any

from .context import ContextBuilder
from .jsonutil import parse_json
from .llm import LLM
from .models import GenerationResult
from .project import NovelProject
from . import prompts


class ChapterPipeline:
    def __init__(self, project: NovelProject, llm: LLM):
        self.project = project
        self.llm = llm
        self.context_builder = ContextBuilder(project)

    def generate(self, user_direction: str = "", chapter_number: int | None = None) -> GenerationResult:
        number = chapter_number or self.project.next_chapter_number()
        context = self.context_builder.build(user_direction, number)
        packed = self.context_builder.compact(context)

        director = self._json(prompts.DIRECTOR_SYSTEM, f"STORY STATE:\n{packed}\n\nUSER DIRECTION:\n{user_direction}")
        self.project.save_plan(number, "director", director)

        plan = self._json(
            prompts.PLANNER_SYSTEM,
            f"STORY STATE:\n{packed}\n\nDIRECTOR:\n{json.dumps(director, ensure_ascii=False, indent=2)}",
        )
        self.project.save_plan(number, "chapter_plan", plan)

        target_words = int(self.project.config.get("generation", {}).get("target_words", 2500))
        prose = self.llm.complete(
            prompts.WRITER_SYSTEM,
            f"TARGET LENGTH: about {target_words} words.\n\nSTORY STATE:\n{packed}\n\nDIRECTOR:\n{json.dumps(director, ensure_ascii=False)}\n\nCHAPTER PLAN:\n{json.dumps(plan, ensure_ascii=False, indent=2)}",
        ).strip()

        critique = self._json(
            prompts.CRITIC_SYSTEM,
            f"FOUNDATION/STATE:\n{packed}\n\nPLAN:\n{json.dumps(plan, ensure_ascii=False)}\n\nCHAPTER:\n{prose}",
        )
        continuity = self._json(
            prompts.CONTINUITY_SYSTEM,
            f"ESTABLISHED STORY STATE:\n{packed}\n\nCHAPTER:\n{prose}",
        )
        self.project.save_plan(number, "critique", critique)
        self.project.save_plan(number, "continuity", continuity)

        auto_revision = bool(self.project.config.get("generation", {}).get("auto_revision", True))
        if auto_revision and (critique.get("needs_revision") or continuity.get("verdict") == "revise"):
            prose = self.llm.complete(
                prompts.REVISION_SYSTEM,
                f"STORY STATE:\n{packed}\n\nPLAN:\n{json.dumps(plan, ensure_ascii=False)}\n\nEDITOR:\n{json.dumps(critique, ensure_ascii=False)}\n\nCONTINUITY:\n{json.dumps(continuity, ensure_ascii=False)}\n\nDRAFT:\n{prose}",
            ).strip()
            continuity = self._json(
                prompts.CONTINUITY_SYSTEM,
                f"ESTABLISHED STORY STATE:\n{packed}\n\nREVISED CHAPTER:\n{prose}",
            )
            self.project.save_plan(number, "continuity", continuity)

        extracted = self._json(prompts.EXTRACTOR_SYSTEM, f"FINAL CHAPTER:\n{prose}")
        canon = self._json(
            prompts.CURATOR_SYSTEM,
            f"EXISTING CANON:\n{json.dumps(context.get('canon_facts', []), ensure_ascii=False)}\n\nFINAL CHAPTER:\n{prose}\n\nPROPOSALS:\n{json.dumps(extracted.get('canon_proposals', []), ensure_ascii=False)}",
        )
        self.project.save_plan(number, "state_extraction", extracted)
        self.project.save_plan(number, "canon_curator", canon)

        title = str(plan.get("chapter_title") or f"Chapter {number}")
        pov = str(plan.get("pov") or context.get("foundation", {}).get("protagonist", ""))
        summary = str(extracted.get("summary") or director.get("chapter_objective") or "")
        self.project.commit_chapter(number, title, prose, summary, pov)
        self._commit_state(number, extracted, canon)

        return GenerationResult(
            chapter_number=number,
            title=title,
            content=prose,
            summary=summary,
            director=director,
            plan=plan,
            critique=critique,
            continuity=continuity,
            canon=canon,
        )

    def _commit_state(self, chapter_number: int, extracted: dict[str, Any], canon: dict[str, Any]) -> None:
        auto_commit = bool(self.project.config.get("generation", {}).get("auto_canon_commit", True))
        accepted = canon.get("accepted_facts", []) if auto_commit else []
        proposed = extracted.get("canon_proposals", [])
        accepted_keys = {
            (str(f.get("subject_type")), str(f.get("subject_name")), str(f.get("predicate")), str(f.get("value")))
            for f in accepted if isinstance(f, dict)
        }
        for f in proposed:
            if not isinstance(f, dict):
                continue
            key = (str(f.get("subject_type")), str(f.get("subject_name")), str(f.get("predicate")), str(f.get("value")))
            status = "established" if key in accepted_keys else "proposed"
            self.project.add_fact(
                key[0], key[1], key[2], key[3], chapter_number,
                float(f.get("confidence", 0.8) or 0.8), status,
            )

        for ev in extracted.get("timeline", []):
            if not isinstance(ev, dict) or not ev.get("event"):
                continue
            self.project.add_timeline_event(
                chapter_number,
                str(ev.get("event")),
                event_order=int(ev.get("event_order", 0) or 0),
                story_time=str(ev.get("story_time", "")),
                location=str(ev.get("location", "")),
                participants=[str(x) for x in ev.get("participants", [])],
                consequence=str(ev.get("consequence", "")),
            )

        for upd in extracted.get("entity_updates", []):
            if isinstance(upd, dict) and upd.get("type") and upd.get("name"):
                self.project.add_entity(
                    str(upd["type"]), str(upd["name"]), str(upd.get("summary", "")), dynamic=upd.get("dynamic") or {}
                )

        for t in extracted.get("thread_updates", []):
            if not isinstance(t, dict) or not t.get("title"):
                continue
            action = t.get("action", "mention")
            title = str(t["title"])
            if action == "open":
                self.project.add_thread(
                    title,
                    str(t.get("description", "")),
                    int(t.get("importance", 5) or 5),
                    chapter_number,
                    str(t.get("target_payoff", "")),
                )
            elif action == "close":
                self.project.db.execute("UPDATE threads SET status='closed',last_mentioned_chapter=? WHERE title=?", (chapter_number, title))
            else:
                self.project.db.execute("UPDATE threads SET last_mentioned_chapter=? WHERE title=?", (chapter_number, title))

    def _json(self, system: str, user: str) -> dict[str, Any]:
        raw = self.llm.complete(system, user)
        parsed = parse_json(raw, {})
        return parsed if isinstance(parsed, dict) else {}
