from __future__ import annotations

from typing import Any

import numpy as np
import polars as pl
from sklearn.linear_model import LinearRegression


def zscore_anomalies(values: list[float], threshold: float = 2.5) -> list[dict[str, Any]]:
    clean = [float(v) for v in values if v is not None]
    if len(clean) < 4:
        return []
    arr = np.array(clean, dtype=float)
    std = arr.std(ddof=1)
    if std == 0:
        return []
    mean = arr.mean()
    anomalies = []
    for idx, value in enumerate(arr):
        z = (value - mean) / std
        if abs(z) >= threshold:
            anomalies.append({"index": int(idx), "value": float(value), "zscore": float(z), "method": "zscore"})
    return anomalies


def iqr_outliers(values: list[float]) -> list[dict[str, Any]]:
    clean = [float(v) for v in values if v is not None]
    if len(clean) < 4:
        return []
    arr = np.array(clean, dtype=float)
    q1, q3 = np.percentile(arr, [25, 75])
    iqr = q3 - q1
    if iqr == 0:
        return []
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    return [
        {"index": int(i), "value": float(v), "method": "iqr"}
        for i, v in enumerate(arr)
        if v < lower or v > upper
    ]


def linear_trend(values: list[float]) -> dict[str, Any]:
    clean = [float(v) for v in values if v is not None]
    if len(clean) < 3:
        return {"slope": None, "direction": "insufficient_data", "r2": None}
    x = np.arange(len(clean)).reshape(-1, 1)
    y = np.array(clean)
    model = LinearRegression().fit(x, y)
    r2 = float(model.score(x, y))
    slope = float(model.coef_[0])
    if slope > 0 and r2 >= 0.2:
        direction = "up"
    elif slope < 0 and r2 >= 0.2:
        direction = "down"
    else:
        direction = "flat"
    return {"slope": slope, "direction": direction, "r2": r2, "intercept": float(model.intercept_)}


def period_change(current: float | None, previous: float | None) -> dict[str, Any]:
    if current is None or previous is None:
        return {"change": None, "change_pct": None}
    change = current - previous
    change_pct = None if previous == 0 else change / previous
    return {"change": change, "change_pct": change_pct}


def pareto(frame: pl.DataFrame, dimension: str, measure: str, share: float = 0.8) -> dict[str, Any]:
    if dimension not in frame.columns or measure not in frame.columns or frame.height == 0:
        return {"items": [], "cutoff_count": 0}
    grouped = (
        frame.group_by(dimension)
        .agg(pl.col(measure).sum().alias("value"))
        .drop_nulls()
        .sort("value", descending=True)
    )
    total = grouped["value"].sum()
    if not total:
        return {"items": [], "cutoff_count": 0, "total": 0}
    items = []
    cumulative = 0.0
    cutoff = 0
    for row in grouped.to_dicts():
        cumulative += float(row["value"])
        pct = cumulative / float(total)
        items.append({"dimension": str(row[dimension]), "value": float(row["value"]), "cumulative_share": pct})
        if pct < share:
            cutoff += 1
    return {"items": items[:25], "cutoff_count": cutoff + 1, "total": float(total), "share": share}


def correlation_matrix(frame: pl.DataFrame) -> list[dict[str, Any]]:
    numeric_cols = [c for c in frame.columns if frame[c].dtype.is_numeric()]
    pairs: list[dict[str, Any]] = []
    for i, a in enumerate(numeric_cols):
        for b in numeric_cols[i + 1 :]:
            sub = frame.select([a, b]).drop_nulls()
            if sub.height < 10:
                continue
            corr = sub.select(pl.corr(a, b)).item()
            if corr is None:
                continue
            pairs.append({"left": a, "right": b, "correlation": float(corr)})
    pairs.sort(key=lambda item: abs(item["correlation"]), reverse=True)
    return pairs[:20]


def concentration(frame: pl.DataFrame, dimension: str) -> dict[str, Any] | None:
    if dimension not in frame.columns or frame.height == 0:
        return None
    counts = frame[dimension].drop_nulls().value_counts().sort("count", descending=True)
    total = int(counts["count"].sum())
    if total == 0:
        return None
    top = counts.head(1).to_dicts()[0]
    dim_key = dimension if dimension in top else [k for k in top if k != "count"][0]
    return {
        "dimension": dimension,
        "top_value": str(top[dim_key]),
        "share": float(top["count"]) / total,
        "distinct": counts.height,
    }
