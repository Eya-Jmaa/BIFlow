"""Export completeness.

The brief lists the Data Quality Report, the KPI catalogue, the insights and
recommendations report, and the evaluation/XAI report as separate deliverables.
Each has to survive the trip out of the app, so these tests assert the report
payload actually carries them — a screen that shows a section is not the same
as a report that contains it.
"""

from __future__ import annotations

import datetime as dt
import io

import polars as pl
import pytest


@pytest.fixture
def exported(tmp_path, monkeypatch):
    """Run a real pipeline, then build the report from it."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'e.db').as_posix()}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_ENABLED", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    import sqlalchemy
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401
    from app.db.base import Base

    engine = sqlalchemy.create_engine(f"sqlite:///{(tmp_path / 'e.db').as_posix()}")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    rows = []
    for month in range(1, 13):
        for line in range(5):
            rows.append(
                {
                    "InvoiceNo": f"{month:02d}{line}",
                    "StockCode": f"S{line}",
                    "Quantity": 10 + line,
                    "InvoiceDate": dt.datetime(2011, month, 5, 10, 0).strftime("%m/%d/%Y %H:%M"),
                    "UnitPrice": 2.0,
                    "CustomerID": 1000 + line,
                    "Country": "UK" if line < 3 else "France",
                }
            )
    # A cancellation, so the returns path and its recommendation are exercised.
    rows.append(
        {
            "InvoiceNo": "C999",
            "StockCode": "S0",
            "Quantity": -5,
            "InvoiceDate": dt.datetime(2011, 6, 6, 10, 0).strftime("%m/%d/%Y %H:%M"),
            "UnitPrice": 2.0,
            "CustomerID": 1000,
            "Country": "UK",
        }
    )
    csv_path = tmp_path / "sales.csv"
    pl.DataFrame(rows).write_csv(csv_path)

    from app.models import Dataset, DatasetFile, Project

    project = Project(
        name="Export test", business_objective="Analyse sales revenue and customers.", status="draft"
    )
    db.add(project)
    db.flush()
    dataset = Dataset(
        project_id=project.id, name="sales", table_name="sales", source_type="csv", layer="raw"
    )
    db.add(dataset)
    db.flush()
    db.add(
        DatasetFile(
            dataset_id=dataset.id,
            filename="sales.csv",
            original_filename="sales.csv",
            storage_path=str(csv_path),
            size_bytes=csv_path.stat().st_size,
        )
    )
    db.commit()

    from app.agents.graph import invoke_pipeline
    from app.api.exports import build_report
    from app.pipeline.jobs import create_run

    run = create_run(db, project)
    invoke_pipeline(db, project.id, run.id)
    db.expire_all()

    report = build_report(db, project.id)
    yield report, db, project.id
    db.close()
    get_settings.cache_clear()


class TestDeliverablesPresent:
    def test_data_quality_report_is_included(self, exported):
        """Brief §10: 'Data Quality Report'."""
        report, _db, _pid = exported
        assert report["data_quality"], "no quality block in the export"
        block = report["data_quality"][0]
        assert block["overall_score"] is not None
        for axis in ("completeness", "uniqueness", "consistency", "validity", "referential_integrity"):
            assert block[axis] is not None, f"{axis} missing"
        assert isinstance(block["issues"], list)

    def test_kpi_catalogue_carries_formulas_and_sql(self, exported):
        """Brief §10: 'Catalogue des KPI et formules'."""
        report, _db, _pid = exported
        assert report["kpis"]
        computed = [k for k in report["kpis"] if k["status"] == "computed"]
        assert computed
        for kpi in computed:
            assert kpi["formula"], f"{kpi['name']} has no formula"
            assert kpi["sql"], f"{kpi['name']} has no SQL"
            assert kpi["business_meaning"]

    def test_insights_carry_recommendations(self, exported):
        """Brief §10: 'Rapport d'insights et recommandations'."""
        report, _db, _pid = exported
        assert report["insights"]
        actionable = [i for i in report["insights"] if i["recommendation"]]
        assert actionable, "no insight carried a recommendation"
        for insight in actionable:
            # Advice without a stated basis is not auditable.
            assert insight["recommendation_basis"]

    def test_evaluation_and_xai_are_included(self, exported):
        """Brief §10: 'Rapport d'évaluation et XAI'."""
        report, _db, _pid = exported
        assert report["evaluation"], "no per-agent evaluation in the export"
        metrics = {row["metric"] for row in report["evaluation"]}
        assert "vs_naive_baseline" in metrics, "baseline comparison missing (brief §9)"
        assert report["xai"], "no XAI explanations in the export"
        for explanation in report["xai"]:
            assert explanation["how_calculated"]
            assert explanation["producer_agent"] and explanation["validator_agent"]

    def test_transformation_lineage_is_included(self, exported):
        report, _db, _pid = exported
        assert isinstance(report["transformations"], list)

    def test_audit_verdict_is_included(self, exported):
        report, _db, _pid = exported
        assert report["audit"]["verdict"] is not None
        assert report["audit"]["verdict"]["status"]


class TestFormats:
    """Every format is built from the same report, so none can drift."""

    def _client(self, db, monkeypatch):
        from fastapi.testclient import TestClient

        from app.db.session import get_db
        from app.main import app

        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_json_is_the_full_report(self, exported, monkeypatch):
        report, db, pid = exported
        client = self._client(db, monkeypatch)
        payload = client.get(f"/api/projects/{pid}/export/json").json()
        assert set(payload) == set(report)

    def test_csv_carries_the_kpi_catalogue(self, exported, monkeypatch):
        report, db, pid = exported
        client = self._client(db, monkeypatch)
        response = client.get(f"/api/projects/{pid}/export/csv")
        assert response.status_code == 200
        text = response.content.decode("utf-8-sig")
        assert "formula" in text.splitlines()[0]
        assert len(text.strip().splitlines()) == len(report["kpis"]) + 1

    def test_xlsx_has_a_sheet_per_deliverable(self, exported, monkeypatch):
        _report, db, pid = exported
        client = self._client(db, monkeypatch)
        response = client.get(f"/api/projects/{pid}/export/xlsx")
        assert response.status_code == 200

        openpyxl = pytest.importorskip("openpyxl")
        workbook = openpyxl.load_workbook(io.BytesIO(response.content))
        assert {
            "KPI catalogue",
            "Data quality",
            "Insights",
            "Evaluation",
            "XAI",
        } <= set(workbook.sheetnames)

    def test_pdf_renders(self, exported, monkeypatch):
        _report, db, pid = exported
        client = self._client(db, monkeypatch)
        response = client.get(f"/api/projects/{pid}/export/pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")
        assert len(response.content) > 2000
