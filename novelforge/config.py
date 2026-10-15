from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG = {
    "llm": {
        "provider": "openai",
        "model": "gpt-5.6-sol",
    },
    "generation": {
        "target_words": 2500,
        "recent_chapters": 3,
        "retrieval_limit": 12,
        "auto_revision": True,
        "auto_canon_commit": True,
    },
}


def load_env(project_dir: Path | None = None) -> None:
    load_dotenv()
    if project_dir:
        load_dotenv(project_dir / ".env", override=True)


def read_config(project_dir: Path) -> dict[str, Any]:
    cfg = DEFAULT_CONFIG.copy()
    path = project_dir / "config.yaml"
    if path.exists():
        custom = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        cfg = _deep_merge(DEFAULT_CONFIG, custom)
    env_model = os.getenv("OPENAI_MODEL")
    if env_model:
        cfg.setdefault("llm", {})["model"] = env_model
    return cfg


def write_config(project_dir: Path, config: dict[str, Any]) -> None:
    path = project_dir / "config.yaml"
    path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")


def write_default_config(project_dir: Path) -> None:
    path = project_dir / "config.yaml"
    if not path.exists():
        path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False, allow_unicode=True), encoding="utf-8")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in base.items():
        out[key] = value.copy() if isinstance(value, dict) else value
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
