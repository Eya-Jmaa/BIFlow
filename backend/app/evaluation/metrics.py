"""Agent evaluation metrics.

These are the single definition of how each agent is scored. The pipeline calls
them at the end of a run and persists the results into ``evaluation_results``,
which is what the Audit / XAI screen and the exported evaluation report read.

Each function takes plain dicts rather than ORM objects so it can be tested
without a database, and so the same scoring can be applied to an exported run.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


def formula_validity(kpis: Sequence[Mapping[str, Any]]) -> float:
    """Share of KPIs whose formula compiled and executed.

    A KPI without SQL did not produce a number, however confident its name
    sounds, so it counts against the semantic agent.
    """
    if not kpis:
        return 0.0
    valid = sum(
        1 for kpi in kpis if kpi.get("validation_status") == "computed" and kpi.get("query_sql")
    )
    return valid / len(kpis)


def insight_groundedness(insights: Sequence[Mapping[str, Any]]) -> float:
    """Share of insights whose metric and value match a computed result.

    A run with no insights scores 1.0: saying nothing is not a hallucination.
    """
    if not insights:
        return 1.0
    return sum(1 for insight in insights if insight.get("grounded")) / len(insights)


def hallucination_rate(insights: Sequence[Mapping[str, Any]]) -> float:
    """The complement of groundedness, reported because it is what people ask for."""
    return 1.0 - insight_groundedness(insights)


def dashboard_validity(widgets: Sequence[Mapping[str, Any]]) -> float:
    """Share of widgets actually bound to a computed metric rather than empty."""
    if not widgets:
        return 0.0
    bound = sum(1 for widget in widgets if widget.get("query_sql") or widget.get("data"))
    return bound / len(widgets)


def type_inference_resolution(decisions: Sequence[Mapping[str, Any]]) -> float:
    """Share of columns given a concrete type instead of being left as text.

    Scored explicitly because silent type coercion is how a pipeline loses data
    without raising: a date column parsed at 43% looks like missing records.
    """
    if not decisions:
        return 0.0
    resolved = sum(
        1
        for decision in decisions
        if decision.get("action") != "keep" or decision.get("target_type") != "String"
    )
    return resolved / len(decisions)


def baseline_lift(catalog_kpis: int, baseline_kpis: int) -> float:
    """Catalog KPIs per KPI a naive script would produce.

    The baseline is one SUM or AVG per numeric column — what you get without a
    semantic layer. It cannot express row-level arithmetic, so it has no
    revenue, no average order value and no return rate at any count.
    """
    return catalog_kpis / max(baseline_kpis, 1)
