"""The multi-agent control flow.

This is the orchestration the BI Orchestrator agent is responsible for: what
runs, in what order, what happens when an agent fails, and when the auditor is
allowed to send work back. The agents themselves live in
:mod:`app.pipeline.executor` and know nothing about routing.

Flow::

    START -> orchestrator -> profiler -> quality -> semantic -> analyst
          -> dashboard -> auditor -> publish -> END

The auditor's verdict adds two feedback edges, which is what makes this a
graph rather than a sequence:

* ``retry_semantic`` when too few KPIs computed -- the semantic agent re-runs
  without the LLM proposals the auditor just rejected.
* ``retry_quality`` when the data was too poor to publish -- quality re-runs
  from the raw tables, and everything downstream is recomputed.

Every back edge is bounded by ``pipeline_max_retries``. When a budget is
exhausted the run publishes with its caveats attached rather than looping or
throwing away the work, because a labelled partial result is more useful to an
analyst than no result at all.
"""

from __future__ import annotations

from typing import Callable

from langgraph.graph import END, START, StateGraph

from app.agents.state import PipelineState
from app.config import get_settings

# An agent that raised is not retried in place; the run continues to the
# auditor, which decides whether what survived is publishable.
FATAL_STEPS = {"orchestrator", "profiler"}


def agent_graph(handlers: dict[str, Callable[[PipelineState], PipelineState]]):
    """Compile the agent graph with bounded feedback edges."""
    settings = get_settings()
    max_retries = settings.pipeline_max_retries

    graph = StateGraph(PipelineState)
    for name, handler in handlers.items():
        graph.add_node(name, handler)

    graph.add_edge(START, "orchestrator")
    graph.add_conditional_edges(
        "orchestrator",
        lambda state: _halt_or(state, "profiler"),
        {"profiler": "profiler", "auditor": "auditor"},
    )
    graph.add_conditional_edges(
        "profiler",
        lambda state: _halt_or(state, "quality"),
        {"quality": "quality", "auditor": "auditor"},
    )
    graph.add_conditional_edges(
        "quality",
        lambda state: _quality_route(state, max_retries),
        {"semantic": "semantic", "auditor": "auditor"},
    )
    graph.add_conditional_edges(
        "semantic",
        lambda state: _semantic_route(state, max_retries),
        {"semantic": "semantic", "analyst": "analyst", "auditor": "auditor"},
    )
    graph.add_edge("analyst", "dashboard")
    graph.add_edge("dashboard", "auditor")
    graph.add_conditional_edges(
        "auditor",
        lambda state: _auditor_route(state, max_retries),
        {"quality": "quality", "semantic": "semantic", "publish": "publish"},
    )
    graph.add_edge("publish", END)
    return graph.compile()


def _spent(state: PipelineState, key: str, max_retries: int) -> bool:
    """Whether a named retry budget is used up.

    Routing functions only read the budget. It is incremented by the node that
    decides to retry, because LangGraph merges what a *node* returns -- state
    mutated inside a conditional edge is discarded, and a counter kept here
    would never advance, so the graph would loop until it hit the recursion
    limit.
    """
    return int((state.get("retry") or {}).get(key, 0)) >= max_retries


def _failed(state: PipelineState, step: str) -> bool:
    return any(error.startswith(f"{step}:") for error in (state.get("errors") or []))


def _halt_or(state: PipelineState, next_step: str) -> str:
    """Skip to the auditor when a step the rest of the run depends on failed."""
    previous = {"profiler": "orchestrator", "quality": "profiler"}.get(next_step)
    if previous and previous in FATAL_STEPS and _failed(state, previous):
        return "auditor"
    return next_step


def _quality_route(state: PipelineState, max_retries: int) -> str:
    if _failed(state, "quality"):
        return "auditor"
    return "semantic"


def _semantic_route(state: PipelineState, max_retries: int) -> str:
    if _failed(state, "semantic"):
        return "auditor"
    kpis = state.get("kpis") or []
    if not any(kpi.get("status") == "computed" for kpi in kpis):
        # Nothing to analyse. Retry while the budget the node consumed allows,
        # then let the auditor record why the run has no metrics.
        if not _spent(state, "semantic", max_retries):
            return "semantic"
        return "auditor"
    return "analyst"


def _auditor_route(state: PipelineState, max_retries: int) -> str:
    """The auditor has already applied the retry budget; this reads its verdict.

    A verdict of ``retry_*`` here is one the auditor decided it still had
    budget for, so it is always followed.
    """
    verdict = (state.get("audit") or {}).get("status")
    if verdict == "retry_quality":
        return "quality"
    if verdict == "retry_semantic":
        return "semantic"
    return "publish"
