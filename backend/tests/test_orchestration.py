"""The multi-agent graph: routing, bounded retries, idempotency.

These run the whole pipeline against a temporary SQLite database, so they
exercise the real agents, the real DuckDB execution and the real persistence
rather than mocks. The earlier design could not be tested this way at all: the
"graph" was dead code and the agents were seven sequential calls in a `try`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import polars as pl
import pytest


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    """A project with one real dataset, wired to a throwaway database."""
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LLM_ENABLED", "false")

    from app.config import get_settings

    get_settings.cache_clear()

    import sqlalchemy
    from sqlalchemy.orm import sessionmaker

    import app.models  # noqa: F401  (registers mappers)
    from app.db.base import Base

    engine = sqlalchemy.create_engine(f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()

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
    csv_path = tmp_path / "sales.csv"
    pl.DataFrame(rows).write_csv(csv_path)

    from app.models import Dataset, DatasetFile, Project

    project = Project(
        name="Test", business_objective="Analyse sales revenue and customers.", status="draft"
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
    yield db, project
    db.close()
    get_settings.cache_clear()


def _run(db, project):
    from app.agents.graph import invoke_pipeline
    from app.pipeline.jobs import create_run

    run = create_run(db, project)
    invoke_pipeline(db, project.id, run.id)
    db.expire_all()
    return run


def _agent_sequence(db, run_id) -> list[str]:
    from app.models import AgentRun

    return [
        agent.agent_name
        for agent in db.query(AgentRun)
        .filter(AgentRun.run_id == run_id)
        .order_by(AgentRun.started_at, AgentRun.retry_count)
        .all()
    ]


def test_a_clean_run_visits_every_agent_once_in_order(pipeline):
    db, project = pipeline
    run = _run(db, project)

    from app.models import PipelineRun

    assert db.get(PipelineRun, run.id).status == "completed"
    assert _agent_sequence(db, run.id) == [
        "orchestrator",
        "profiler",
        "quality",
        "semantic",
        "analyst",
        "dashboard",
        "auditor",
    ]


def test_a_clean_run_publishes_computed_kpis_and_a_dashboard(pipeline):
    db, project = pipeline
    run = _run(db, project)

    from app.models import AuditEvent, DashboardDefinition, Insight, KPI

    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    assert kpis, "the catalog produced no KPIs"
    assert all(kpi.validation_status == "computed" for kpi in kpis)
    assert {"net_revenue", "order_count", "average_order_value"} <= {k.slug for k in kpis}

    dashboard = db.query(DashboardDefinition).filter(DashboardDefinition.run_id == run.id).one()
    assert dashboard.published and dashboard.audit_status == "VALID"
    assert db.query(Insight).filter(Insight.run_id == run.id).count() > 0

    verdict = (
        db.query(AuditEvent)
        .filter(AuditEvent.run_id == run.id, AuditEvent.event_type == "run_verdict")
        .one()
    )
    assert verdict.status == "VALID"


def test_revenue_is_computed_from_row_level_arithmetic(pipeline):
    db, project = pipeline
    run = _run(db, project)

    from app.models import KPI, KPIResult

    revenue = db.query(KPI).filter(KPI.run_id == run.id, KPI.slug == "net_revenue").one()
    result = db.query(KPIResult).filter(KPIResult.kpi_id == revenue.id).one()
    # 12 months x (10+11+12+13+14 units) x 2.0
    assert result.value == pytest.approx(12 * 60 * 2.0)
    assert "*" in revenue.formula


def test_the_auditor_can_send_the_run_back_and_the_budget_ends_it(pipeline, monkeypatch):
    """The feedback edge is the difference between a graph and a script."""
    db, project = pipeline
    import app.pipeline.executor as executor

    # Demand a success ratio no run can reach, so the auditor always rejects.
    monkeypatch.setattr(executor, "MIN_KPI_SUCCESS_RATIO", 1.5)
    run = _run(db, project)

    sequence = _agent_sequence(db, run.id)
    assert sequence.count("auditor") > 1, "the auditor never re-ran, so no feedback edge fired"
    assert sequence.count("semantic") > 1, "the run was not routed back to the semantic agent"

    from app.config import get_settings
    from app.models import PipelineRun

    budget = get_settings().pipeline_max_retries
    assert sequence.count("semantic") == budget + 1, "the retry budget was not respected"
    # It terminates rather than looping, and says why it published anyway.
    assert db.get(PipelineRun, run.id).status == "completed"


def test_reruns_inside_one_run_do_not_duplicate_artefacts(pipeline, monkeypatch):
    db, project = pipeline
    import app.pipeline.executor as executor

    monkeypatch.setattr(executor, "MIN_KPI_SUCCESS_RATIO", 1.5)
    run = _run(db, project)

    from app.models import DashboardDefinition, KPI, SemanticModel

    # The semantic agent ran three times; each cleared its own output first.
    assert db.query(SemanticModel).filter(SemanticModel.run_id == run.id).count() == 1
    assert db.query(DashboardDefinition).filter(DashboardDefinition.run_id == run.id).count() == 1
    slugs = [k.slug for k in db.query(KPI).filter(KPI.run_id == run.id).all()]
    assert len(slugs) == len(set(slugs)), "a retry duplicated the KPI catalog"


def test_type_inference_and_baseline_comparison_are_scored(pipeline):
    db, project = pipeline
    run = _run(db, project)

    from app.models import EvaluationResult

    scores = {
        row.metric_name: row
        for row in db.query(EvaluationResult).filter(EvaluationResult.run_id == run.id).all()
    }
    assert scores["kpi_formula_validity"].score == 1.0
    assert scores["type_inference_resolution"].score > 0
    baseline = scores["vs_naive_baseline"]
    assert baseline.details["baseline_kpis"] >= 1
    assert baseline.details["catalog_kpis"] >= 1


def test_the_date_column_survives_loading(pipeline):
    """The regression that motivated most of this file."""
    db, project = pipeline
    run = _run(db, project)

    from app.models import DataProfile, DataProfileColumn

    profile = db.query(DataProfile).filter(DataProfile.run_id == run.id).one()
    column = (
        db.query(DataProfileColumn)
        .filter(DataProfileColumn.profile_id == profile.id, DataProfileColumn.name == "InvoiceDate")
        .one()
    )
    assert column.logical_type == "datetime"
    assert column.null_pct == 0.0
    assert column.stats["type_inference"]["parse_rate"] == 1.0
