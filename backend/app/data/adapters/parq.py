from __future__ import annotations

from pathlib import Path

import polars as pl

from app.data.adapters.base import DatasetAdapter, SchemaField


class ParquetAdapter(DatasetAdapter):
    source_type = "parquet"

    def load(self, n_rows: int | None = None) -> pl.DataFrame:
        frame = pl.read_parquet(self.path)
        if n_rows is not None:
            return frame.head(n_rows)
        return frame

    def schema(self) -> list[SchemaField]:
        schema = pl.read_parquet_schema(self.path)
        return [SchemaField(name=name, dtype=str(dtype)) for name, dtype in schema.items()]

    def lazy(self) -> pl.LazyFrame:
        return pl.scan_parquet(self.path)
