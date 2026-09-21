from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl


@dataclass
class SchemaField:
    name: str
    dtype: str
    nullable: bool = True


@dataclass
class DatasetMetadata:
    name: str
    source_type: str
    path: str | None = None
    encoding: str | None = None
    delimiter: str | None = None
    row_count: int | None = None
    column_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class DatasetAdapter(ABC):
    """Common interface for loading tabular sources without mutating raw files."""

    source_type: str

    def __init__(self, path: str | Path, name: str | None = None) -> None:
        self.path = Path(path)
        self.name = name or self.path.stem

    @abstractmethod
    def load(self, n_rows: int | None = None) -> pl.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def schema(self) -> list[SchemaField]:
        raise NotImplementedError

    def load_with_inference(self, n_rows: int | None = None):
        """Load and report how each column's type was decided.

        Sources that already carry a schema (Parquet, Postgres) mostly report
        ``keep``; text sources resolve dates and numbers from scored evidence.
        Adapters that read typed formats inherit this; CSV overrides it.
        """
        from app.data.schema_infer import infer_and_apply

        return infer_and_apply(self.load(n_rows=n_rows), self.name)

    def sample(self, n: int = 20) -> pl.DataFrame:
        return self.load(n_rows=n)

    def metadata(self) -> DatasetMetadata:
        frame = self.load()
        return DatasetMetadata(
            name=self.name,
            source_type=self.source_type,
            path=str(self.path),
            row_count=frame.height,
            column_count=frame.width,
        )

    def lazy(self) -> pl.LazyFrame:
        return self.load().lazy()
