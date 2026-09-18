from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from app.agents.state import PipelineState
from app.config import get_settings


def agent_graph(handlers: dict[str, Callable[[PipelineState], PipelineState]]):
    """Explicit multi-agent state graph with retry limits and no infinite loops."""
    settings = get_settings()
    max_retries = settings.pipeline_max_retries

    graph = StateGraph(PipelineState)
    for name, handler in handlers.items():
        graph.add_node(name, handler)

    graph.add_edge(START, "orchestrator")
    graph.add_edge("orchestrator", "profiler")
    graph.add_edge("profiler", "quality")
    graph.add_conditional_edges("quality", lambda s: _quality_route(s, max_retries), {"profiler": "profiler", "semantic": "semantic", "auditor": "auditor"})
    graph.add_conditional_edges("semantic", lambda s: _semantic_route(s, max_retries), {"semantic": "semantic", "analyst": "analyst", "auditor": "auditor"})
    graph.add_edge("analyst", "dashboard")
    graph.add_edge("dashboard", "auditor")
    graph.add_conditional_edges("auditor", lambda s: _auditor_route(s, max_retries), {"quality": "quality", "semantic": "semantic", "publish": "publish", END: END})
    graph.add_edge("publish", END)
    return graph.compile()


def _retry(state: PipelineState, key: str, max_retries: int) -> bool:
    retries = dict(state.get("retry") or {})
    count = int(retries.get(key, 0))
    if count >= max_retries:
        return False
    retries[key] = count + 1
    state["retry"] = retries
    return True


def _quality_route(state: PipelineState, max_retries: int) -> str:
    report = state.get("quality_report") or {}
    score = report.get("overall_score")
    if score is not None and score < 30 and _retry(state, "quality", max_retries):
        return "profiler"
    if state.get("errors"):
        return "auditor"
    return "semantic"


def _semantic_route(state: PipelineState, max_retries: int) -> str:
    kpis = state.get("kpis") or []
    if not kpis and _retry(state, "semantic", max_retries):
        return "semantic"
    if not kpis:
        return "auditor"
    return "analyst"


def _auditor_route(state: PipelineState, max_retries: int) -> str:
    audit = state.get("audit") or {}
    status = audit.get("status")
    if status == "retry_quality" and _retry(state, "audit_quality", max_retries):
        return "quality"
    if status == "retry_semantic" and _retry(state, "audit_semantic", max_retries):
        return "semantic"
    if status == "VALID":
        return "publish"
    return END
