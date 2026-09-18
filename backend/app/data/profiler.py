from __future__ import annotations

import math
import re
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[\d\s().-]{8,}$")
ID_HINTS = ("id", "uuid", "pk", "key", "code")
DATE_HINTS = ("date", "time", "timestamp", "dt", "created", "updated")
MONEY_HINTS = ("price", "amount", "value", "revenue", "cost", "payment", "total", "fee", "freight")
GEO_HINTS = ("city", "state", "country", "zip", "cep", "lat", "lon", "lng", "region", "province")
QTY_HINTS = ("qty", "quantity", "count", "units")


class ColumnProfile(BaseModel):
    name: str
    inferred_type: str
    logical_type: str
    null_count: int
    null_pct: float
    distinct_count: int
    uniqueness_pct: float
    is_candidate_pk: bool = False
    is_candidate_fk: bool = False
    semantic_hint: str | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    sample_values: list[str] = Field(default_factory=list)


class TableProfile(BaseModel):
    name: str
    row_count: int
    column_count: int
    duplicate_row_count: int = 0
    quality_score: float
    columns: list[ColumnProfile]
    warnings: list[str] = Field(default_factory=list)
    pii_flags: list[dict[str, Any]] = Field(default_factory=list)


NUMERIC_DTYPES = {
    pl.Int8, pl.Int16, pl.Int32, pl.Int64,
    pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
    pl.Float32, pl.Float64, pl.Decimal,
}
TEMPORAL_DTYPES = {pl.Date, pl.Datetime, pl.Time, pl.Duration}


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _logical_type(name: str, dtype: pl.DataType, distinct: int, rows: int, sample: list[str]) -> str:
    lowered = name.lower()
    if any(h in lowered for h in DATE_HINTS) or dtype in TEMPORAL_DTYPES:
        return "datetime"
    if dtype in NUMERIC_DTYPES:
        if any(h in lowered for h in MONEY_HINTS):
            return "currency"
        if any(h in lowered for h in QTY_HINTS):
            return "quantity"
        if any(h in lowered for h in ID_HINTS) and distinct >= max(1, int(rows * 0.9)):
            return "identifier"
        return "numeric"
    if any(h in lowered for h in GEO_HINTS):
        return "geo"
    if distinct > 0 and distinct <= max(20, int(rows * 0.05)):
        return "categorical"
    if any(h in lowered for h in ID_HINTS):
        return "identifier"
    if sample and sum(1 for v in sample if EMAIL_RE.match(v or "")) >= max(1, len(sample) // 2):
        return "email"
    return "text"


def _semantic_hint(name: str, logical: str) -> str:
    lowered = name.lower()
    if logical == "currency":
        return "measure.revenue_like"
    if logical == "quantity":
        return "measure.quantity"
    if logical == "datetime":
        return "dimension.time"
    if logical == "geo":
        return "dimension.geo"
    if logical == "categorical":
        return "dimension.category"
    if logical == "identifier":
        return "identifier"
    if "status" in lowered:
        return "dimension.status"
    if "customer" in lowered:
        return "entity.customer"
    if "product" in lowered:
        return "entity.product"
    if "order" in lowered:
        return "entity.order"
    return logical


def profile_frame(frame: pl.DataFrame, name: str) -> TableProfile:
    rows = frame.height
    columns: list[ColumnProfile] = []
    warnings: list[str] = []
    if rows == 0:
        warnings.append("Table is empty")

    duplicate_count = 0
    if rows > 0:
        duplicate_count = int(rows - frame.unique().height)

    for col in frame.columns:
        series = frame[col]
        dtype = series.dtype
        null_count = int(series.null_count())
        null_pct = (null_count / rows * 100) if rows else 0.0
        distinct = int(series.n_unique())
        uniqueness = (distinct / rows * 100) if rows else 0.0
        non_null = series.drop_nulls()
        sample_values = [str(v) for v in non_null.head(8).to_list()]
        logical = _logical_type(col, dtype, distinct, rows, sample_values)
        col_warnings: list[str] = []
        stats: dict[str, Any] = {"polars_dtype": str(dtype)}

        if dtype in NUMERIC_DTYPES and non_null.len() > 0:
            numeric = non_null.cast(pl.Float64, strict=False)
            desc = numeric.describe()
            desc_map = {row["statistic"]: _safe_float(row["value"]) for row in desc.to_dicts()}
            quantiles = {
                "q25": _safe_float(numeric.quantile(0.25)),
                "q50": _safe_float(numeric.quantile(0.50)),
                "q75": _safe_float(numeric.quantile(0.75)),
            }
            stats.update(
                {
                    "count": int(numeric.len()),
                    "mean": desc_map.get("mean"),
                    "std": desc_map.get("std"),
                    "min": desc_map.get("min"),
                    "max": desc_map.get("max"),
                    "median": quantiles["q50"],
                    **quantiles,
                }
            )
            q1, q3 = quantiles["q25"], quantiles["q75"]
            if q1 is not None and q3 is not None:
                iqr = q3 - q1
                if iqr > 0:
                    outlier_mask = (numeric < q1 - 1.5 * iqr) | (numeric > q3 + 1.5 * iqr)
                    outlier_count = int(outlier_mask.sum())
                    stats["outlier_count_iqr"] = outlier_count
                    if outlier_count / numeric.len() > 0.05:
                        col_warnings.append("High outlier rate by IQR")
            if stats.get("min") is not None and stats.get("max") is not None and stats["min"] < 0 and "id" in col.lower():
                col_warnings.append("Negative values in identifier-like column")
        elif dtype in TEMPORAL_DTYPES and non_null.len() > 0:
            stats.update(
                {
                    "min_date": str(non_null.min()),
                    "max_date": str(non_null.max()),
                    "granularity": _infer_date_granularity(non_null),
                }
            )
        else:
            value_counts = (
                non_null.cast(pl.Utf8, strict=False)
                .value_counts()
                .sort("count", descending=True)
                .head(10)
            )
            top_values = [
                {"value": str(row[col]) if col in row else str(row.get(value_counts.columns[0])), "count": int(row["count"])}
                for row in value_counts.to_dicts()
            ]
            # Polars value_counts uses the original column name.
            cleaned_top = []
            for row in value_counts.to_dicts():
                value = row.get(col)
                if value is None:
                    value = next(v for k, v in row.items() if k != "count")
                cleaned_top.append({"value": str(value), "count": int(row["count"])})
            stats["top_values"] = cleaned_top
            stats["distinct_count"] = distinct

        is_pk = uniqueness >= 99.5 and null_count == 0 and rows > 0
        is_fk = ("id" in col.lower() or col.lower().endswith("_fk")) and not is_pk and uniqueness >= 1
        if null_pct > 40:
            col_warnings.append("High missingness")
        if uniqueness == 100 and rows > 1 and logical == "text":
            col_warnings.append("All values unique — possible identifier")

        columns.append(
            ColumnProfile(
                name=col,
                inferred_type=str(dtype),
                logical_type=logical,
                null_count=null_count,
                null_pct=round(null_pct, 4),
                distinct_count=distinct,
                uniqueness_pct=round(uniqueness, 4),
                is_candidate_pk=is_pk,
                is_candidate_fk=is_fk,
                semantic_hint=_semantic_hint(col, logical),
                stats=stats,
                warnings=col_warnings,
                sample_values=sample_values[:5],
            )
        )

    completeness = 100 - (sum(c.null_pct for c in columns) / len(columns) if columns else 0)
    uniqueness_score = 100 - min(100, (duplicate_count / rows * 100 if rows else 0))
    quality_score = round((completeness * 0.6 + uniqueness_score * 0.4), 2)
    if duplicate_count:
        warnings.append(f"{duplicate_count} duplicate rows detected")

    return TableProfile(
        name=name,
        row_count=rows,
        column_count=len(frame.columns),
        duplicate_row_count=duplicate_count,
        quality_score=quality_score,
        columns=columns,
        warnings=warnings,
    )


def _infer_date_granularity(series: pl.Series) -> str:
    try:
        as_dt = series.cast(pl.Datetime, strict=False).drop_nulls()
        if as_dt.len() < 3:
            return "unknown"
        diffs = as_dt.sort().diff().drop_nulls().dt.total_days()
        median_days = _safe_float(diffs.median()) or 0
        if median_days < 1:
            return "hour_or_finer"
        if median_days <= 2:
            return "day"
        if median_days <= 10:
            return "week"
        if median_days <= 40:
            return "month"
        return "year"
    except Exception:
        return "unknown"
