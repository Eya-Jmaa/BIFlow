"""Entry point that runs a pipeline through the agent graph."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.graph_def import agent_graph
from app.agents.state import PipelineState
from app.logging import get_logger
from app.pipeline.events import publish_event
from app.pipeline.executor import PipelineExecutor

logger = get_logger(service="graph")

# Each feedback edge can re-enter a node, so the walk is bounded well above the
# eight nodes of a clean run but still far below any possibility of a loop.
GRAPH_STEP_LIMIT = 40


def build_graph(executor: PipelineExecutor):
    return agent_graph(executor.handlers())


def invoke_pipeline(db: Session, project_id: UUID, run_id: UUID) -> None:
    """Run every agent for one pipeline run, under graph control."""
    executor = PipelineExecutor(db, project_id, run_id)
    executor.run.status = "running"
    executor.run.started_at = datetime.now(timezone.utc)
    db.commit()
    publish_event(str(run_id), "pipeline.started", {"project_id": str(project_id)})

    try:
        executor.load()
    except Exception as exc:  # noqa: BLE001 - nothing can run without tables
        logger.exception("pipeline_load_failed", run_id=str(run_id), error=str(exc))
        executor.fail(str(exc))
        raise

    state: PipelineState = {
        "project_id": str(project_id),
        "run_id": str(run_id),
        "business_objective": executor.project.business_objective,
        "errors": [],
        "warnings": [],
        "retry": {},
        "summaries": {},
        "status": "started",
    }

    graph = build_graph(executor)
    try:
        final = graph.invoke(state, config={"recursion_limit": GRAPH_STEP_LIMIT})
    except Exception as exc:  # noqa: BLE001 - graph-level failure
        logger.exception("pipeline_failed", run_id=str(run_id), error=str(exc))
        executor.fail(str(exc))
        raise

    errors = final.get("errors") or []
    if errors and final.get("status") != "published":
        executor.fail("; ".join(errors))
        raise RuntimeError(f"Pipeline finished with errors: {'; '.join(errors)}")
    if errors:
        logger.warning("pipeline_completed_with_errors", run_id=str(run_id), errors=errors)
