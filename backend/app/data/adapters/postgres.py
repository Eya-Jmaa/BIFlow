from __future__ import annotations

from typing import Any

import polars as pl
from sqlalchemy import create_engine, text

from app.data.adapters.base import DatasetAdapter, DatasetMetadata, SchemaField
from app.security.sql import assert_readonly_identifier


class PostgresAdapter(DatasetAdapter):
    source_type = "postgres"

    def __init__(self, dsn: str, table: str, name: str | None = None, schema: str = "public") -> None:
        super().__init__(path=table, name=name or table)
        self.dsn = dsn
        self.table = table
        self.db_schema = schema

    def _qualified(self) -> str:
        assert_readonly_identifier(self.db_schema)
        assert_readonly_identifier(self.table)
        return f'"{self.db_schema}"."{self.table}"'

    def load(self, n_rows: int | None = None) -> pl.DataFrame:
        engine = create_engine(self.dsn)
        limit = f" LIMIT {int(n_rows)}" if n_rows else ""
        query = f"SELECT * FROM {self._qualified()}{limit}"
        with engine.connect() as conn:
            return pl.read_database(query, connection=conn)

    def schema(self) -> list[SchemaField]:
        engine = create_engine(self.dsn)
        sql = text(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = :schema AND table_name = :table
            ORDER BY ordinal_position
            """
        )
        with engine.connect() as conn:
            rows = conn.execute(sql, {"schema": self.db_schema, "table": self.table}).mappings().all()
        return [
            SchemaField(name=row["column_name"], dtype=row["data_type"], nullable=row["is_nullable"] == "YES")
            for row in rows
        ]

    def metadata(self) -> DatasetMetadata:
        engine = create_engine(self.dsn)
        with engine.connect() as conn:
            count = conn.execute(text(f"SELECT COUNT(*) FROM {self._qualified()}")).scalar_one()
        fields = self.schema()
        return DatasetMetadata(
            name=self.name,
            source_type=self.source_type,
            path=self._qualified(),
            row_count=int(count),
            column_count=len(fields),
        )
