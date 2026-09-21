"""Agent evaluation metrics.

These back the Audit / XAI screen and the exported evaluation report, so they
are tested against plain dicts rather than a live run.
"""

from app.evaluation.metrics import (
    baseline_lift,
    dashboard_validity,
    formula_validity,
    hallucination_rate,
    insight_groundedness,
    type_inference_resolution,
)


def test_formula_validity_counts_only_kpis_that_produced_sql():
    kpis = [
        {"validation_status": "computed", "query_sql": "SELECT 1"},
        {"validation_status": "invalid_formula", "query_sql": None},
    ]
    assert formula_validity(kpis) == 0.5


def test_formula_validity_of_an_empty_catalog_is_zero():
    assert formula_validity([]) == 0.0


def test_insight_groundedness_metric():
    insights = [{"grounded": True}, {"grounded": True}, {"grounded": False}]
    assert abs(insight_groundedness(insights) - 2 / 3) < 1e-9
    assert abs(hallucination_rate(insights) - 1 / 3) < 1e-9


def test_saying_nothing_is_not_a_hallucination():
    assert insight_groundedness([]) == 1.0
    assert hallucination_rate([]) == 0.0


def test_dashboard_validity_metric():
    widgets = [{"query_sql": "SELECT 1"}, {"data": {"value": 3}}, {}]
    assert dashboard_validity(widgets) == 2 / 3


def test_type_inference_resolution_counts_columns_given_a_real_type():
    decisions = [
        {"action": "parse_datetime", "target_type": "Datetime"},
        {"action": "cast_numeric", "target_type": "Float64"},
        {"action": "keep", "target_type": "Int64"},  # already typed by the source
        {"action": "keep", "target_type": "String"},  # left as text
    ]
    assert type_inference_resolution(decisions) == 0.75
    assert type_inference_resolution([]) == 0.0


def test_baseline_lift_compares_catalog_against_a_naive_script():
    assert baseline_lift(catalog_kpis=14, baseline_kpis=3) > 4
    # No numeric columns must not divide by zero.
    assert baseline_lift(catalog_kpis=2, baseline_kpis=0) == 2
