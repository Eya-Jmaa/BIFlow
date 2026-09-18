from __future__ import annotations

from typing import Any, Literal

import polars as pl
from pydantic import BaseModel, Field


ALLOWED_OPERATIONS = {
    "trim_whitespace",
    "empty_to_null",
    "normalize_case",
    "cast_numeric",
    "cast_datetime",
    "drop_duplicates",
    "drop_all_null_rows",
}


class TransformStep(BaseModel):
    operation: Literal[
        "trim_whitespace",
        "empty_to_null",
        "normalize_case",
        "cast_numeric",
        "cast_datetime",
        "drop_duplicates",
        "drop_all_null_rows",
    ]
    table_name: str
    column_name: str | None = None
    reason: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class TransformResult(BaseModel):
    operation: str
    table_name: str
    column_name: str | None = None
    rows_affected: int
    reason: str
    before_example: str | None = None
    after_example: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class TransformPlan(BaseModel):
    steps: list[TransformStep]
    notes: list[str] = Field(default_factory=list)


def plan_from_issues(issues) -> TransformPlan:
    steps: list[TransformStep] = []
    seen: set[tuple] = set()
    for issue in issues:
        key = None
        if issue.issue_type == "whitespace" and issue.column_name:
            key = ("trim_whitespace", issue.table_name, issue.column_name)
            step = TransformStep(
                operation="trim_whitespace",
                table_name=issue.table_name,
                column_name=issue.column_name,
                reason=issue.recommended_action,
            )
        elif issue.issue_type == "empty_string" and issue.column_name:
            key = ("empty_to_null", issue.table_name, issue.column_name)
            step = TransformStep(
                operation="empty_to_null",
                table_name=issue.table_name,
                column_name=issue.column_name,
                reason=issue.recommended_action,
            )
        elif issue.issue_type == "duplicates":
            key = ("drop_duplicates", issue.table_name, None)
            step = TransformStep(
                operation="drop_duplicates",
                table_name=issue.table_name,
                reason="Remove exact duplicate rows after review of uniqueness score.",
            )
        else:
            continue
        if key in seen:
            continue
        seen.add(key)
        steps.append(step)
    return TransformPlan(steps=steps, notes=["Only conservative, reversible cleanups are auto-applied. Outliers are never dropped automatically."])


def execute_plan(tables: dict[str, pl.DataFrame], plan: TransformPlan) -> tuple[dict[str, pl.DataFrame], list[TransformResult]]:
    cleaned = {name: frame.clone() for name, frame in tables.items()}
    results: list[TransformResult] = []
    for step in plan.steps:
        if step.table_name not in cleaned:
            continue
        frame = cleaned[step.table_name]
        if step.operation == "trim_whitespace" and step.column_name and step.column_name in frame.columns:
            col = frame[step.column_name]
            if col.dtype not in (pl.Utf8, pl.String) and "String" not in str(col.dtype):
                continue
            before = _first_dirty(col)
            new_col = col.cast(pl.Utf8).str.strip_chars()
            affected = int((col.cast(pl.Utf8, strict=False) != new_col).fill_null(False).sum())
            cleaned[step.table_name] = frame.with_columns(new_col.alias(step.column_name))
            results.append(
                TransformResult(
                    operation=step.operation,
                    table_name=step.table_name,
                    column_name=step.column_name,
                    rows_affected=affected,
                    reason=step.reason,
                    before_example=before,
                    after_example=before.strip() if before else None,
                )
            )
        elif step.operation == "empty_to_null" and step.column_name and step.column_name in frame.columns:
            col = frame[step.column_name].cast(pl.Utf8, strict=False)
            affected = int((col.drop_nulls().str.len_chars() == 0).sum()) if col.len() else 0
            cleaned[step.table_name] = frame.with_columns(
                pl.when(col.str.len_chars() == 0).then(None).otherwise(col).alias(step.column_name)
            )
            results.append(
                TransformResult(
                    operation=step.operation,
                    table_name=step.table_name,
                    column_name=step.column_name,
                    rows_affected=affected,
                    reason=step.reason,
                    before_example="",
                    after_example=None,
                )
            )
        elif step.operation == "drop_duplicates":
            before_h = frame.height
            cleaned[step.table_name] = frame.unique()
            results.append(
                TransformResult(
                    operation=step.operation,
                    table_name=step.table_name,
                    rows_affected=before_h - cleaned[step.table_name].height,
                    reason=step.reason,
                )
            )
        elif step.operation == "normalize_case" and step.column_name:
            col = frame[step.column_name].cast(pl.Utf8, strict=False)
            cleaned[step.table_name] = frame.with_columns(col.str.to_lowercase().alias(step.column_name))
            results.append(
                TransformResult(
                    operation=step.operation,
                    table_name=step.table_name,
                    column_name=step.column_name,
                    rows_affected=frame.height,
                    reason=step.reason,
                )
            )
        elif step.operation == "cast_numeric" and step.column_name:
            col = frame[step.column_name]
            cleaned[step.table_name] = frame.with_columns(col.cast(pl.Float64, strict=False).alias(step.column_name))
            results.append(
                TransformResult(
                    operation=step.operation,
                    table_name=step.table_name,
                    column_name=step.column_name,
                    rows_affected=frame.height,
                    reason=step.reason,
                )
            )
        elif step.operation == "cast_datetime" and step.column_name:
            col = frame[step.column_name]
            cleaned[step.table_name] = frame.with_columns(col.str.to_datetime(strict=False).alias(step.column_name))
            results.append(
                TransformResult(
                    operation=step.operation,
                    table_name=step.table_name,
                    column_name=step.column_name,
                    rows_affected=frame.height,
                    reason=step.reason,
                )
            )
    return cleaned, results


def _first_dirty(col: pl.Series) -> str | None:
    for value in col.drop_nulls().cast(pl.Utf8, strict=False).head(100).to_list():
        if value is not None and value != value.strip():
            return value
    return None
