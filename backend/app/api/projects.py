from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import get_settings
from app.data.adapters import adapter_for_file
from app.db.session import get_db
from app.models import Dataset, DatasetFile, Project
from app.schemas.api import DatasetOut, ProjectCreate, ProjectOut
from app.security.files import safe_join, validate_upload

router = APIRouter()


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
    meta = adapter.metadata()
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
