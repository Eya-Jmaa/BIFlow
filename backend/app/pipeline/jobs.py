from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.agents.graph import invoke_pipeline
from app.config import get_settings
from app.logging import get_logger
from app.models import PipelineRun, PipelineStep, Project
from app.pipeline.executor import STEP_SEQUENCE
from app.pipeline.events import publish_event

logger = get_logger(service="jobs")


def enqueue_pipeline(run_id: str) -> None:
    settings = get_settings()
    try:
        import redis
        from rq import Queue

        queue = Queue(settings.rq_queue_name, connection=redis.from_url(settings.redis_url))
        queue.enqueue(run_pipeline_job, run_id, job_timeout=settings.pipeline_step_timeout_seconds * 8)
    except Exception as exc:
        logger.warning("queue_unavailable_running_inline", error=str(exc), run_id=run_id)
        run_pipeline_job(run_id)


def run_pipeline_job(run_id: str) -> None:
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        run = db.get(PipelineRun, UUID(run_id))
        if run is None:
            raise RuntimeError(f"Unknown pipeline run {run_id}")
        invoke_pipeline(db, run.project_id, run.id)
    finally:
        db.close()


def create_run(db: Session, project: Project) -> PipelineRun:
    settings = get_settings()
    run = PipelineRun(
        project_id=project.id,
        status="queued",
        business_objective=project.business_objective,
        llm_provider=settings.llm_provider if settings.llm_configured else None,
        llm_model=settings.llm_model if settings.llm_configured else None,
        agent_versions={
            "orchestrator": "1.0",
            "profiler": "1.0",
            "quality": "1.0",
            "semantic": "1.0",
            "analyst": "1.0",
            "dashboard": "1.0",
            "auditor": "1.0",
        },
        dataset_versions={str(ds.id): ds.checksum for ds in project.datasets},
    )
    db.add(run)
    db.flush()
    for index, (name, display) in enumerate(STEP_SEQUENCE):
        db.add(
            PipelineStep(
                run_id=run.id,
                name=name,
                display_name=display,
                status="pending",
                sequence=index,
            )
        )
    db.commit()
    db.refresh(run)
    publish_event(str(run.id), "pipeline.queued", {"project_id": str(project.id)})
    return run
