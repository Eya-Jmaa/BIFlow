from __future__ import annotations

from pathlib import Path

import duckdb
import polars as pl

from app.config import get_settings
from app.security.sql import validate_readonly_sql


class AnalyticalStore:
    """DuckDB-backed analytical store over cleaned parquet tables."""

    def __init__(self, parquet_dir: Path) -> None:
        self.parquet_dir = Path(parquet_dir)
        self.con = duckdb.connect(database=":memory:")
        self.con.execute(f"SET memory_limit='{get_settings().duckdb_memory_limit}'")
        self.tables: list[str] = []
        self._register()

    def _register(self) -> None:
        if not self.parquet_dir.exists():
            return
        for path in sorted(self.parquet_dir.glob("*.parquet")):
            table = path.stem
            self.con.execute(
                f'CREATE OR REPLACE VIEW "{table}" AS SELECT * FROM read_parquet(?)',
                [str(path)],
            )
            self.tables.append(table)

    def register_frames(self, tables: dict[str, pl.DataFrame]) -> None:
        for name, frame in tables.items():
            self.con.register(name, frame.to_arrow())
            if name not in self.tables:
                self.tables.append(name)

    def query(self, sql: str) -> pl.DataFrame:
        safe_sql = validate_readonly_sql(sql)
        result = self.con.execute(safe_sql).arrow()
        return pl.from_arrow(result)

    def close(self) -> None:
        self.con.close()
