from __future__ import annotations

from app.config import get_settings
from app.llm.base import LLMProvider
from app.llm.openai_compat import OpenAICompatibleProvider


def get_llm_provider() -> LLMProvider | None:
    settings = get_settings()
    if not settings.llm_configured:
        return None
    provider = settings.llm_provider.lower()
    if provider == "groq":
        return OpenAICompatibleProvider(
            api_key=settings.groq_api_key,
            base_url=settings.groq_api_base,
            default_model=settings.llm_model or "llama-3.3-70b-versatile",
            name="groq",
        )
    return OpenAICompatibleProvider(
        api_key=settings.openai_api_key,
        base_url=settings.openai_api_base,
        default_model=settings.llm_model,
        name="openai" if provider == "openai" else "local",
    )
