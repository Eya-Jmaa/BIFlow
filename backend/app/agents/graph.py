from __future__ import annotations

from typing import Any
from uuid import UUID

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.agents.state import PipelineState
from app.pipeline.executor import PipelineExecutor


def build_graph():
    graph = StateGraph(PipelineState)
    graph.add_node("run", _run_node)
    graph.add_edge(START, "run")
    graph.add_edge("run", END)
    return graph.compile()


def _run_node(state: PipelineState) -> PipelineState:
    # The detailed agent graph with retries lives in PipelineExecutor.
    # LangGraph owns the top-level invocation contract and persisted state envelope.
    state["status"] = "delegated"
    return state


def invoke_pipeline(db: Session, project_id: UUID, run_id: UUID) -> None:
    executor = PipelineExecutor(db, project_id, run_id)
    executor.execute()
