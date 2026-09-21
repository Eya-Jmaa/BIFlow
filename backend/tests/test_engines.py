from pathlib import Path

import polars as pl

from app.analytics.kpi_engine import compile_formula
from app.data.etl import execute_plan, plan_from_issues
from app.data.joins import discover_joins
from app.data.profiler import profile_frame
from app.data.quality import assess_quality
from app.security.sql import validate_readonly_sql
import pytest


def _orders() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "order_id": ["o1", "o2", "o3", "o3"],
            "customer_id": ["c1", "c2", "c1", "c1"],
            "order_date": ["2024-01-01", "2024-02-01", "2024-03-01", "2024-03-01"],
            "status": [" delivered", "shipped", "delivered", "delivered"],
            "amount": [10.0, 20.0, 30.0, 30.0],
        }
    )


def _customers() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "customer_id": ["c1", "c2"],
            "customer_city": [" Sao Paulo ", "Rio"],
        }
    )


def test_profiler_computes_real_stats():
    profile = profile_frame(_orders(), "orders")
    assert profile.row_count == 4
    amount = next(c for c in profile.columns if c.name == "amount")
    assert amount.stats["mean"] == 22.5
    assert amount.stats["min"] == 10.0
    assert profile.duplicate_row_count == 1


def test_quality_detects_whitespace_and_duplicates():
    frame = _orders()
    profile = profile_frame(frame, "orders")
    score = assess_quality(frame, profile)
    types = {i.issue_type for i in score.issues}
    assert "duplicates" in types
    assert "whitespace" in types
    assert 0 <= score.overall <= 100


def test_etl_trims_and_dedupes():
    tables = {"orders": _orders()}
    profile = profile_frame(tables["orders"], "orders")
    plan = plan_from_issues(assess_quality(tables["orders"], profile).issues)
    cleaned, results = execute_plan(tables, plan)
    assert any(r.operation == "trim_whitespace" for r in results)
    statuses = cleaned["orders"]["status"].to_list()
    assert " delivered" not in statuses
    assert "delivered" in statuses


def test_join_discovery_requires_overlap():
    joins = discover_joins({"orders": _orders(), "customers": _customers()}, min_overlap=0.5)
    customer_joins = [
        j
        for j in joins
        if j.source_column == "customer_id" and j.target_column == "customer_id"
    ]
    assert customer_joins
    assert customer_joins[0].validated
    assert customer_joins[0].overlap_ratio >= 0.5


def test_kpi_formula_compiles_and_executes():
    compiled = compile_formula("SUM(orders.amount) / COUNT_DISTINCT(orders.order_id)")
    import duckdb

    con = duckdb.connect()
    con.register("orders", _orders().to_arrow())
    value = con.execute(compiled.sql).fetchone()[0]
    assert value == 90.0 / 3


def test_sql_rejects_mutations():
    with pytest.raises(ValueError):
        validate_readonly_sql("DROP TABLE orders")
    with pytest.raises(ValueError):
        validate_readonly_sql("SELECT * FROM orders; DELETE FROM orders")
    assert "SELECT" in validate_readonly_sql("SELECT SUM(amount) FROM orders")


def test_second_schema_is_dataset_agnostic():
    retail = pl.DataFrame(
        {
            "invoice_id": ["A", "B", "C"],
            "stock_code": ["s1", "s1", "s2"],
            "quantity": [2, 5, 1],
            "unit_price": [3.5, 3.5, 10.0],
        }
    )
    profile = profile_frame(retail, "invoices")
    qty = next(c for c in profile.columns if c.name == "quantity")
    assert qty.logical_type in {"quantity", "numeric"}
    compiled = compile_formula("SUM(invoices.quantity)")
    import duckdb

    con = duckdb.connect()
    con.register("invoices", retail.to_arrow())
    assert con.execute(compiled.sql).fetchone()[0] == 8


def test_analytical_store_reads_parquet(tmp_path: Path):
    from app.data.store import AnalyticalStore

    frame = pl.DataFrame({"amount": [1.0, 2.0, 3.0]})
    frame.write_parquet(tmp_path / "orders.parquet")
    store = AnalyticalStore(tmp_path)
    result = store.query('SELECT SUM("orders"."amount") AS value FROM "orders"')
    assert float(result[0, 0]) == 6.0
    store.close()


def test_csv_adapter_reads_latin1(tmp_path: Path):
    from app.data.adapters.csv import CSVAdapter

    path = tmp_path / "data.csv"
    path.write_bytes("city,amount\nSão Paulo,10\n".encode("latin-1"))
    frame = CSVAdapter(path).load()
    assert frame.height == 1
    assert "city" in frame.columns
    assert frame["amount"].to_list()[0] == 10
