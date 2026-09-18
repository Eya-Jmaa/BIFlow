from __future__ import annotations

from typing import Any


def formula_validity(kpis: list[dict[str, Any]]) -> float:
    if not kpis:
        return 0.0
    valid = sum(1 for k in kpis if k.get("validation_status") == "computed" and k.get("query_sql"))
    return valid / len(kpis)


def insight_groundedness(insights: list[dict[str, Any]]) -> float:
    if not insights:
        return 1.0
    return sum(1 for i in insights if i.get("grounded")) / len(insights)


def hallucination_rate(insights: list[dict[str, Any]]) -> float:
    return 1.0 - insight_groundedness(insights)


def profiler_coverage(expected_tables: int, profiled_tables: int) -> float:
    if expected_tables <= 0:
        return 0.0
    return min(1.0, profiled_tables / expected_tables)


def dashboard_validity(widgets: list[dict[str, Any]]) -> float:
    if not widgets:
        return 0.0
    bound = sum(1 for w in widgets if w.get("query_sql") or w.get("data"))
    return bound / len(widgets)
