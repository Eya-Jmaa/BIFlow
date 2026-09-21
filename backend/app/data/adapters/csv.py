from __future__ import annotations

from pathlib import Path

import charset_normalizer
import pandas as pd
import polars as pl

from app.data.adapters.base import DatasetAdapter, SchemaField
from app.data.schema_infer import SchemaInference, infer_and_apply

POLARS_ENCODINGS = {"utf8", "utf8-lossy"}


def detect_encoding(path: Path, nbytes: int = 256_000) -> str:
    raw = path.read_bytes()[:nbytes]
    if raw.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    result = charset_normalizer.from_bytes(raw).best()
    if result is None:
        return "utf-8"
    encoding = (result.encoding or "utf-8").lower()
    if encoding in {"ascii", "utf_8", "utf-8"}:
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
        frame, _ = self.load_with_inference(n_rows=n_rows)
        return frame

    def load_with_inference(self, n_rows: int | None = None) -> tuple[pl.DataFrame, SchemaInference]:
        """Load, then re-type columns from scored evidence rather than a guess.

        ``try_parse_dates`` is deliberately off: it infers a format from the
        first rows and silently nulls everything that disagrees, which on a
        M/D/Y file destroys every row whose day exceeds 12. Dates are resolved
        afterwards by :mod:`app.data.schema_infer`, which records the chosen
        format and its parse rate.
        """
        frame = self._read_raw(n_rows=n_rows)
        return infer_and_apply(frame, self.name)

    def _read_raw(self, n_rows: int | None = None) -> pl.DataFrame:
        last_error: Exception | None = None
        for encoding in ("utf8-lossy", "utf8"):
            try:
                return pl.read_csv(
                    self.path,
                    separator=self.delimiter,
                    encoding=encoding,
                    infer_schema_length=5000,
                    n_rows=n_rows,
                    ignore_errors=True,
                    try_parse_dates=False,
                )
            except Exception as exc:
                last_error = exc

        pandas_encodings = [self.encoding, "utf-8-sig", "utf-8", "cp1252", "latin-1", "iso-8859-1"]
        seen: set[str] = set()
        for encoding in pandas_encodings:
            key = encoding.lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                frame = pd.read_csv(
                    self.path,
                    encoding=encoding,
                    sep=self.delimiter,
                    nrows=n_rows,
                    engine="python",
                    on_bad_lines="skip",
                )
                return pl.from_pandas(frame)
            except Exception as exc:
                last_error = exc

        raise ValueError(f"Could not parse CSV {self.path.name}: {last_error}") from last_error

    def schema(self) -> list[SchemaField]:
        frame = self.load(n_rows=200)
        return [SchemaField(name=col, dtype=str(dtype), nullable=True) for col, dtype in zip(frame.columns, frame.dtypes)]

    def metadata(self):
        meta = super().metadata()
        meta.encoding = self.encoding
        meta.delimiter = self.delimiter
        return meta

    def lazy(self) -> pl.LazyFrame:
        return self.load().lazy()
