from __future__ import annotations

from typing import Any

import httpx
import polars as pl

from app.data.adapters.base import DatasetAdapter, DatasetMetadata, SchemaField


class APIAdapter(DatasetAdapter):
    """Loads a tabular JSON array from a controlled HTTP endpoint."""

    source_type = "api"

    def __init__(self, url: str, name: str | None = None, headers: dict[str, str] | None = None, records_path: str | None = None) -> None:
        super().__init__(path=url, name=name or "api_source")
        self.url = url
        self.headers = headers or {}
        self.records_path = records_path

    def _fetch(self) -> list[dict[str, Any]]:
        with httpx.Client(timeout=30.0, follow_redirects=True) as client:
            response = client.get(self.url, headers=self.headers)
            response.raise_for_status()
            payload = response.json()
        if self.records_path:
            for part in self.records_path.split("."):
                payload = payload[part]
        if not isinstance(payload, list):
            raise ValueError("API payload is not a JSON array of records")
        return payload

    def load(self, n_rows: int | None = None) -> pl.DataFrame:
        records = self._fetch()
        if n_rows is not None:
            records = records[:n_rows]
        return pl.DataFrame(records)

    def schema(self) -> list[SchemaField]:
        frame = self.load(n_rows=50)
        return [SchemaField(name=col, dtype=str(dtype)) for col, dtype in zip(frame.columns, frame.dtypes)]

    def metadata(self) -> DatasetMetadata:
        frame = self.load()
        return DatasetMetadata(
            name=self.name,
            source_type=self.source_type,
            path=self.url,
            row_count=frame.height,
            column_count=frame.width,
        )
