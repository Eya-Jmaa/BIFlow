from app.evaluation.metrics import dashboard_validity, formula_validity, insight_groundedness


def test_formula_validity_metric():
    kpis = [
        {"validation_status": "computed", "query_sql": "SELECT 1"},
        {"validation_status": "invalid_formula", "query_sql": None},
    ]
    assert formula_validity(kpis) == 0.5


def test_insight_groundedness_metric():
    insights = [{"grounded": True}, {"grounded": True}, {"grounded": False}]
    assert abs(insight_groundedness(insights) - 2 / 3) < 1e-9


def test_dashboard_validity_metric():
    widgets = [{"query_sql": "SELECT 1"}, {"data": {"value": 3}}, {}]
    assert dashboard_validity(widgets) == 2 / 3
