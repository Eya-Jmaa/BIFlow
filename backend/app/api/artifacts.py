from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.session import get_db
from app.models import (
    AnalysisResult,
    AuditEvent,
    DashboardDefinition,
    DataProfile,
    DataQualityReport,
    Dataset,
    Insight,
    KPI,
    KPIResult,
    PipelineRun,
    Project,
    SemanticModel,
    Transformation,
    XAIExplanation,
)
from app.schemas.api import DashboardOut, InsightOut, KPIOut, QualityReportOut

router = APIRouter()


def _latest_run(db: Session, project_id: UUID) -> PipelineRun:
    run = (
        db.query(PipelineRun)
        .filter(PipelineRun.project_id == project_id)
        .order_by(PipelineRun.created_at.desc())
        .first()
    )
    if not run:
        raise HTTPException(404, "No pipeline run found")
    return run


@router.get("/projects/{project_id}/quality", response_model=list[QualityReportOut])
def quality(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    return (
        db.query(DataQualityReport)
        .options(joinedload(DataQualityReport.issues))
        .filter(DataQualityReport.run_id == run.id)
        .all()
    )


@router.get("/projects/{project_id}/transformations")
def transformations(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    rows = db.query(Transformation).filter(Transformation.run_id == run.id).all()
    return [
        {
            "id": str(r.id),
            "table_name": r.table_name,
            "column_name": r.column_name,
            "operation": r.operation,
            "rows_affected": r.rows_affected,
            "reason": r.reason,
            "before_example": r.before_example,
            "after_example": r.after_example,
            "status": r.status,
        }
        for r in rows
    ]


@router.get("/projects/{project_id}/profile")
def profiles(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    rows = db.query(DataProfile).filter(DataProfile.run_id == run.id).all()
    payload = []
    for row in rows:
        dataset = db.get(Dataset, row.dataset_id)
        payload.append(
            {
                "id": str(row.id),
                "dataset": dataset.name if dataset else None,
                "table_name": dataset.table_name if dataset else None,
                "row_count": row.row_count,
                "column_count": row.column_count,
                "quality_score": row.quality_score,
                "duplicate_row_count": row.duplicate_row_count,
                "warnings": row.warnings,
                "pii_flags": row.pii_flags,
                "summary": row.summary,
                "columns": [
                    {
                        "name": c.name,
                        "inferred_type": c.inferred_type,
                        "logical_type": c.logical_type,
                        "null_pct": c.null_pct,
                        "distinct_count": c.distinct_count,
                        "uniqueness_pct": c.uniqueness_pct,
                        "is_candidate_pk": c.is_candidate_pk,
                        "semantic_hint": c.semantic_hint,
                        "stats": c.stats,
                        "warnings": c.warnings,
                    }
                    for c in row.columns
                ],
            }
        )
    return payload


@router.get("/projects/{project_id}/semantic-model")
def semantic(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    model = db.query(SemanticModel).filter(SemanticModel.run_id == run.id).first()
    if not model:
        raise HTTPException(404, "Semantic model not available yet")
    return {
        "id": str(model.id),
        "domain": model.domain,
        "summary": model.summary,
        "version": model.version,
        "dimensions": [
            {
                "name": d.name,
                "table_name": d.table_name,
                "column_name": d.column_name,
                "dim_type": d.dim_type,
                "grain": d.grain,
                "description": d.description,
            }
            for d in model.dimensions
        ],
        "measures": [
            {
                "name": m.name,
                "table_name": m.table_name,
                "column_name": m.column_name,
                "aggregation": m.aggregation,
                "unit": m.unit,
                "description": m.description,
            }
            for m in model.measures
        ],
        "relationships": [
            {
                "source_table": r.source_table,
                "source_column": r.source_column,
                "target_table": r.target_table,
                "target_column": r.target_column,
                "cardinality": r.cardinality,
                "confidence": r.confidence,
                "validated": r.validated,
                "overlap_ratio": r.overlap_ratio,
            }
            for r in model.relationships
        ],
    }


@router.get("/projects/{project_id}/kpis", response_model=list[KPIOut])
def kpis(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    rows = db.query(KPI).filter(KPI.run_id == run.id).all()
    out = []
    for kpi in rows:
        result = db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first()
        item = KPIOut.model_validate(kpi)
        if result:
            item.value = result.value
            item.previous_value = result.previous_value
            item.change_pct = result.change_pct
        out.append(item)
    return out


@router.get("/projects/{project_id}/kpis/{kpi_id}")
def kpi_detail(project_id: UUID, kpi_id: UUID, db: Session = Depends(get_db)):
    kpi = db.get(KPI, kpi_id)
    if not kpi:
        raise HTTPException(404, "KPI not found")
    result = db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first()
    explanation = (
        db.query(XAIExplanation)
        .filter(XAIExplanation.run_id == kpi.run_id, XAIExplanation.entity_id == str(kpi.id))
        .first()
    )
    return {
        "kpi": KPIOut.model_validate(kpi).model_dump(),
        "result": {
            "value": result.value if result else None,
            "previous_value": result.previous_value if result else None,
            "change_pct": result.change_pct if result else None,
            "query_sql": result.query_sql if result else kpi.query_sql,
            "breakdown": result.breakdown if result else [],
            "time_series": result.time_series if result else [],
            "status": result.status if result else kpi.validation_status,
        },
        "lineage": {
            "tables": kpi.data_sources,
            "formula": kpi.formula,
            "sql": kpi.query_sql,
            "run_id": str(kpi.run_id),
        },
        "explanation": None
        if explanation is None
        else {
            "what_happened": explanation.what_happened,
            "how_calculated": explanation.how_calculated,
            "data_used": explanation.data_used,
            "kpi_relevance": explanation.kpi_relevance,
            "assumptions": explanation.assumptions,
            "quality_limitations": explanation.quality_limitations,
            "producer_agent": explanation.producer_agent,
            "validator_agent": explanation.validator_agent,
        },
    }


@router.get("/projects/{project_id}/insights", response_model=list[InsightOut])
def insights(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    return db.query(Insight).filter(Insight.run_id == run.id).all()


@router.get("/projects/{project_id}/analysis")
def analysis(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    rows = db.query(AnalysisResult).filter(AnalysisResult.run_id == run.id).all()
    return [
        {"id": str(r.id), "analysis_type": r.analysis_type, "metric": r.metric, "details": r.details, "evidence": r.evidence}
        for r in rows
    ]


@router.get("/projects/{project_id}/dashboard", response_model=DashboardOut)
def dashboard(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    dash = (
        db.query(DashboardDefinition)
        .options(joinedload(DashboardDefinition.widgets))
        .filter(DashboardDefinition.run_id == run.id)
        .first()
    )
    if not dash:
        raise HTTPException(404, "Dashboard not available yet")
    return dash


@router.get("/projects/{project_id}/audit")
def audit(project_id: UUID, db: Session = Depends(get_db)):
    run = _latest_run(db, project_id)
    events = db.query(AuditEvent).filter(AuditEvent.run_id == run.id).all()
    explanations = db.query(XAIExplanation).filter(XAIExplanation.run_id == run.id).all()
    return {
        "run_id": str(run.id),
        "status": run.status,
        "events": [
            {
                "id": str(e.id),
                "event_type": e.event_type,
                "severity": e.severity,
                "message": e.message,
                "entity_type": e.entity_type,
                "status": e.status,
                "details": e.details,
            }
            for e in events
        ],
        "explanations": [
            {
                "id": str(x.id),
                "entity_type": x.entity_type,
                "entity_id": x.entity_id,
                "what_happened": x.what_happened,
                "how_calculated": x.how_calculated,
                "data_used": x.data_used,
                "visualization_reason": x.visualization_reason,
                "kpi_relevance": x.kpi_relevance,
                "assumptions": x.assumptions,
                "quality_limitations": x.quality_limitations,
                "transformations": x.transformations,
                "producer_agent": x.producer_agent,
                "validator_agent": x.validator_agent,
            }
            for x in explanations
        ],
    }


@router.get("/projects/{project_id}/lineage")
def lineage(project_id: UUID, db: Session = Depends(get_db)):
    from app.data.lineage import kpi_lineage
    from app.models import Transformation as T

    run = _latest_run(db, project_id)
    kpis = db.query(KPI).filter(KPI.run_id == run.id).all()
    transforms = [t.operation for t in db.query(T).filter(T.run_id == run.id).all()]
    graphs = []
    for kpi in kpis:
        graphs.append(
            kpi_lineage(
                run_id=str(run.id),
                kpi_name=kpi.name,
                formula=kpi.formula,
                query_sql=kpi.query_sql or "",
                tables=list(kpi.data_sources or []),
                columns=[],
                transformations=transforms,
            ).model_dump()
        )
    return {"run_id": str(run.id), "kpis": graphs}


@router.get("/projects/{project_id}/agent-runs")
def agent_runs(project_id: UUID, db: Session = Depends(get_db)):
    from app.models import AgentRun

    run = _latest_run(db, project_id)
    rows = db.query(AgentRun).filter(AgentRun.run_id == run.id).all()
    return [
        {
            "id": str(r.id),
            "agent_name": r.agent_name,
            "status": r.status,
            "started_at": r.started_at,
            "completed_at": r.completed_at,
            "llm_model": r.llm_model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "latency_ms": r.latency_ms,
            "retry_count": r.retry_count,
            "input_summary": r.input_summary,
            "output_summary": r.output_summary,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/projects/{project_id}/evaluation")
def evaluation(project_id: UUID, db: Session = Depends(get_db)):
    from app.models import EvaluationResult

    run = _latest_run(db, project_id)
    rows = db.query(EvaluationResult).filter(EvaluationResult.run_id == run.id).all()
    return [
        {"agent_name": r.agent_name, "metric_name": r.metric_name, "score": r.score, "details": r.details}
        for r in rows
    ]
