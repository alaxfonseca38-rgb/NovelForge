from __future__ import annotations

import os
from typing import Protocol


class LLM(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class OpenAILLM:
    def __init__(self, model: str = "gpt-5.6-sol", api_key: str | None = None):
        env_name = "OPENAI" + "_API" + "_KEY"
        key = api_key or os.getenv(env_name)
        if not key:
            raise RuntimeError("A chave da API da OpenAI não está configurada.")
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError("O SDK da OpenAI não está instalado.") from exc
        self.model = model
        self.client = OpenAI(api_key=key)

    def complete(self, system: str, user: str) -> str:
        response = self.client.responses.create(model=self.model, instructions=system, input=user)
        return response.output_text
