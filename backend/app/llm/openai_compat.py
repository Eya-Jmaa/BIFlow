from __future__ import annotations

import json
import re
from typing import Any

import httpx

from app.llm.base import LLMProvider, LLMResponse


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, default_model: str, name: str = "openai") -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.name = name

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_hint: str | None = None,
        temperature: float = 0.1,
        model: str | None = None,
    ) -> LLMResponse:
        payload = {
            "model": model or self.default_model,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system + ("\nReturn valid JSON only." if schema_hint is None else f"\nReturn JSON matching: {schema_hint}")},
                {"role": "user", "content": user},
            ],
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=90.0) as client:
            response = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            body = response.json()
        choice = body["choices"][0]["message"]["content"]
        usage = body.get("usage") or {}
        parsed = _parse_json(choice)
        return LLMResponse(
            content=choice,
            parsed=parsed,
            model=payload["model"],
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            provider=self.name,
        )


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))
