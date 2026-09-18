from __future__ import annotations

from typing import Any

from app.agents.prompts import (
    ANALYST_SYSTEM,
    AUDITOR_SYSTEM,
    DASHBOARD_SYSTEM,
    ORCHESTRATOR_SYSTEM,
    PROFILER_SYSTEM,
    QUALITY_SYSTEM,
    SEMANTIC_SYSTEM,
)
from app.llm.factory import get_llm_provider


def llm_interpret(system: str, payload: dict[str, Any], schema_hint: str | None = None) -> dict[str, Any] | None:
    provider = get_llm_provider()
    if provider is None:
        return None
    from app.config import get_settings

    settings = get_settings()
    response = provider.complete_json(
        system=system,
        user=_compact(payload),
        schema_hint=schema_hint,
        temperature=settings.llm_temperature,
        model=settings.llm_model,
    )
    parsed = response.parsed if isinstance(response.parsed, dict) else None
    if parsed is None:
        return None
    parsed["_llm"] = {
        "provider": response.provider,
        "model": response.model,
        "prompt_tokens": response.prompt_tokens,
        "completion_tokens": response.completion_tokens,
    }
    return parsed


def interpret_orchestrator(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(ORCHESTRATOR_SYSTEM, payload)


def interpret_profiler(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(PROFILER_SYSTEM, payload)


def interpret_quality(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(QUALITY_SYSTEM, payload)


def interpret_semantic(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(SEMANTIC_SYSTEM, payload, schema_hint="{dimensions,measures,kpis}")


def interpret_analyst(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(ANALYST_SYSTEM, payload, schema_hint="{executive_summary,insights}")


def interpret_dashboard(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(DASHBOARD_SYSTEM, payload, schema_hint="{title,widgets}")


def interpret_auditor(payload: dict[str, Any]) -> dict[str, Any] | None:
    return llm_interpret(AUDITOR_SYSTEM, payload, schema_hint="{status,findings,caveats}")


def _compact(payload: dict[str, Any], limit: int = 18000) -> str:
    import json

    text = json.dumps(payload, default=str)
    if len(text) > limit:
        return text[:limit] + "...[truncated for LLM safety]"
    return text
