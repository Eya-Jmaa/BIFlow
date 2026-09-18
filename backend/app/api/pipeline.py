from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import PipelineRun, PipelineStep, Project
from app.pipeline.events import event_history
from app.pipeline.jobs import create_run, enqueue_pipeline
from app.schemas.api import PipelineRunOut, PipelineStepOut

router = APIRouter()


@router.post("/projects/{project_id}/pipeline/run", response_model=PipelineRunOut)
def start_pipeline(project_id: UUID, db: Session = Depends(get_db)) -> PipelineRun:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    from app.models import Dataset

    if db.query(Dataset).filter(Dataset.project_id == project.id).count() == 0:
        raise HTTPException(400, "Upload at least one dataset before running the pipeline")
    run = create_run(db, project)
    enqueue_pipeline(str(run.id))
    return run


@router.get("/projects/{project_id}/pipeline-runs", response_model=list[PipelineRunOut])
def list_runs(project_id: UUID, db: Session = Depends(get_db)) -> list[PipelineRun]:
    return (
        db.query(PipelineRun)
        .filter(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
        .all()
    )


@router.get("/pipeline-runs/{run_id}", response_model=PipelineRunOut)
def get_run(run_id: UUID, db: Session = Depends(get_db)) -> PipelineRun:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@router.get("/pipeline-runs/{run_id}/steps", response_model=list[PipelineStepOut])
def get_steps(run_id: UUID, db: Session = Depends(get_db)) -> list[PipelineStep]:
    return db.query(PipelineStep).filter(PipelineStep.run_id == run_id).order_by(PipelineStep.sequence).all()


@router.get("/pipeline-runs/{run_id}/events")
def get_events(run_id: UUID) -> list[dict]:
    return event_history(str(run_id))
