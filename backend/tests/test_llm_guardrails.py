"""What happens to what the LLM says.

The pipeline's central claim is that an LLM never produces a number. It may
propose a KPI or phrase a finding, but the proposal is re-checked against the
real schema and the real computed values first. These tests drive that path
with a stub provider, so they run offline and no data leaves the machine.
"""

from __future__ import annotations

import pytest

from app.pipeline.executor import _insight_grounded


EVIDENCE = [
    {"kpi": "Net Revenue", "value": 9_747_747.93, "change_pct": 0.362},
    {"kpi": "Orders", "value": 22_064, "change_pct": 0.328},
    {"kpi": "Order Return Rate", "value": 0.0, "change_pct": None},
]


class TestInsightGrounding:
    def test_a_matching_claim_is_kept(self):
        assert _insight_grounded(
            {"metric": "Net Revenue", "value": 9_747_747.93, "title": "Revenue"}, EVIDENCE
        )

    def test_a_rounded_claim_is_kept(self):
        """Wording may round; 9.75M for 9,747,747.93 is the same number."""
        assert _insight_grounded({"metric": "Net Revenue", "value": 9_750_000}, EVIDENCE)

    def test_a_fabricated_value_is_rejected(self):
        assert not _insight_grounded({"metric": "Net Revenue", "value": 15_000_000}, EVIDENCE)

    def test_a_fabricated_metric_is_rejected(self):
        assert not _insight_grounded(
            {"metric": "Customer Lifetime Value", "value": 1234}, EVIDENCE
        )

    def test_a_claim_with_no_metric_is_rejected(self):
        assert not _insight_grounded({"title": "Things look good", "value": 1}, EVIDENCE)

    def test_a_zero_valued_metric_is_compared_exactly(self):
        assert _insight_grounded({"metric": "Order Return Rate", "value": 0.0}, EVIDENCE)
        assert not _insight_grounded({"metric": "Order Return Rate", "value": 5.0}, EVIDENCE)

    def test_a_qualitative_claim_about_a_real_metric_is_allowed(self):
        """No value to check means the wording is judged, not the arithmetic."""
        assert _insight_grounded({"metric": "Orders", "description": "Orders grew"}, EVIDENCE)


class TestProposedKPIs:
    """An LLM formula is compiled against the real schema before it is trusted."""

    @pytest.fixture
    def executor(self, monkeypatch):
        from app.pipeline.executor import PipelineExecutor

        instance = PipelineExecutor.__new__(PipelineExecutor)
        instance.run_id = "00000000-0000-0000-0000-000000000000"
        instance.tables = {
            "sales": __import__("polars").DataFrame(
                {"quantity": [1], "unit_price": [2.0], "invoice_no": ["A"]}
            )
        }
        monkeypatch.setattr(
            "app.pipeline.executor.publish_event", lambda *args, **kwargs: None
        )
        return instance

    def test_a_valid_proposal_is_accepted(self, executor):
        merged = executor._merge_llm_kpis(
            [],
            [
                {
                    "name": "Revenue",
                    "formula": "SUM(sales.quantity * sales.unit_price)",
                    "unit": "currency",
                }
            ],
        )
        assert [kpi.name for kpi in merged] == ["Revenue"]
        assert merged[0].source == "llm"

    def test_a_proposal_referencing_an_invented_column_is_dropped(self, executor):
        merged = executor._merge_llm_kpis(
            [], [{"name": "Margin", "formula": "SUM(sales.profit_margin)"}]
        )
        assert merged == []

    def test_a_proposal_that_is_not_valid_syntax_is_dropped(self, executor):
        merged = executor._merge_llm_kpis(
            [], [{"name": "Bad", "formula": "SELECT * FROM sales"}]
        )
        assert merged == []

    def test_catalog_kpis_are_never_replaced_by_proposals(self, executor):
        from app.analytics.kpi_catalog import InstantiatedKPI

        catalog = [
            InstantiatedKPI(
                slug="net_revenue",
                name="Revenue",
                description="d",
                business_meaning="m",
                formula="SUM(sales.quantity * sales.unit_price)",
                unit="currency",
                confidence=0.95,
                priority=1,
            )
        ]
        merged = executor._merge_llm_kpis(
            catalog,
            # Same formula, different framing: must not displace the catalog entry.
            [{"name": "LLM Revenue", "formula": "SUM(sales.quantity * sales.unit_price)"}],
        )
        assert len(merged) == 1
        assert merged[0].source == "catalog"


def test_no_llm_configured_still_produces_a_full_catalog():
    """The deterministic floor does not depend on a model being available."""
    import datetime as dt

    import polars as pl

    from app.analytics.kpi_catalog import instantiate_catalog
    from app.analytics.roles import bind_roles
    from app.data.profiler import profile_frame

    frame = pl.DataFrame(
        {
            "InvoiceNo": ["A1", "A2", "C3"],
            "Quantity": [5, 6, -1],
            "UnitPrice": [2.0, 3.0, 2.0],
            "CustomerID": [1, 2, 1],
            "InvoiceDate": [dt.datetime(2011, 1, 1)] * 3,
            "Country": ["UK", "UK", "FR"],
        }
    )
    binding = bind_roles({"sales": profile_frame(frame, "sales")}, {"sales": frame})
    slugs = {kpi.slug for kpi in instantiate_catalog(binding, "ecommerce")}
    assert {"net_revenue", "gross_revenue", "order_count", "average_order_value"} <= slugs
