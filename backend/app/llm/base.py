from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LLMResponse(BaseModel):
    content: str
    parsed: Any | None = None
    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    provider: str


class LLMProvider:
    name: str

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: str | None = None,
        temperature: float = 0.1,
        model: str | None = None,
    ) -> LLMResponse:
        raise NotImplementedError
