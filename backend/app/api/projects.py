from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.adapters import adapter_for_file
from app.db.session import get_db
from app.domains.profiles import get_domain, infer_domain
from app.models import Dataset, DatasetFile, Project
from app.schemas.api import DatasetOut, ProjectCreate, ProjectOut
from app.security.files import safe_join, validate_upload

router = APIRouter()


class DomainInferRequest(BaseModel):
    business_objective: str
    columns: list[str] = []


@router.post("/projects", response_model=ProjectOut)
def create_project(payload: ProjectCreate, db: Session = Depends(get_db)) -> Project:
    project = Project(
        name=payload.name,
        description=payload.description,
        business_objective=payload.business_objective,
        domain=payload.domain,
        status="draft",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(db: Session = Depends(get_db)) -> list[Project]:
    return db.query(Project).order_by(Project.created_at.desc()).all()


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: UUID, db: Session = Depends(get_db)) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    return project


@router.delete("/projects/{project_id}")
def delete_project(project_id: UUID, db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    db.delete(project)
    db.commit()
    return {"deleted": str(project_id)}


@router.post("/projects/{project_id}/datasets", response_model=DatasetOut)
async def upload_dataset(
    project_id: UUID,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> Dataset:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(404, "Project not found")
    content = await file.read()
    filename = validate_upload(file, len(content))
    settings = get_settings()
    dataset_id = uuid4()
    dest_dir = safe_join(settings.raw_dir, str(project_id), str(dataset_id))
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    dest.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    adapter = adapter_for_file(dest, name=Path(filename).stem)
    try:
        meta = adapter.metadata()
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Could not read dataset: {exc}") from exc
    table_name = Path(filename).stem.replace("-", "_").replace(" ", "_")
    dataset = Dataset(
        id=dataset_id,
        project_id=project.id,
        name=Path(filename).stem,
        table_name=table_name,
        layer="raw",
        source_type=adapter.source_type,
        row_count=meta.row_count,
        column_count=meta.column_count,
        checksum=checksum,
        status="uploaded",
        extra_metadata={"encoding": meta.encoding, "delimiter": meta.delimiter},
    )
    db.add(dataset)
    db.add(
        DatasetFile(
            dataset_id=dataset.id,
            filename=filename,
            original_filename=filename,
            mime_type=file.content_type,
            size_bytes=len(content),
            encoding=meta.encoding,
            delimiter=meta.delimiter,
            storage_path=str(dest),
            checksum=checksum,
        )
    )
    db.commit()
    db.refresh(dataset)
    return dataset


@router.get("/projects/{project_id}/datasets", response_model=list[DatasetOut])
def list_datasets(project_id: UUID, db: Session = Depends(get_db)) -> list[Dataset]:
    return db.query(Dataset).filter(Dataset.project_id == project_id).all()


class DomainPreview(BaseModel):
    """What the orchestrator would infer from this objective, right now."""

    domain: str
    matched_terms: list[str]
    common_dimensions: list[str]
    common_metrics: list[str]
    common_kpis: list[str]
    rules: list[str]
    confident: bool


@router.post("/domains/infer", response_model=DomainPreview)
def infer_domain_preview(payload: DomainInferRequest) -> DomainPreview:
    """Preview domain inference before a project exists.

    This runs the same deterministic `infer_domain` the BI Orchestrator uses at
    the start of a run, so the preview a user sees while typing their objective
    is the decision the pipeline will actually make — not an illustration of one.
    """
    objective = payload.business_objective or ""
    columns = payload.columns or []
    domain = infer_domain(objective, columns)
    profile = get_domain(domain)

    blob = f"{objective} {' '.join(columns)}".lower()
    matched = sorted(
        {
            term
            for term in profile.business_terms + profile.common_metrics + profile.common_dimensions
            if term.lower() in blob
        }
    )
    return DomainPreview(
        domain=domain,
        matched_terms=matched,
        common_dimensions=profile.common_dimensions,
        common_metrics=profile.common_metrics,
        common_kpis=profile.common_kpis,
        rules=profile.rules,
        # "general" is the fallback when nothing matched, not a positive match.
        confident=domain != "general" and bool(matched),
    )
