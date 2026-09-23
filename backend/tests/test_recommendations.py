"""Recommendation rules.

A recommendation is only defensible if it follows from a measured condition and
quotes the numbers behind it. These tests pin both halves: that a rule stays
silent when its threshold is not met, and that when it does fire the text
carries the figures it was derived from.
"""

from __future__ import annotations

import pytest

from app.analytics import recommendations as rec


class TestThresholds:
    """Below threshold, a rule says nothing rather than filling space."""

    def test_ordinary_distribution_is_not_a_concentration_risk(self):
        assert rec.concentration(segment="UK", share=0.3, metric="Revenue", segment_value=100) is None

    def test_dominant_segment_is(self):
        assert rec.concentration(segment="UK", share=0.85, metric="Revenue", segment_value=100) is not None

    def test_a_small_move_gets_no_action(self):
        assert (
            rec.adverse_move(
                metric="Revenue", change_pct=0.04, previous=100, current=104, period="Nov"
            )
            is None
        )

    def test_a_material_move_does(self):
        assert (
            rec.adverse_move(
                metric="Revenue", change_pct=-0.3, previous=100, current=70, period="Nov"
            )
            is not None
        )

    def test_weak_correlation_is_not_reported(self):
        assert rec.correlation(left="a", right="b", coefficient=0.2) is None
        assert rec.correlation(left="a", right="b", coefficient=-0.81) is not None

    def test_a_flat_series_gets_no_seasonality_advice(self):
        assert rec.seasonality(metric="Revenue", peak="Nov", trough="Feb", amplitude_pct=10) is None

    def test_a_negligible_return_rate_is_not_flagged(self):
        assert rec.return_rate(rate_pct=1.2, returned_value=-100) is None

    def test_pareto_needs_an_actual_concentration(self):
        # Every segment needed to reach 80% means there is no 80/20 to act on.
        assert rec.pareto(dimension="country", measure="revenue", cutoff=25, total_segments=25) is None
        assert rec.pareto(dimension="country", measure="revenue", cutoff=2, total_segments=25) is not None


class TestGrounding:
    """Firing rules quote the measurement, so the advice can be checked."""

    def test_concentration_quantifies_the_exposure(self):
        text, basis = rec.concentration(
            segment="United Kingdom", share=0.851, metric="Net Revenue", segment_value=8_167_128.18
        )
        assert "United Kingdom" in text
        assert "85.1%" in text
        # A 10% fall on 8.17M is ~817k; the rule must do that arithmetic.
        assert "816,713" in text
        assert basis.startswith("concentration")

    def test_adverse_move_states_both_endpoints(self):
        text, _ = rec.adverse_move(
            metric="Orders", change_pct=-0.25, previous=1000, current=750, period="2011-11"
        )
        assert "25.0%" in text and "1,000" in text and "750" in text and "2011-11" in text

    def test_anomaly_names_the_period_and_the_test(self):
        text, basis = rec.anomaly(
            metric="Net Revenue", period="2011-11", value=1_456_145.8, method="iqr", periods_tested=13
        )
        assert "2011-11" in text and "iqr" in text and "1,456,146" in text
        assert "12 periods" in text  # the other periods it was compared against
        assert basis == "iqr outlier"

    def test_return_rate_includes_the_value_at_stake(self):
        text, _ = rec.return_rate(rate_pct=14.8, returned_value=-893_979.73)
        assert "14.8%" in text and "893,980" in text

    def test_correlation_refuses_to_claim_causation(self):
        text, _ = rec.correlation(left="Quantity", right="UnitPrice", coefficient=-0.62)
        assert "not cause" in text or "association, not" in text


class TestAttach:
    def test_a_silent_rule_leaves_the_insight_untouched(self):
        from app.models import Insight

        insight = Insight(title="t", description="d", category="finding")
        rec.attach(insight, None)
        assert insight.recommendation is None
        assert insight.recommendation_basis is None

    def test_a_firing_rule_records_both_text_and_rule(self):
        from app.models import Insight

        insight = Insight(title="t", description="d", category="risk")
        rec.attach(insight, ("do the thing", "some rule"))
        assert insight.recommendation == "do the thing"
        assert insight.recommendation_basis == "some rule"
