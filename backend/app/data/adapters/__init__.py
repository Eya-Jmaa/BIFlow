from __future__ import annotations

from pathlib import Path

from app.data.adapters.api import APIAdapter
from app.data.adapters.base import DatasetAdapter
from app.data.adapters.csv import CSVAdapter
from app.data.adapters.excel import ExcelAdapter
from app.data.adapters.parq import ParquetAdapter
from app.data.adapters.postgres import PostgresAdapter


def adapter_for_file(path: str | Path, name: str | None = None) -> DatasetAdapter:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return CSVAdapter(file_path, name=name)
    if suffix == ".parquet":
        return ParquetAdapter(file_path, name=name)
    if suffix in {".xlsx", ".xls"}:
        return ExcelAdapter(file_path, name=name)
    raise ValueError(f"Unsupported file type: {suffix}")


__all__ = [
    "DatasetAdapter",
    "CSVAdapter",
    "ParquetAdapter",
    "ExcelAdapter",
    "PostgresAdapter",
    "APIAdapter",
    "adapter_for_file",
]
