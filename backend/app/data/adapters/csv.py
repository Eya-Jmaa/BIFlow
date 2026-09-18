from __future__ import annotations

from pathlib import Path

import charset_normalizer
import polars as pl

from app.data.adapters.base import DatasetAdapter, SchemaField


def detect_encoding(path: Path, nbytes: int = 256_000) -> str:
    raw = path.read_bytes()[:nbytes]
    result = charset_normalizer.from_bytes(raw).best()
    if result is None:
        return "utf-8"
    encoding = result.encoding or "utf-8"
    if encoding.lower() in {"ascii", "utf_8"}:
        return "utf-8"
    return encoding


def detect_delimiter(path: Path, encoding: str) -> str:
    sample = path.read_text(encoding=encoding, errors="replace")[:8192]
    candidates = [",", ";", "\t", "|"]
    scores = {d: sample.count(d) for d in candidates}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ","


class CSVAdapter(DatasetAdapter):
    source_type = "csv"

    def __init__(self, path: str | Path, name: str | None = None, encoding: str | None = None, delimiter: str | None = None) -> None:
        super().__init__(path, name)
        self.encoding = encoding or detect_encoding(self.path)
        self.delimiter = delimiter or detect_delimiter(self.path, self.encoding)

    def load(self, n_rows: int | None = None) -> pl.DataFrame:
        return pl.read_csv(
            self.path,
            separator=self.delimiter,
            encoding=self._csv_encoding(),
            infer_schema_length=5000,
            n_rows=n_rows,
            ignore_errors=True,
            try_parse_dates=True,
        )

    def schema(self) -> list[SchemaField]:
        frame = self.load(n_rows=200)
        return [SchemaField(name=col, dtype=str(dtype), nullable=True) for col, dtype in zip(frame.columns, frame.dtypes)]

    def metadata(self):
        meta = super().metadata()
        meta.encoding = self.encoding
        meta.delimiter = self.delimiter
        return meta

    def _csv_encoding(self) -> str:
        encoding = self.encoding.lower().replace("_", "-")
        if encoding in {"utf-8", "utf8"}:
            return "utf8"
        return encoding

    def lazy(self) -> pl.LazyFrame:
        return pl.scan_csv(
            self.path,
            separator=self.delimiter,
            encoding=self._csv_encoding(),
            infer_schema_length=5000,
            ignore_errors=True,
            try_parse_dates=True,
        )
