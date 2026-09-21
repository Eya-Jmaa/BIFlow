from __future__ import annotations

import re
from pathlib import Path

import duckdb
import polars as pl

from app.config import get_settings
from app.security.sql import validate_readonly_sql


def _ident(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", name or "")
    if not cleaned or cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    return cleaned


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
            table = _ident(path.stem)
            escaped = str(path.resolve()).replace("\\", "/").replace("'", "''")
            # DuckDB rejects prepared parameters in CREATE VIEW.
            self.con.execute(
                f'CREATE OR REPLACE VIEW "{table}" AS SELECT * FROM read_parquet(\'{escaped}\')'
            )
            self.tables.append(table)

    def register_frames(self, tables: dict[str, pl.DataFrame]) -> None:
        for name, frame in tables.items():
            ident = _ident(name)
            self.con.execute(f'DROP VIEW IF EXISTS "{ident}"')
            try:
                self.con.unregister(ident)
            except Exception:
                pass
            self.con.register(ident, frame.to_arrow())
            if ident not in self.tables:
                self.tables.append(ident)

    def query(self, sql: str) -> pl.DataFrame:
        safe_sql = validate_readonly_sql(sql)
        result = self.con.execute(safe_sql).arrow()
        return pl.from_arrow(result)

    def close(self) -> None:
        self.con.close()
