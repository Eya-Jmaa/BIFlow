from __future__ import annotations

from typing import Any

import polars as pl
from pydantic import BaseModel, Field

from app.data.profiler import TableProfile
from app.data.schema_infer import SchemaInference


class QualityIssue(BaseModel):
    severity: str
    issue_type: str
    table_name: str
    column_name: str | None = None
    rows_affected: int = 0
    detection_method: str
    recommended_action: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class QualityScorecard(BaseModel):
    overall: float
    completeness: float
    uniqueness: float
    consistency: float
    validity: float
    referential_integrity: float
    issues: list[QualityIssue]
    table_name: str


def assess_quality(
    frame: pl.DataFrame,
    profile: TableProfile,
    join_issues: list[QualityIssue] | None = None,
    inference: SchemaInference | None = None,
) -> QualityScorecard:
    issues: list[QualityIssue] = list(join_issues or [])
    rows = max(frame.height, 1)
    issues.extend(_type_inference_issues(profile.name, inference))

    missing_cells = sum(c.null_count for c in profile.columns)
    total_cells = rows * max(profile.column_count, 1)
    completeness = 100 * (1 - missing_cells / total_cells)

    uniqueness = 100 * (1 - profile.duplicate_row_count / rows)
    if profile.duplicate_row_count:
        issues.append(
            QualityIssue(
                severity="medium" if profile.duplicate_row_count / rows < 0.05 else "high",
                issue_type="duplicates",
                table_name=profile.name,
                rows_affected=profile.duplicate_row_count,
                detection_method="full-row uniqueness",
                recommended_action="Review and optionally drop exact duplicate rows.",
                evidence={"duplicate_row_count": profile.duplicate_row_count},
            )
        )

    consistency_penalties = 0
    validity_penalties = 0
    for column in profile.columns:
        if column.null_pct >= 5:
            issues.append(
                QualityIssue(
                    severity="low" if column.null_pct < 20 else "medium" if column.null_pct < 50 else "high",
                    issue_type="missing_values",
                    table_name=profile.name,
                    column_name=column.name,
                    rows_affected=column.null_count,
                    detection_method="null_count",
                    recommended_action="Keep nulls unless a domain default is justified. Record imputation if applied.",
                    evidence={"null_pct": column.null_pct},
                )
            )
        series = frame[column.name]
        if series.dtype == pl.Utf8 or str(series.dtype).startswith("String"):
            stripped = series.drop_nulls().cast(pl.Utf8)
            whitespace = int((stripped != stripped.str.strip_chars()).sum())
            if whitespace:
                consistency_penalties += min(15, whitespace / rows * 100)
                issues.append(
                    QualityIssue(
                        severity="low",
                        issue_type="whitespace",
                        table_name=profile.name,
                        column_name=column.name,
                        rows_affected=whitespace,
                        detection_method="trim comparison",
                        recommended_action="Trim leading/trailing whitespace.",
                        evidence={"example": _example(stripped, lambda s: s != s.strip())},
                    )
                )
            empty = int((stripped.str.len_chars() == 0).sum())
            if empty:
                validity_penalties += min(10, empty / rows * 100)
                issues.append(
                    QualityIssue(
                        severity="low",
                        issue_type="empty_string",
                        table_name=profile.name,
                        column_name=column.name,
                        rows_affected=empty,
                        detection_method="empty string count",
                        recommended_action="Treat empty strings as nulls.",
                    )
                )
        if column.logical_type == "currency" and "min" in column.stats:
            min_v = column.stats.get("min")
            if min_v is not None and min_v < 0:
                validity_penalties += 10
                issues.append(
                    QualityIssue(
                        severity="medium",
                        issue_type="impossible_values",
                        table_name=profile.name,
                        column_name=column.name,
                        rows_affected=int((frame[column.name] < 0).sum()) if frame[column.name].dtype.is_numeric() else 0,
                        detection_method="domain rule: currency >= 0",
                        recommended_action="Investigate negative monetary values before aggregating revenue.",
                    )
                )
        # Negative quantities are how almost every retail extract encodes a
        # return. Summing straight through them nets refunds against sales
        # without saying so, which is why they are reported here rather than
        # quietly cleaned away.
        if column.logical_type == "quantity" and series.dtype.is_numeric():
            negatives = int((series < 0).sum())
            if negatives:
                issues.append(
                    QualityIssue(
                        severity="medium",
                        issue_type="returns_present",
                        table_name=profile.name,
                        column_name=column.name,
                        rows_affected=negatives,
                        detection_method="negative quantity count",
                        recommended_action=(
                            "Treat these as returns. Report gross and net separately rather than "
                            "summing the column as if every line were a sale."
                        ),
                        evidence={
                            "negative_rows": negatives,
                            "share": round(negatives / rows, 6),
                        },
                    )
                )
        if column.stats.get("outlier_count_iqr"):
            count = int(column.stats["outlier_count_iqr"])
            issues.append(
                QualityIssue(
                    severity="low",
                    issue_type="outliers",
                    table_name=profile.name,
                    column_name=column.name,
                    rows_affected=count,
                    detection_method="IQR 1.5",
                    recommended_action="Do not drop automatically. Review distribution before filtering.",
                    evidence={"outlier_count": count},
                )
            )

    consistency = max(0, 100 - consistency_penalties)
    validity = max(0, 100 - validity_penalties)
    ref_issues = [i for i in issues if i.issue_type == "referential_integrity"]
    referential = 100.0 if not ref_issues else max(0, 100 - min(80, 15 * len(ref_issues)))
    overall = round(
        completeness * 0.3 + uniqueness * 0.2 + consistency * 0.2 + validity * 0.2 + referential * 0.1, 2
    )
    return QualityScorecard(
        overall=round(overall, 2),
        completeness=round(completeness, 2),
        uniqueness=round(uniqueness, 2),
        consistency=round(consistency, 2),
        validity=round(validity, 2),
        referential_integrity=round(referential, 2),
        issues=issues,
        table_name=profile.name,
    )


def _type_inference_issues(
    table_name: str, inference: SchemaInference | None
) -> list[QualityIssue]:
    """Surface what the loader could not type, and what typing cost.

    A date column that only 96% parses is a real data problem, and the run
    should say so rather than let the missing 4% look like absent records.
    """
    if inference is None:
        return []
    issues: list[QualityIssue] = []
    for column in inference.columns:
        if column.action == "parse_datetime" and (column.parse_rate or 1.0) < 1.0:
            issues.append(
                QualityIssue(
                    severity="high" if (column.parse_rate or 1) < 0.99 else "low",
                    issue_type="unparsed_dates",
                    table_name=table_name,
                    column_name=column.column,
                    rows_affected=0,
                    detection_method=f"date format inference ({column.format})",
                    recommended_action=(
                        "Check the source for mixed date formats. Unparsed values are null and "
                        "are excluded from every time series."
                    ),
                    evidence={
                        "format": column.format,
                        "parse_rate": column.parse_rate,
                        "rejected_candidates": column.rejected,
                    },
                )
            )
        if column.warnings and column.action == "keep" and column.parse_rate:
            issues.append(
                QualityIssue(
                    severity="low",
                    issue_type="ambiguous_type",
                    table_name=table_name,
                    column_name=column.column,
                    rows_affected=0,
                    detection_method="schema inference",
                    recommended_action="; ".join(column.warnings),
                    evidence={"parse_rate": column.parse_rate, "reason": column.reason},
                )
            )
        if column.action == "parse_datetime" and any(
            "Ambiguous date order" in warning for warning in column.warnings
        ):
            issues.append(
                QualityIssue(
                    severity="high",
                    issue_type="ambiguous_date_order",
                    table_name=table_name,
                    column_name=column.column,
                    rows_affected=0,
                    detection_method="day/month component analysis",
                    recommended_action=(
                        "Confirm the source's date convention. Every value fits both orderings, "
                        "so the chosen one cannot be proven from the data."
                    ),
                    evidence={"format": column.format, "rejected_candidates": column.rejected},
                )
            )
    return issues


def referential_issues(tables: dict[str, pl.DataFrame], joins) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for join in joins:
        if not join.validated:
            continue
        left = tables[join.source_table][join.source_column].drop_nulls()
        right = set(tables[join.target_table][join.target_column].drop_nulls().unique().to_list())
        orphans = [v for v in left.unique().to_list() if v not in right]
        # Bound cost
        if len(orphans) > 5000:
            orphan_count = int((1 - join.overlap_ratio) * left.n_unique())
        else:
            orphan_count = len(orphans)
        if orphan_count:
            issues.append(
                QualityIssue(
                    severity="medium" if orphan_count / max(left.n_unique(), 1) < 0.1 else "high",
                    issue_type="referential_integrity",
                    table_name=join.source_table,
                    column_name=join.source_column,
                    rows_affected=orphan_count,
                    detection_method="join overlap",
                    recommended_action=f"Investigate keys in {join.source_table}.{join.source_column} missing from {join.target_table}.{join.target_column}.",
                    evidence={
                        "target": f"{join.target_table}.{join.target_column}",
                        "overlap_ratio": join.overlap_ratio,
                    },
                )
            )
    return issues


def _example(series: pl.Series, predicate) -> str | None:
    for value in series.head(50).to_list():
        if value is not None and predicate(str(value)):
            return str(value)
    return None
