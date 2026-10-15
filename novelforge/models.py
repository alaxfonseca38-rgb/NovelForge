from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class StoryFoundation:
    title: str
    premise: str = ""
    genre: str = ""
    tone: str = ""
    pov: str = "third-person limited"
    protagonist: str = ""
    setting: str = ""
    themes: list[str] = field(default_factory=list)
    hard_rules: list[str] = field(default_factory=list)
    style_rules: list[str] = field(default_factory=list)
    forbidden: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "premise": self.premise,
            "genre": self.genre,
            "tone": self.tone,
            "pov": self.pov,
            "protagonist": self.protagonist,
            "setting": self.setting,
            "themes": self.themes,
            "hard_rules": self.hard_rules,
            "style_rules": self.style_rules,
            "forbidden": self.forbidden,
        }


@dataclass(slots=True)
class GenerationResult:
    chapter_number: int
    title: str
    content: str
    summary: str
    director: dict[str, Any]
    plan: dict[str, Any]
    critique: dict[str, Any]
    continuity: dict[str, Any]
    canon: dict[str, Any]
