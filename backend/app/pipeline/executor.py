from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from uuid import UUID

import polars as pl
from sqlalchemy.orm import Session

from app.agents.llm_support import (
    interpret_analyst,
    interpret_auditor,
    interpret_dashboard,
    interpret_orchestrator,
    interpret_profiler,
    interpret_quality,
    interpret_semantic,
)
from app.analytics.kpi_engine import FormulaError, compile_formula
from app.analytics.stats import concentration, correlation_matrix, iqr_outliers, linear_trend, pareto, period_change, zscore_anomalies
from app.config import get_settings
from app.data.etl import execute_plan, plan_from_issues
from app.data.joins import discover_joins
from app.data.pii import detect_pii
from app.data.profiler import TableProfile, profile_frame
from app.data.quality import QualityIssue, assess_quality, referential_issues
from app.data.store import AnalyticalStore
from app.domains.profiles import get_domain, infer_domain
from app.logging import get_logger
from app.models import (
    AnalysisResult,
    AuditEvent,
    DashboardDefinition,
    DashboardWidget,
    DataProfile,
    DataProfileColumn,
    DataQualityIssue,
    DataQualityReport,
    Dataset,
    DatasetFile,
    Dimension,
    EvaluationResult,
    Insight,
    KPI,
    KPIResult,
    Measure,
    Relationship,
    SemanticModel,
    Transformation,
    XAIExplanation,
)
from app.pipeline.events import publish_event

logger = get_logger(service="pipeline")

STEP_SEQUENCE = [
    ("orchestrator", "BI Orchestrator"),
    ("profiler", "Data Profiler"),
    ("quality", "Data Quality / ETL"),
    ("semantic", "Semantic / KPI"),
    ("analyst", "BI Analyst"),
    ("dashboard", "Dashboard Generator"),
    ("auditor", "BI Auditor / XAI"),
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:80]


def load_project_tables(db: Session, project_id: UUID) -> dict[str, tuple[Dataset, pl.DataFrame, Path]]:
    from app.data.adapters import adapter_for_file

    datasets = db.query(Dataset).filter(Dataset.project_id == project_id, Dataset.layer == "raw").all()
    loaded: dict[str, tuple[Dataset, pl.DataFrame, Path]] = {}
    for dataset in datasets:
        file = db.query(DatasetFile).filter(DatasetFile.dataset_id == dataset.id).first()
        if not file:
            continue
        adapter = adapter_for_file(file.storage_path, name=dataset.table_name)
        frame = adapter.load()
        loaded[dataset.table_name] = (dataset, frame, Path(file.storage_path))
    return loaded


def persist_parquet(run_id: UUID, tables: dict[str, pl.DataFrame]) -> Path:
    settings = get_settings()
    out = settings.processed_dir / str(run_id)
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.write_parquet(out / f"{name}.parquet")
    return out


class PipelineExecutor:
    def __init__(self, db: Session, project_id: UUID, run_id: UUID):
        from app.models import PipelineRun, Project

        self.db = db
        self.project_id = project_id
        self.run_id = run_id
        self.project = db.get(Project, project_id)
        self.run = db.get(PipelineRun, run_id)
        self.tables: dict[str, pl.DataFrame] = {}
        self.raw_tables: dict[str, pl.DataFrame] = {}
        self.dataset_map: dict[str, Dataset] = {}
        self.profiles: dict[str, TableProfile] = {}
        self.joins = []
        self.parquet_dir: Path | None = None

    def execute(self) -> None:
        from datetime import datetime, timezone

        self.run.status = "running"
        self.run.started_at = datetime.now(timezone.utc)
        self.db.commit()
        publish_event(str(self.run_id), "pipeline.started", {"project_id": str(self.project_id)})
        try:
            loaded = load_project_tables(self.db, self.project_id)
            if not loaded:
                raise RuntimeError("No datasets uploaded for this project")
            for name, (dataset, frame, _) in loaded.items():
                self.tables[name] = frame
                self.raw_tables[name] = frame
                self.dataset_map[name] = dataset
            self._orchestrator()
            self._profiler()
            self._quality()
            self._semantic()
            self._analyst()
            self._dashboard()
            self._auditor()
            self._evaluate()
            self.run.status = "completed"
            self.run.completed_at = datetime.now(timezone.utc)
            self.run.current_step = "completed"
            self.db.commit()
            publish_event(str(self.run_id), "pipeline.completed", {"status": "completed"})
        except Exception as exc:
            logger.exception("pipeline_failed", run_id=str(self.run_id), error=str(exc))
            self.run.status = "failed"
            self.run.error = str(exc)
            self.run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            publish_event(str(self.run_id), "pipeline.failed", {"error": str(exc)})
            raise

    def _step(self, name: str, fn):
        from datetime import datetime, timezone

        from app.models import AgentRun, PipelineStep

        step = (
            self.db.query(PipelineStep)
            .filter(PipelineStep.run_id == self.run_id, PipelineStep.name == name)
            .one()
        )
        step.status = "running"
        step.started_at = datetime.now(timezone.utc)
        self.run.current_step = name
        self.db.commit()
        publish_event(str(self.run_id), "agent.started", {"agent": name})
        agent = AgentRun(
            run_id=self.run_id,
            step_id=step.id,
            agent_name=name,
            status="running",
            started_at=step.started_at,
        )
        self.db.add(agent)
        self.db.commit()
        try:
            summary = fn()
            ended = datetime.now(timezone.utc)
            step.status = "completed"
            step.completed_at = ended
            step.duration_ms = int((ended - step.started_at).total_seconds() * 1000)
            step.output_summary = summary or {}
            agent.status = "completed"
            agent.completed_at = ended
            agent.latency_ms = step.duration_ms
            agent.output_summary = summary or {}
            llm_meta = (summary or {}).get("llm") or {}
            agent.llm_model = llm_meta.get("model")
            agent.prompt_tokens = llm_meta.get("prompt_tokens")
            agent.completion_tokens = llm_meta.get("completion_tokens")
            self.db.commit()
            publish_event(str(self.run_id), "agent.completed", {"agent": name, "summary": summary})
            return summary
        except Exception as exc:
            ended = datetime.now(timezone.utc)
            step.status = "failed"
            step.error = str(exc)
            step.completed_at = ended
            agent.status = "failed"
            agent.error = str(exc)
            agent.completed_at = ended
            self.db.commit()
            publish_event(str(self.run_id), "agent.failed", {"agent": name, "error": str(exc)})
            raise

    def _orchestrator(self):
        def run():
            columns = [c for frame in self.tables.values() for c in frame.columns]
            domain = infer_domain(self.project.business_objective, columns)
            self.project.domain = domain
            interpretation = interpret_orchestrator(
                {
                    "objective": self.project.business_objective,
                    "tables": {name: list(frame.columns) for name, frame in self.tables.items()},
                    "row_counts": {name: frame.height for name, frame in self.tables.items()},
                }
            )
            self.run.configuration = {
                "domain": domain,
                "table_count": len(self.tables),
                "plan": (interpretation or {}).get("plan_summary"),
            }
            return {
                "domain": domain,
                "tables": list(self.tables),
                "rows": {n: f.height for n, f in self.tables.items()},
                "llm": (interpretation or {}).get("_llm"),
            }

        return self._step("orchestrator", run)

    def _profiler(self):
        def run():
            all_pii = []
            compact_profiles = []
            for name, frame in self.tables.items():
                profile = profile_frame(frame, name)
                self.profiles[name] = profile
                pii = detect_pii(frame, name)
                all_pii.extend(pii)
                dataset = self.dataset_map[name]
                dataset.row_count = profile.row_count
                dataset.column_count = profile.column_count
                row = DataProfile(
                    dataset_id=dataset.id,
                    run_id=self.run_id,
                    row_count=profile.row_count,
                    column_count=profile.column_count,
                    quality_score=profile.quality_score,
                    duplicate_row_count=profile.duplicate_row_count,
                    warnings=profile.warnings,
                    pii_flags=pii,
                )
                self.db.add(row)
                self.db.flush()
                for col in profile.columns:
                    self.db.add(
                        DataProfileColumn(
                            profile_id=row.id,
                            name=col.name,
                            inferred_type=col.inferred_type,
                            logical_type=col.logical_type,
                            null_count=col.null_count,
                            null_pct=col.null_pct,
                            distinct_count=col.distinct_count,
                            uniqueness_pct=col.uniqueness_pct,
                            is_candidate_pk=col.is_candidate_pk,
                            is_candidate_fk=col.is_candidate_fk,
                            semantic_hint=col.semantic_hint,
                            stats=col.stats,
                            warnings=col.warnings,
                        )
                    )
                compact_profiles.append(profile.model_dump())
            self.joins = discover_joins(self.tables)
            interpretation = interpret_profiler(
                {
                    "profiles": [
                        {
                            "name": p["name"],
                            "row_count": p["row_count"],
                            "column_count": p["column_count"],
                            "quality_score": p["quality_score"],
                            "warnings": p["warnings"],
                            "columns": [
                                {
                                    "name": c["name"],
                                    "logical_type": c["logical_type"],
                                    "null_pct": c["null_pct"],
                                    "distinct_count": c["distinct_count"],
                                    "semantic_hint": c["semantic_hint"],
                                }
                                for c in p["columns"]
                            ],
                        }
                        for p in compact_profiles
                    ],
                    "joins": [j.model_dump() for j in self.joins[:20]],
                    "pii": all_pii,
                }
            )
            if interpretation:
                for name, profile_row in [(p["name"], None) for p in compact_profiles]:
                    rec = (
                        self.db.query(DataProfile)
                        .filter(DataProfile.run_id == self.run_id)
                        .all()
                    )
                    for item in rec:
                        if item.summary is None:
                            item.summary = interpretation.get("summary")
                            break
            return {
                "tables": len(self.tables),
                "rows": sum(p.row_count for p in self.profiles.values()),
                "joins": len(self.joins),
                "pii_flags": len(all_pii),
                "llm": (interpretation or {}).get("_llm"),
            }

        return self._step("profiler", run)

    def _quality(self):
        def run():
            all_issues: list[QualityIssue] = referential_issues(self.tables, self.joins)
            reports = []
            for name, frame in self.tables.items():
                scorecard = assess_quality(frame, self.profiles[name], join_issues=[i for i in all_issues if i.table_name == name])
                reports.append(scorecard)
                dataset = self.dataset_map[name]
                report = DataQualityReport(
                    run_id=self.run_id,
                    dataset_id=dataset.id,
                    overall_score=scorecard.overall,
                    completeness=scorecard.completeness,
                    uniqueness=scorecard.uniqueness,
                    consistency=scorecard.consistency,
                    validity=scorecard.validity,
                    referential_integrity=scorecard.referential_integrity,
                    summary=f"Overall {scorecard.overall}",
                )
                self.db.add(report)
                self.db.flush()
                for issue in scorecard.issues:
                    self.db.add(
                        DataQualityIssue(
                            report_id=report.id,
                            severity=issue.severity,
                            issue_type=issue.issue_type,
                            table_name=issue.table_name,
                            column_name=issue.column_name,
                            rows_affected=issue.rows_affected,
                            detection_method=issue.detection_method,
                            recommended_action=issue.recommended_action,
                            evidence=issue.evidence,
                            status="open",
                        )
                    )
                    publish_event(
                        str(self.run_id),
                        "quality.issue_detected",
                        {"table": issue.table_name, "type": issue.issue_type, "rows": issue.rows_affected},
                    )
            combined_issues = [issue for report in reports for issue in report.issues]
            plan = plan_from_issues(combined_issues)
            interpretation = interpret_quality(
                {
                    "issues": [i.model_dump() for i in combined_issues[:80]],
                    "proposed_plan": plan.model_dump(),
                }
            )
            cleaned, results = execute_plan(self.tables, plan)
            self.tables = cleaned
            for result in results:
                dataset = self.dataset_map.get(result.table_name)
                self.db.add(
                    Transformation(
                        run_id=self.run_id,
                        dataset_id=dataset.id if dataset else None,
                        table_name=result.table_name,
                        column_name=result.column_name,
                        operation=result.operation,
                        rows_affected=result.rows_affected,
                        reason=result.reason,
                        before_example=result.before_example,
                        after_example=result.after_example,
                        parameters=result.parameters,
                    )
                )
            self.parquet_dir = persist_parquet(self.run_id, self.tables)
            overall = round(sum(r.overall for r in reports) / max(len(reports), 1), 2)
            return {
                "issues": len(combined_issues),
                "transformations": len(results),
                "overall_score": overall,
                "llm": (interpretation or {}).get("_llm"),
            }

        return self._step("quality", run)

    def _semantic(self):
        def run():
            domain = get_domain(self.project.domain or "general")
            dimensions, measures = self._infer_semantic()
            kpi_specs = self._heuristic_kpis(measures, dimensions)
            llm = interpret_semantic(
                {
                    "objective": self.project.business_objective,
                    "domain": domain.model_dump(),
                    "dimensions": dimensions,
                    "measures": measures,
                    "joins": [j.model_dump() for j in self.joins if j.validated][:30],
                }
            )
            if llm and isinstance(llm.get("kpis"), list):
                kpi_specs = self._merge_llm_kpis(kpi_specs, llm["kpis"], measures)
            model = SemanticModel(
                run_id=self.run_id,
                project_id=self.project_id,
                version=1,
                domain=self.project.domain,
                summary=f"{len(dimensions)} dimensions, {len(measures)} measures, {len(kpi_specs)} KPIs",
            )
            self.db.add(model)
            self.db.flush()
            for dim in dimensions:
                self.db.add(Dimension(semantic_model_id=model.id, **dim))
            for meas in measures:
                self.db.add(Measure(semantic_model_id=model.id, **meas))
            for join in self.joins:
                if not join.validated:
                    continue
                self.db.add(
                    Relationship(
                        semantic_model_id=model.id,
                        source_table=join.source_table,
                        source_column=join.source_column,
                        target_table=join.target_table,
                        target_column=join.target_column,
                        cardinality=join.cardinality,
                        confidence=join.confidence,
                        validated=join.validated,
                        overlap_ratio=join.overlap_ratio,
                        extra=join.evidence,
                    )
                )
            store = AnalyticalStore(self.parquet_dir or persist_parquet(self.run_id, self.tables))
            store.register_frames(self.tables)
            join_dicts = [j.model_dump() for j in self.joins if j.validated]
            computed = 0
            for spec in kpi_specs:
                try:
                    compiled = compile_formula(spec["formula"], join_dicts)
                    result_frame = store.query(compiled.sql)
                    value = result_frame[0, 0] if result_frame.height else None
                    value = float(value) if value is not None else None
                    kpi = KPI(
                        run_id=self.run_id,
                        semantic_model_id=model.id,
                        name=spec["name"],
                        slug=_slug(spec["name"]),
                        description=spec.get("description") or spec["name"],
                        business_meaning=spec.get("business_meaning") or spec["name"],
                        formula=spec["formula"],
                        unit=spec.get("unit"),
                        dimensions=spec.get("dimensions") or [],
                        data_sources=compiled.tables,
                        confidence=spec.get("confidence", 0.7),
                        validation_status="computed" if value is not None else "failed",
                        query_sql=compiled.sql,
                    )
                    self.db.add(kpi)
                    self.db.flush()
                    breakdown = self._breakdown(store, compiled, spec)
                    series = self._time_series(store, compiled, dimensions)
                    self.db.add(
                        KPIResult(
                            kpi_id=kpi.id,
                            run_id=self.run_id,
                            value=value,
                            query_sql=compiled.sql,
                            row_count=int(result_frame.height),
                            breakdown=breakdown,
                            time_series=series,
                            status="computed" if value is not None else "failed",
                            computed_at=self._now(),
                            previous_value=_previous(series),
                            change_pct=_change_from_series(series),
                        )
                    )
                    computed += 1
                    publish_event(str(self.run_id), "kpi.calculated", {"name": kpi.name, "value": value})
                except (FormulaError, Exception) as exc:
                    logger.warning("kpi_failed", formula=spec.get("formula"), error=str(exc))
                    self.db.add(
                        KPI(
                            run_id=self.run_id,
                            semantic_model_id=model.id,
                            name=spec["name"],
                            slug=_slug(spec["name"]),
                            description=spec.get("description") or spec["name"],
                            business_meaning=spec.get("business_meaning") or spec["name"],
                            formula=spec["formula"],
                            unit=spec.get("unit"),
                            confidence=0.0,
                            validation_status="invalid_formula",
                            query_sql=None,
                        )
                    )
            store.close()
            return {"dimensions": len(dimensions), "measures": len(measures), "kpis_computed": computed, "llm": (llm or {}).get("_llm")}

        return self._step("semantic", run)

    def _analyst(self):
        def run():
            kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
            evidence_pack = []
            insights: list[Insight] = []
            for kpi in kpis:
                result = self.db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first()
                if not result or result.value is None:
                    continue
                series_vals = [p.get("value") for p in (result.time_series or []) if p.get("value") is not None]
                trend = linear_trend(series_vals)
                anomalies = zscore_anomalies(series_vals) + iqr_outliers(series_vals)
                change = period_change(result.value, result.previous_value)
                self.db.add(
                    AnalysisResult(
                        run_id=self.run_id,
                        analysis_type="trend",
                        metric=kpi.name,
                        details=trend,
                        evidence={"series_points": len(series_vals)},
                    )
                )
                if anomalies:
                    self.db.add(
                        AnalysisResult(
                            run_id=self.run_id,
                            analysis_type="anomaly",
                            metric=kpi.name,
                            details={"anomalies": anomalies[:10]},
                            evidence={"method": "zscore+iqr"},
                        )
                    )
                evidence_pack.append(
                    {
                        "kpi": kpi.name,
                        "value": result.value,
                        "previous": result.previous_value,
                        "change_pct": result.change_pct,
                        "formula": kpi.formula,
                        "sql": kpi.query_sql,
                        "trend": trend,
                        "anomalies": anomalies[:5],
                    }
                )
                if result.change_pct is not None:
                    direction = "increased" if result.change_pct > 0 else "decreased"
                    insights.append(
                        Insight(
                            run_id=self.run_id,
                            kpi_id=kpi.id,
                            title=f"{kpi.name} {direction} by {abs(result.change_pct)*100:.1f}%",
                            description=(
                                f"{kpi.name} {direction} from {result.previous_value:.4g} to {result.value:.4g} "
                                f"({result.change_pct*100:+.1f}%) based on {kpi.formula}."
                            ),
                            category="trend",
                            evidence={"previous": result.previous_value, "current": result.value, "sql": kpi.query_sql},
                            metric=kpi.name,
                            value=result.value,
                            comparison=f"{result.change_pct*100:+.1f}% vs previous period",
                            period="period-over-period",
                            severity="info" if abs(result.change_pct) < 0.2 else "warning",
                            confidence=0.8 if trend.get("r2") else 0.6,
                            query_sql=kpi.query_sql,
                            grounded=True,
                        )
                    )
                elif result.value is not None:
                    insights.append(
                        Insight(
                            run_id=self.run_id,
                            kpi_id=kpi.id,
                            title=f"{kpi.name} = {result.value:.4g}",
                            description=f"{kpi.name} was computed as {result.value:.4g} using {kpi.formula}.",
                            category="finding",
                            evidence={"current": result.value, "sql": kpi.query_sql},
                            metric=kpi.name,
                            value=result.value,
                            comparison=None,
                            period=None,
                            severity="info",
                            confidence=0.75,
                            query_sql=kpi.query_sql,
                            grounded=True,
                        )
                    )
                if anomalies:
                    top = anomalies[0]
                    insights.append(
                        Insight(
                            run_id=self.run_id,
                            kpi_id=kpi.id,
                            title=f"Anomaly detected in {kpi.name}",
                            description=f"Statistical {top['method']} flagged value {top['value']:.4g} in the {kpi.name} series.",
                            category="anomaly",
                            evidence={"anomaly": top, "series_len": len(series_vals)},
                            metric=kpi.name,
                            value=top["value"],
                            severity="warning",
                            confidence=0.7,
                            query_sql=kpi.query_sql,
                            grounded=True,
                        )
                    )

            # Pareto / concentration on first categorical dimension with a numeric measure
            for name, frame in self.tables.items():
                cats = [c for c in frame.columns if frame[c].dtype in (pl.Utf8, pl.String) or "String" in str(frame[c].dtype)]
                nums = [c for c in frame.columns if frame[c].dtype.is_numeric()]
                if cats and nums:
                    par = pareto(frame, cats[0], nums[0])
                    self.db.add(AnalysisResult(run_id=self.run_id, analysis_type="pareto", metric=f"{nums[0]} by {cats[0]}", details=par, evidence={"table": name}))
                    conc = concentration(frame, cats[0])
                    if conc:
                        self.db.add(AnalysisResult(run_id=self.run_id, analysis_type="concentration", metric=cats[0], details=conc, evidence={"table": name}))
                corr = correlation_matrix(frame)
                if corr:
                    self.db.add(AnalysisResult(run_id=self.run_id, analysis_type="correlation", metric=name, details={"pairs": corr}, evidence={"table": name}))

            llm = interpret_analyst(
                {
                    "objective": self.project.business_objective,
                    "evidence": evidence_pack,
                }
            )
            if llm and isinstance(llm.get("insights"), list):
                for item in llm["insights"]:
                    if not _insight_grounded(item, evidence_pack):
                        continue
                    insights.append(
                        Insight(
                            run_id=self.run_id,
                            title=item.get("title") or "Insight",
                            description=item.get("description") or "",
                            category=item.get("category") or "finding",
                            evidence=item.get("evidence") or {},
                            metric=item.get("metric"),
                            value=_as_float(item.get("value")),
                            comparison=item.get("comparison"),
                            period=item.get("period"),
                            severity=item.get("severity") or "info",
                            confidence=float(item.get("confidence") or 0.5),
                            grounded=True,
                        )
                    )
            for insight in insights:
                self.db.add(insight)
                publish_event(str(self.run_id), "insight.generated", {"title": insight.title})
            return {"insights": len(insights), "analyses": len(evidence_pack), "llm": (llm or {}).get("_llm")}

        return self._step("analyst", run)

    def _dashboard(self):
        def run():
            kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id, KPI.validation_status == "computed").all()
            widgets_spec = self._default_dashboard(kpis)
            llm = interpret_dashboard(
                {
                    "objective": self.project.business_objective,
                    "kpis": [{"name": k.name, "slug": k.slug, "formula": k.formula, "unit": k.unit} for k in kpis],
                }
            )
            if llm and isinstance(llm.get("widgets"), list):
                widgets_spec = self._merge_dashboard(widgets_spec, llm["widgets"], kpis)
            dash = DashboardDefinition(
                run_id=self.run_id,
                project_id=self.project_id,
                title=llm.get("title") if llm else f"{self.project.name} dashboard",
                layout={"columns": 12},
                published=False,
                audit_status="pending",
            )
            self.db.add(dash)
            self.db.flush()
            kpi_by_slug = {k.slug: k for k in kpis}
            kpi_by_name = {_slug(k.name): k for k in kpis}
            for spec in widgets_spec:
                kpi = kpi_by_slug.get(spec.get("kpi_slug") or "") or kpi_by_name.get(_slug(spec.get("kpi_slug") or spec.get("title") or ""))
                result = self.db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first() if kpi else None
                data = {}
                if result:
                    data = {
                        "value": result.value,
                        "previous_value": result.previous_value,
                        "change_pct": result.change_pct,
                        "series": result.time_series,
                        "breakdown": result.breakdown,
                    }
                pos = spec.get("position") or {}
                self.db.add(
                    DashboardWidget(
                        dashboard_id=dash.id,
                        widget_type=spec["type"],
                        title=spec["title"],
                        kpi_id=kpi.id if kpi else None,
                        query_sql=kpi.query_sql if kpi else None,
                        dimensions=spec.get("dimensions") or [],
                        measures=spec.get("measures") or [],
                        format=spec.get("format") or {},
                        position_x=int(pos.get("x", 0)),
                        position_y=int(pos.get("y", 0)),
                        width=int(pos.get("w", 3)),
                        height=int(pos.get("h", 2)),
                        data=data,
                        explanation=spec.get("reason"),
                    )
                )
            publish_event(str(self.run_id), "dashboard.generated", {"widgets": len(widgets_spec)})
            return {"widgets": len(widgets_spec), "llm": (llm or {}).get("_llm")}

        return self._step("dashboard", run)

    def _auditor(self):
        def run():
            kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
            insights = self.db.query(Insight).filter(Insight.run_id == self.run_id).all()
            dash = self.db.query(DashboardDefinition).filter(DashboardDefinition.run_id == self.run_id).first()
            findings = []
            for kpi in kpis:
                ok = kpi.validation_status == "computed" and kpi.query_sql is not None
                findings.append({"entity_type": "kpi", "entity": kpi.name, "status": "VALID" if ok else "INVALID", "message": kpi.validation_status})
                self.db.add(
                    AuditEvent(
                        run_id=self.run_id,
                        event_type="kpi_validation",
                        severity="info" if ok else "error",
                        message=f"KPI {kpi.name}: {kpi.validation_status}",
                        entity_type="kpi",
                        entity_id=str(kpi.id),
                        details={"formula": kpi.formula, "sql": kpi.query_sql},
                        status="VALID" if ok else "INVALID",
                    )
                )
                result = self.db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first()
                self.db.add(
                    XAIExplanation(
                        run_id=self.run_id,
                        entity_type="kpi",
                        entity_id=str(kpi.id),
                        what_happened=f"{kpi.name} evaluated to {result.value if result else 'n/a'}.",
                        how_calculated=f"Formula {kpi.formula} compiled to SQL and executed on cleaned parquet tables.",
                        data_used=", ".join(kpi.data_sources or []),
                        kpi_relevance=kpi.business_meaning,
                        assumptions="Aggregation uses cleaned layer after recorded transformations. Outer joins may introduce nulls.",
                        quality_limitations="See data quality report for missingness and referential issues.",
                        transformations="Recorded in transformations table for this run.",
                        producer_agent="semantic",
                        validator_agent="auditor",
                        extra={"sql": kpi.query_sql},
                    )
                )
            ungrounded = [i for i in insights if not i.grounded]
            for insight in insights:
                self.db.add(
                    AuditEvent(
                        run_id=self.run_id,
                        event_type="insight_validation",
                        severity="info" if insight.grounded else "warning",
                        message=f"Insight '{insight.title}' grounded={insight.grounded}",
                        entity_type="insight",
                        entity_id=str(insight.id),
                        details=insight.evidence,
                        status="VALID" if insight.grounded else "REJECTED",
                    )
                )
            dash_status = "VALID" if dash and dash.widgets else "INVALID"
            if dash:
                dash.audit_status = dash_status
                dash.published = dash_status == "VALID"
            llm = interpret_auditor(
                {
                    "kpis": [{"name": k.name, "formula": k.formula, "status": k.validation_status} for k in kpis],
                    "insight_count": len(insights),
                    "ungrounded": len(ungrounded),
                }
            )
            publish_event(str(self.run_id), "audit.completed", {"status": dash_status})
            self.project.status = "ready" if dash_status == "VALID" else "audited_with_issues"
            return {"findings": len(findings), "dashboard_status": dash_status, "llm": (llm or {}).get("_llm")}

        return self._step("auditor", run)

    def _evaluate(self) -> None:
        kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
        valid = sum(1 for k in kpis if k.validation_status == "computed")
        self.db.add(EvaluationResult(run_id=self.run_id, agent_name="semantic", metric_name="kpi_formula_validity", score=valid / max(len(kpis), 1), details={"valid": valid, "total": len(kpis)}))
        insights = self.db.query(Insight).filter(Insight.run_id == self.run_id).all()
        grounded = sum(1 for i in insights if i.grounded)
        self.db.add(EvaluationResult(run_id=self.run_id, agent_name="analyst", metric_name="insight_factuality", score=grounded / max(len(insights), 1), details={"grounded": grounded, "total": len(insights)}))
        profiles = self.db.query(DataProfile).filter(DataProfile.run_id == self.run_id).all()
        self.db.add(EvaluationResult(run_id=self.run_id, agent_name="profiler", metric_name="tables_profiled", score=1.0 if profiles else 0.0, details={"count": len(profiles)}))
        self.db.commit()

    def _infer_semantic(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        dimensions: list[dict[str, Any]] = []
        measures: list[dict[str, Any]] = []
        for name, profile in self.profiles.items():
            for col in profile.columns:
                if col.logical_type in {"datetime", "categorical", "geo"} or (
                    col.logical_type == "text" and col.distinct_count <= max(50, int(profile.row_count * 0.05))
                ):
                    dimensions.append(
                        {
                            "name": f"{name}.{col.name}",
                            "table_name": name,
                            "column_name": col.name,
                            "dim_type": col.logical_type if col.logical_type in {"datetime", "categorical", "geo"} else "categorical",
                            "grain": col.stats.get("granularity") if col.logical_type == "datetime" else None,
                            "description": col.semantic_hint,
                        }
                    )
                if col.logical_type in {"currency", "quantity", "numeric"} and not col.is_candidate_pk:
                    agg = "SUM" if col.logical_type in {"currency", "quantity"} else "AVG"
                    measures.append(
                        {
                            "name": f"{name}.{col.name}",
                            "table_name": name,
                            "column_name": col.name,
                            "aggregation": agg,
                            "unit": "currency" if col.logical_type == "currency" else None,
                            "description": col.semantic_hint,
                        }
                    )
        return dimensions[:80], measures[:80]

    def _heuristic_kpis(self, measures: list[dict[str, Any]], dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        money = [m for m in measures if m.get("unit") == "currency"] or [m for m in measures if m["aggregation"] == "SUM"]
        id_cols = []
        for name, profile in self.profiles.items():
            for col in profile.columns:
                if col.is_candidate_pk or col.logical_type == "identifier":
                    id_cols.append((name, col.name, col.uniqueness_pct))
        if money:
            m = money[0]
            formula = f"SUM({m['table_name']}.{m['column_name']})"
            specs.append(
                {
                    "name": "Total Amount",
                    "description": f"Sum of {m['name']}",
                    "business_meaning": "Primary additive monetary or volume measure inferred from the schema.",
                    "formula": formula,
                    "unit": m.get("unit") or "units",
                    "confidence": 0.75,
                    "dimensions": [d["name"] for d in dimensions if d["dim_type"] == "datetime"][:1],
                }
            )
            if id_cols:
                table, col, _ = sorted(id_cols, key=lambda x: -x[2])[0]
                specs.append(
                    {
                        "name": "Average per identifier",
                        "description": f"{formula} / COUNT_DISTINCT({table}.{col})",
                        "business_meaning": "Ratio of the primary additive measure to distinct identifiers.",
                        "formula": f"{formula} / COUNT_DISTINCT({table}.{col})",
                        "unit": m.get("unit"),
                        "confidence": 0.65,
                    }
                )
        if id_cols:
            table, col, _ = sorted(id_cols, key=lambda x: -x[2])[0]
            specs.append(
                {
                    "name": "Record count",
                    "description": f"Distinct {table}.{col}",
                    "business_meaning": "Volume of distinct identifiers in the dataset.",
                    "formula": f"COUNT_DISTINCT({table}.{col})",
                    "unit": "count",
                    "confidence": 0.8,
                }
            )
        # Additional SUM/AVG measures as KPIs (bounded)
        for meas in measures[:6]:
            name = f"{meas['aggregation'].title()} of {meas['column_name']}"
            specs.append(
                {
                    "name": name,
                    "description": name,
                    "business_meaning": meas.get("description") or name,
                    "formula": f"{meas['aggregation']}({meas['table_name']}.{meas['column_name']})",
                    "unit": meas.get("unit"),
                    "confidence": 0.6,
                }
            )
        # de-dupe by formula
        unique: dict[str, dict[str, Any]] = {}
        for spec in specs:
            unique[spec["formula"]] = spec
        return list(unique.values())[:12]

    def _merge_llm_kpis(self, base: list[dict[str, Any]], proposed: list[dict[str, Any]], measures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        known_cols = {f"{m['table_name']}.{m['column_name']}" for m in measures}
        for name, profile in self.profiles.items():
            for col in profile.columns:
                known_cols.add(f"{name}.{col.name}")
        merged = {s["formula"]: s for s in base}
        for item in proposed:
            formula = (item.get("formula") or "").strip()
            if not formula:
                continue
            try:
                compiled = compile_formula(formula, [])
            except FormulaError:
                continue
            if any(col not in known_cols and "." in col for col in compiled.columns):
                continue
            merged[formula] = {
                "name": item.get("name") or formula,
                "description": item.get("description") or item.get("name") or formula,
                "business_meaning": item.get("business_meaning") or item.get("description") or formula,
                "formula": formula,
                "unit": item.get("unit"),
                "dimensions": item.get("dimensions") or [],
                "confidence": float(item.get("confidence") or 0.6),
            }
        return list(merged.values())[:15]

    def _breakdown(self, store: AnalyticalStore, compiled, spec: dict[str, Any]) -> list[dict[str, Any]]:
        dims = spec.get("dimensions") or []
        if not dims:
            for d in self._first_cat_dim():
                dims = [d]
                break
        if not dims:
            return []
        dim = dims[0]
        if "." in dim:
            table, col = dim.split(".", 1)
        else:
            return []
        try:
            sql = compiled.sql.replace("SELECT ", f'SELECT "{table}"."{col}" AS dimension, ', 1) + f' GROUP BY "{table}"."{col}" ORDER BY value DESC LIMIT 12'
            frame = store.query(sql)
            return [{"dimension": str(r["dimension"]), "value": _as_float(r["value"])} for r in frame.to_dicts()]
        except Exception:
            return []

    def _time_series(self, store: AnalyticalStore, compiled, dimensions: list[dict[str, Any]]) -> list[dict[str, Any]]:
        time_dims = [d for d in dimensions if d.get("dim_type") == "datetime"]
        if not time_dims:
            return []
        d = time_dims[0]
        try:
            sql = (
                compiled.sql.replace("SELECT ", f"SELECT date_trunc('month', \"{d['table_name']}\".\"{d['column_name']}\") AS period, ", 1)
                + f" GROUP BY 1 ORDER BY 1"
            )
            frame = store.query(sql)
            return [{"period": str(r["period"]), "value": _as_float(r["value"])} for r in frame.to_dicts() if r.get("period") is not None]
        except Exception:
            return []

    def _first_cat_dim(self) -> list[str]:
        for name, profile in self.profiles.items():
            for col in profile.columns:
                if col.logical_type in {"categorical", "geo"}:
                    return [f"{name}.{col.name}"]
        return []

    def _default_dashboard(self, kpis: list[KPI]) -> list[dict[str, Any]]:
        widgets = []
        x = 0
        for kpi in kpis[:4]:
            widgets.append({"type": "kpi", "title": kpi.name, "kpi_slug": kpi.slug, "position": {"x": x, "y": 0, "w": 3, "h": 2}, "reason": "Executive KPI card from computed metric."})
            x += 3
        if kpis:
            widgets.append({"type": "line", "title": f"{kpis[0].name} over time", "kpi_slug": kpis[0].slug, "position": {"x": 0, "y": 2, "w": 8, "h": 4}, "reason": "Time series when a date dimension exists; otherwise empty state."})
            widgets.append({"type": "bar", "title": f"{kpis[0].name} breakdown", "kpi_slug": kpis[0].slug, "position": {"x": 8, "y": 2, "w": 4, "h": 4}, "reason": "Categorical breakdown of the primary KPI."})
        if len(kpis) > 1:
            widgets.append({"type": "table", "title": "KPI catalog", "kpi_slug": kpis[0].slug, "position": {"x": 0, "y": 6, "w": 12, "h": 3}, "reason": "Tabular inspection of computed KPIs."})
        widgets.append({"type": "anomaly", "title": "Anomalies", "kpi_slug": kpis[0].slug if kpis else None, "position": {"x": 0, "y": 9, "w": 6, "h": 3}, "reason": "Surface statistically detected anomalies."})
        return widgets

    def _merge_dashboard(self, base, proposed, kpis: list[KPI]) -> list[dict[str, Any]]:
        slugs = {k.slug for k in kpis}
        allowed = {"kpi", "line", "bar", "area", "scatter", "map", "table", "ranking", "anomaly"}
        extra = []
        for item in proposed:
            wtype = item.get("type")
            if wtype not in allowed:
                continue
            slug = item.get("kpi_slug")
            if slug and slug not in slugs:
                continue
            extra.append(item)
        return extra or base

    def _now(self):
        from datetime import datetime, timezone

        return datetime.now(timezone.utc)


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _previous(series: list[dict[str, Any]]) -> float | None:
    if len(series) < 2:
        return None
    return _as_float(series[-2].get("value"))


def _change_from_series(series: list[dict[str, Any]]) -> float | None:
    if len(series) < 2:
        return None
    prev = _as_float(series[-2].get("value"))
    curr = _as_float(series[-1].get("value"))
    if prev in (None, 0) or curr is None:
        return None
    return (curr - prev) / prev


def _insight_grounded(item: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    metric = (item.get("metric") or "").lower()
    value = _as_float(item.get("value"))
    if not metric:
        return False
    for row in evidence:
        if metric not in row["kpi"].lower() and row["kpi"].lower() not in metric:
            continue
        if value is None:
            return True
        actual = row.get("value")
        if actual is None:
            continue
        if actual == 0:
            return abs(value) < 1e-6
        return abs(value - actual) / abs(actual) < 0.05 or abs(value - actual) < 1e-6
    return False
