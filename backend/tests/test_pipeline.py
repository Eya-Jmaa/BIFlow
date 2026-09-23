"""Semantic layer, analysis correctness and agent orchestration."""

from __future__ import annotations

import datetime as dt

import duckdb
import polars as pl
import pytest

from app.analytics.kpi_catalog import instantiate_catalog
from app.analytics.kpi_engine import compile_formula
from app.analytics.roles import bind_roles
from app.analytics.stats import seasonality
from app.data.profiler import profile_frame
from app.pipeline.executor import _complete_points, _is_partial_period, _rank_insights


def _retail() -> pl.DataFrame:
    """A retail extract shaped like the real thing: returns, cancellations, dates."""
    rows = []
    for month in range(1, 13):
        for line in range(4):
            rows.append(
                {
                    "InvoiceNo": f"{month:02d}{line}",
                    "StockCode": f"S{line}",
                    "Description": f"Item {line}",
                    "Quantity": 10 + line,
                    "InvoiceDate": dt.datetime(2011, month, 5, 10, 0),
                    "UnitPrice": 2.0,
                    "CustomerID": 1000 + line,
                    "Country": "UK" if line < 3 else "France",
                }
            )
    # One cancellation document with a negative quantity.
    rows.append(
        {
            "InvoiceNo": "C999",
            "StockCode": "S0",
            "Description": "Item 0",
            "Quantity": -5,
            "InvoiceDate": dt.datetime(2011, 6, 6, 10, 0),
            "UnitPrice": 2.0,
            "CustomerID": 1000,
            "Country": "UK",
        }
    )
    return pl.DataFrame(rows)


@pytest.fixture
def binding():
    frame = _retail()
    return bind_roles({"sales": profile_frame(frame, "sales")}, {"sales": frame}), frame


class TestRoleBinding:
    def test_business_roles_are_bound_from_the_profile(self, binding):
        bound, _frame = binding
        assert bound.ref("quantity") == "sales.Quantity"
        assert bound.ref("unit_price") == "sales.UnitPrice"
        assert bound.ref("order_id") == "sales.InvoiceNo"
        assert bound.ref("customer_id") == "sales.CustomerID"
        assert bound.ref("event_date") == "sales.InvoiceDate"
        assert bound.ref("geo") == "sales.Country"

    def test_both_return_conventions_are_detected(self, binding):
        bound, _frame = binding
        assert bound.returns.detected
        assert bound.returns.has_negative_quantity
        assert bound.returns.cancel_prefix == "C"

    def test_high_cardinality_columns_are_not_offered_as_chart_dimensions(self, binding):
        bound, _frame = binding
        names = {d.ref for d in bound.dimensions}
        # 49 distinct invoice numbers in 49 rows is a key, not an axis.
        assert "sales.InvoiceNo" not in names
        assert "sales.Country" in names


class TestCatalog:
    def _values(self, bound, frame) -> dict[str, float]:
        con = duckdb.connect()
        con.register("sales", frame.to_arrow())
        schema = {"sales": frame.columns}
        try:
            return {
                kpi.slug: con.execute(compile_formula(kpi.formula, schema=schema).sql).fetchone()[0]
                for kpi in instantiate_catalog(bound, "ecommerce")
            }
        finally:
            con.close()

    def test_revenue_is_quantity_times_price(self, binding):
        bound, frame = binding
        values = self._values(bound, frame)
        expected = (frame["Quantity"] * frame["UnitPrice"]).sum()
        assert values["net_revenue"] == pytest.approx(expected)

    def test_gross_minus_returns_reconciles_to_net(self, binding):
        bound, frame = binding
        values = self._values(bound, frame)
        assert values["gross_revenue"] + values["returned_value"] == pytest.approx(
            values["net_revenue"]
        )

    def test_orders_exclude_cancellation_documents(self, binding):
        bound, frame = binding
        values = self._values(bound, frame)
        assert values["order_count"] + values["cancelled_orders"] == frame["InvoiceNo"].n_unique()
        assert values["cancelled_orders"] == 1

    def test_average_order_value_uses_matching_numerator_and_denominator(self, binding):
        bound, frame = binding
        values = self._values(bound, frame)
        assert values["average_order_value"] == pytest.approx(
            values["gross_revenue"] / values["order_count"]
        )

    def test_a_template_without_its_roles_produces_nothing(self):
        """No cost column means no margin KPI, rather than an invented one."""
        frame = _retail()
        bound = bind_roles({"sales": profile_frame(frame, "sales")}, {"sales": frame})
        slugs = {kpi.slug for kpi in instantiate_catalog(bound, "ecommerce")}
        assert "gross_margin" not in slugs
        assert "net_revenue" in slugs

    def test_every_catalog_formula_compiles_against_the_real_schema(self, binding):
        bound, frame = binding
        schema = {"sales": frame.columns}
        for kpi in instantiate_catalog(bound, "ecommerce"):
            compile_formula(kpi.formula, schema=schema)  # raises on any bad reference


class TestPartialPeriods:
    """A truncated final period must never be compared against a full one."""

    def test_a_period_the_data_stops_inside_is_flagged(self):
        last_row = dt.datetime(2011, 12, 9)
        assert _is_partial_period(dt.datetime(2011, 12, 1), "month", last_row) is True
        assert _is_partial_period(dt.datetime(2011, 11, 1), "month", last_row) is False

    def test_a_period_the_data_covers_fully_is_not_flagged(self):
        assert _is_partial_period(dt.datetime(2011, 12, 1), "month", dt.datetime(2011, 12, 31)) is False

    def test_comparisons_use_only_complete_points(self):
        series = [
            {"period": "2011-10-01", "value": 100.0, "partial": False},
            {"period": "2011-11-01", "value": 120.0, "partial": False},
            {"period": "2011-12-01", "value": 12.0, "partial": True},
        ]
        complete = _complete_points(series)
        assert [point["period"] for point in complete] == ["2011-10-01", "2011-11-01"]
        change = (complete[-1]["value"] - complete[-2]["value"]) / complete[-2]["value"]
        assert change == pytest.approx(0.2)  # +20%, not the -90% the stub month implies

    def test_seasonality_ignores_a_truncated_tail(self):
        series = [{"period": f"2011-{m:02d}", "value": 100.0 + m} for m in range(1, 12)]
        result = seasonality(series)
        assert result is not None
        assert result["peak_period"] == "2011-11"


class TestInsightRanking:
    def _insight(self, **kwargs):
        from app.models import Insight

        defaults = dict(
            title="t",
            description="d",
            category="finding",
            severity="info",
            confidence=0.5,
            metric="m",
            grounded=True,
        )
        return Insight(**{**defaults, **kwargs})

    def test_severe_findings_outrank_routine_ones(self):
        routine = self._insight(title="routine", category="finding", severity="info")
        severe = self._insight(title="severe", category="risk", severity="warning", confidence=0.9)
        ranked = _rank_insights([routine, severe])
        assert ranked[0].title == "severe"

    def test_one_noisy_metric_cannot_crowd_out_the_rest(self):
        noisy = [
            self._insight(title=f"noisy {i}", metric="same", category="risk", severity="warning")
            for i in range(10)
        ]
        other = self._insight(title="other metric", metric="different", category="finding")
        ranked = _rank_insights([*noisy, other])
        assert sum(1 for i in ranked if i.metric == "same") <= 3
        assert any(i.metric == "different" for i in ranked)

    def test_duplicate_titles_are_collapsed(self):
        pair = [self._insight(title="Same title", metric=f"m{i}") for i in range(2)]
        assert len(_rank_insights(pair)) == 1


class TestDtypeHandling:
    """Polars parametrises some dtypes; identity against a set silently fails.

    ``Datetime(time_unit="us")`` is not ``pl.Datetime``, so a `dtype in {...}`
    check sent every datetime column down the categorical branch. Date ranges
    and grain were never computed, and the semantic model's grain was always
    None as a result.
    """

    def test_datetime_columns_get_a_range_and_grain(self):
        frame = pl.DataFrame(
            {"ordered_at": [dt.datetime(2011, 1, 5), dt.datetime(2011, 6, 5), dt.datetime(2011, 12, 9)]}
        )
        column = profile_frame(frame, "t").columns[0]
        assert column.logical_type == "datetime"
        assert "min_date" in column.stats and "max_date" in column.stats
        assert column.stats["granularity"] != "unknown"
        # The categorical fallback must not have fired.
        assert "top_values" not in column.stats

    def test_numeric_columns_still_get_quantiles(self):
        frame = pl.DataFrame({"amount": [1.0, 2.0, 3.0, 4.0, 100.0]})
        column = profile_frame(frame, "t").columns[0]
        assert {"q25", "median", "q75", "min", "max"} <= set(column.stats)

    def test_a_date_typed_column_is_temporal_too(self):
        frame = pl.DataFrame({"day": [dt.date(2011, 1, 5), dt.date(2011, 2, 5)]})
        column = profile_frame(frame, "t").columns[0]
        assert column.logical_type == "datetime"
        assert "min_date" in column.stats
