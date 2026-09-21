"""Regression tests against the real UCI Online Retail dataset.

Synthetic fixtures cannot catch what this file catches. Every defect these
tests pin was invisible on tidy test data and only appeared on 541,909 real
rows: a M/D/Y date column that a format guess destroyed, invoice numbers with
a letter prefix, negative quantities encoding returns, and a trailing month the
extract cuts off nine days in.

The dataset is not in the repository (it is large, and third-party licensed).
These tests skip when it is absent. To run them:

    python scripts/download_demo_data.py

Expected values were computed independently of this pipeline, directly from the
source file with Polars.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
import polars as pl
import pytest

from app.analytics.kpi_catalog import instantiate_catalog
from app.analytics.kpi_engine import compile_formula
from app.analytics.roles import bind_roles
from app.data.adapters.csv import CSVAdapter
from app.data.profiler import profile_frame

# Ground truth, derived from the source CSV, not from this code.
EXPECTED = {
    "rows": 541_909,
    "net_revenue": 9_747_747.93,
    "gross_revenue": 10_644_560.42,
    "returned_value": -896_812.49,
    "orders": 22_064,
    "cancelled_orders": 3_836,
    "unique_customers": 4_372,
    "average_order_value": 482.44,
    "first_date": "2010-12-01",
    "last_date": "2011-12-09",
    "negative_quantity_rows": 10_624,
    "cancellation_documents": 9_288,
}


def _locate() -> Path | None:
    override = os.environ.get("UCI_ONLINE_RETAIL_CSV")
    if override and Path(override).exists():
        return Path(override)
    root = Path(__file__).resolve().parents[2]
    # scripts/download_demo_data.py extracts an .xlsx from the UCI archive; a
    # manual export is usually .csv. Either is fine, the adapters handle both.
    for candidate in sorted(root.glob("data/raw/**/*.csv")) + sorted(
        root.glob("data/raw/**/*.xlsx")
    ):
        if candidate.suffix.lower() == ".xlsx":
            return candidate
        try:
            header = candidate.read_text(encoding="latin-1", errors="replace").split("\n", 1)[0]
        except OSError:
            continue
        if "InvoiceNo" in header and "UnitPrice" in header:
            return candidate
    return None


DATASET = _locate()
needs_dataset = pytest.mark.skipif(
    DATASET is None,
    reason="UCI Online Retail CSV not present; run scripts/download_demo_data.py",
)


@pytest.fixture(scope="module")
def loaded():
    frame, inference = CSVAdapter(DATASET, name="online_retail").load_with_inference()
    return frame, inference


@pytest.fixture(scope="module")
def catalog(loaded):
    frame, _inference = loaded
    profile = profile_frame(frame, "online_retail")
    binding = bind_roles({"online_retail": profile}, {"online_retail": frame})
    con = duckdb.connect()
    con.register("online_retail", frame.to_arrow())
    schema = {"online_retail": frame.columns}
    values = {}
    for kpi in instantiate_catalog(binding, "ecommerce"):
        compiled = compile_formula(kpi.formula, schema=schema)
        values[kpi.slug] = con.execute(compiled.sql).fetchone()[0]
    con.close()
    return values, binding


@needs_dataset
def test_the_whole_file_loads(loaded):
    frame, _inference = loaded
    assert frame.height == EXPECTED["rows"]


@needs_dataset
def test_no_date_is_lost_to_a_format_guess(loaded):
    """The original bug: 308,950 of 541,909 dates silently became null."""
    frame, inference = loaded
    dates = frame["InvoiceDate"]
    assert dates.null_count() == 0
    assert str(dates.min())[:10] == EXPECTED["first_date"]
    assert str(dates.max())[:10] == EXPECTED["last_date"]
    decision = inference.by_column("InvoiceDate")
    assert decision.action == "parse_datetime"
    assert decision.format == "%m/%d/%Y %H:%M"
    assert decision.parse_rate == 1.0


@needs_dataset
def test_cancellation_invoices_survive_loading(loaded):
    frame, _inference = loaded
    assert frame["InvoiceNo"].dtype == pl.String
    prefixed = frame.filter(pl.col("InvoiceNo").str.starts_with("C")).height
    assert prefixed == EXPECTED["cancellation_documents"]


@needs_dataset
def test_returns_are_detected_not_cleaned_away(catalog):
    _values, binding = catalog
    assert binding.returns.has_negative_quantity
    assert binding.returns.negative_quantity_rows == EXPECTED["negative_quantity_rows"]
    assert binding.returns.cancel_prefix == "C"


@needs_dataset
@pytest.mark.parametrize(
    "slug",
    ["net_revenue", "gross_revenue", "returned_value", "orders", "cancelled_orders",
     "unique_customers", "average_order_value"],
)
def test_headline_kpis_match_the_source_data(catalog, slug):
    values, _binding = catalog
    key = {"orders": "orders", "cancelled_orders": "cancelled_orders"}.get(slug, slug)
    actual = values["order_count" if slug == "orders" else slug]
    assert actual == pytest.approx(EXPECTED[key], rel=1e-6)


@needs_dataset
def test_revenue_is_not_the_sum_of_the_price_column(catalog, loaded):
    """Guards the specific wrong answer the previous grammar was forced into."""
    values, _binding = catalog
    frame, _inference = loaded
    sum_of_prices = frame["UnitPrice"].sum()
    assert values["net_revenue"] == pytest.approx(EXPECTED["net_revenue"], rel=1e-6)
    assert values["net_revenue"] > sum_of_prices * 3


@needs_dataset
def test_gross_and_returns_reconcile_to_net(catalog):
    values, _binding = catalog
    assert values["gross_revenue"] + values["returned_value"] == pytest.approx(
        values["net_revenue"], rel=1e-9
    )


@needs_dataset
def test_orders_and_cancellations_account_for_every_document(catalog, loaded):
    values, _binding = catalog
    frame, _inference = loaded
    assert values["order_count"] + values["cancelled_orders"] == frame["InvoiceNo"].n_unique()


@needs_dataset
def test_only_low_cardinality_dimensions_are_offered_for_charts(catalog):
    _values, binding = catalog
    names = {d.ref for d in binding.dimensions}
    # 25,900 invoices and 4,070 stock codes are keys, not chart axes.
    assert "online_retail.InvoiceNo" not in names
    assert "online_retail.StockCode" not in names
    assert "online_retail.Country" in names
