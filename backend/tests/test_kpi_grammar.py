"""The KPI formula grammar and its safety properties.

The grammar previously accepted only ``AGG(table.column)``, which cannot
express revenue on a transaction table. ``SUM(unit_price)`` was published as
"Total Amount" -- the sum of price tags, four times smaller than the real
figure. These tests hold the line on both the expressiveness and the safety.
"""

from __future__ import annotations

import duckdb
import polars as pl
import pytest

from app.analytics.kpi_engine import FormulaError, compile_formula


def _sales() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "invoice_no": ["A1", "A1", "A2", "C3", "A4"],
            "customer_id": ["c1", "c1", "c2", "c1", None],
            "quantity": [2, 3, 10, -4, 5],
            "unit_price": [1.5, 2.0, 0.5, 2.0, 10.0],
            "country": ["UK", "UK", "France", "UK", "UK"],
        }
    )


def _run(formula: str, schema_check: bool = True) -> float | None:
    frame = _sales()
    schema = {"sales": frame.columns} if schema_check else None
    compiled = compile_formula(formula, schema=schema)
    con = duckdb.connect()
    con.register("sales", frame.to_arrow())
    try:
        return con.execute(compiled.sql).fetchone()[0]
    finally:
        con.close()


def test_revenue_multiplies_per_row_before_summing():
    # 2*1.5 + 3*2 + 10*0.5 + (-4)*2 + 5*10 = 3 + 6 + 5 - 8 + 50
    assert _run("SUM(sales.quantity * sales.unit_price)") == pytest.approx(56.0)


def test_summing_a_price_column_is_not_revenue():
    """The old grammar's only option, kept as a regression marker."""
    assert _run("SUM(sales.unit_price)") == pytest.approx(16.0)
    assert _run("SUM(sales.quantity * sales.unit_price)") != _run("SUM(sales.unit_price)")


def test_conditional_aggregation_filters_per_row():
    # Cancellations excluded: 3 + 6 + 5 + 50 = 64
    assert _run(
        "SUM(sales.quantity * sales.unit_price WHERE sales.invoice_no NOT LIKE 'C%')"
    ) == pytest.approx(64.0)
    # Returns only: -8
    assert _run(
        "SUM(sales.quantity * sales.unit_price WHERE sales.quantity < 0)"
    ) == pytest.approx(-8.0)


def test_gross_minus_returns_equals_net():
    net = _run("SUM(sales.quantity * sales.unit_price)")
    gross = _run("SUM(sales.quantity * sales.unit_price WHERE sales.quantity >= 0)")
    returned = _run("SUM(sales.quantity * sales.unit_price WHERE sales.quantity < 0)")
    assert gross + returned == pytest.approx(net)


def test_ratios_between_aggregates():
    # 64 / 3 distinct non-cancelled invoices
    value = _run(
        "SUM(sales.quantity * sales.unit_price WHERE sales.invoice_no NOT LIKE 'C%')"
        " / COUNT_DISTINCT(sales.invoice_no WHERE sales.invoice_no NOT LIKE 'C%')"
    )
    assert value == pytest.approx(64.0 / 3)


def test_count_star_and_distinct_ignore_nulls_like_sql():
    assert _run("COUNT(*)") == 5
    assert _run("COUNT_DISTINCT(sales.customer_id)") == 2  # NULL is not a value


def test_division_by_zero_yields_null_not_an_error():
    assert _run("SUM(sales.quantity) / COUNT_DISTINCT(sales.invoice_no WHERE sales.quantity > 999)") is None


def test_percentages_compose():
    value = _run(
        "COUNT_DISTINCT(sales.invoice_no WHERE sales.invoice_no LIKE 'C%')"
        " / COUNT_DISTINCT(sales.invoice_no) * 100"
    )
    assert value == pytest.approx(25.0)  # 1 of 4 distinct invoices


def test_additivity_is_classified_so_shares_are_only_claimed_where_they_mean_something():
    schema = {"sales": _sales().columns}
    assert compile_formula("SUM(sales.quantity)", schema=schema).additivity == "additive"
    assert compile_formula("COUNT(*)", schema=schema).additivity == "additive"
    assert (
        compile_formula("COUNT_DISTINCT(sales.customer_id)", schema=schema).additivity
        == "semi_additive"
    )
    # You cannot sum averages across segments.
    assert compile_formula("AVG(sales.unit_price)", schema=schema).additivity == "non_additive"
    assert (
        compile_formula(
            "SUM(sales.quantity) / COUNT_DISTINCT(sales.invoice_no)", schema=schema
        ).additivity
        == "non_additive"
    )


def test_grouped_sql_reuses_the_same_select_expression():
    """A breakdown must never drift from the headline number."""
    schema = {"sales": _sales().columns}
    compiled = compile_formula("SUM(sales.quantity * sales.unit_price)", schema=schema)
    grouped = compiled.grouped_sql('"sales"."country"', alias="dimension")
    assert compiled.select_expr in grouped

    con = duckdb.connect()
    con.register("sales", _sales().to_arrow())
    try:
        total = con.execute(compiled.sql).fetchone()[0]
        parts = con.execute(grouped).fetchall()
    finally:
        con.close()
    assert sum(value for _dimension, value in parts) == pytest.approx(total)


class TestRejection:
    """A hallucinated column must fail at compile time, not become a number."""

    @pytest.mark.parametrize(
        "formula",
        [
            "SUM(sales.revenue)",  # no such column
            "SUM(ghost.amount)",  # no such table
            "sales.quantity",  # not aggregated
            "AVG(SUM(sales.quantity))",  # nested aggregate
            "SUM(sales.quantity); DROP TABLE sales",  # statement injection
            "EXEC(sales.quantity)",  # unknown function
            "",  # empty
        ],
    )
    def test_invalid_formulas_raise(self, formula):
        with pytest.raises(FormulaError):
            compile_formula(formula, schema={"sales": _sales().columns})

    def test_a_quote_in_a_filter_value_is_escaped_not_executed(self):
        formula = "SUM(sales.quantity WHERE sales.country = 'x'') OR 1=1 --')"
        compiled = compile_formula(formula, schema={"sales": _sales().columns})
        con = duckdb.connect()
        con.register("sales", _sales().to_arrow())
        try:
            # The payload is compared as a literal country name; it matches nothing.
            assert con.execute(compiled.sql).fetchone()[0] is None
            assert con.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 5
        finally:
            con.close()


def test_multi_table_formulas_require_a_validated_join_path():
    schema = {"orders": ["id", "amount"], "customers": ["id", "city"]}
    with pytest.raises(FormulaError, match="join path"):
        compile_formula("SUM(orders.amount) / COUNT_DISTINCT(customers.id)", [], schema=schema)

    joins = [
        {
            "source_table": "orders",
            "source_column": "id",
            "target_table": "customers",
            "target_column": "id",
        }
    ]
    compiled = compile_formula(
        "SUM(orders.amount) / COUNT_DISTINCT(customers.id)", joins, schema=schema
    )
    assert "LEFT JOIN" in compiled.sql
