from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_settings


def validate_upload(file: UploadFile, size_bytes: int) -> str:
    settings = get_settings()
    filename = Path(file.filename or "").name
    if not filename or filename in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if ".." in Path(filename).parts:
        raise HTTPException(status_code=400, detail="Path traversal is not allowed")
    suffix = Path(filename).suffix.lower().lstrip(".")
    if suffix not in settings.allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: .{suffix}")
    if size_bytes <= 0:
        raise HTTPException(status_code=400, detail="Empty file")
    if size_bytes > settings.max_upload_bytes:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.max_upload_mb} MB limit")
    return filename


def safe_join(root: Path, *parts: str) -> Path:
    candidate = (root.joinpath(*parts)).resolve()
    root_resolved = root.resolve()
    if root_resolved not in candidate.parents and candidate != root_resolved:
        raise HTTPException(status_code=400, detail="Invalid storage path")
    return candidate
