from __future__ import annotations

from pathlib import Path

import polars as pl

from app.data.adapters.base import DatasetAdapter, SchemaField


class ExcelAdapter(DatasetAdapter):
    source_type = "excel"

    def __init__(self, path: str | Path, name: str | None = None, sheet_name: str | None = None) -> None:
        super().__init__(path, name)
        self.sheet_name = sheet_name

    def load(self, n_rows: int | None = None) -> pl.DataFrame:
        frame = pl.read_excel(self.path, sheet_name=self.sheet_name, engine="openpyxl")
        if n_rows is not None:
            return frame.head(n_rows)
        return frame

    def schema(self) -> list[SchemaField]:
        frame = self.load(n_rows=200)
        return [SchemaField(name=col, dtype=str(dtype)) for col, dtype in zip(frame.columns, frame.dtypes)]
