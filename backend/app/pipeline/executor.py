"""Agent implementations for the BI pipeline.

Each agent is a node function over :class:`~app.agents.state.PipelineState`.
They are wired together by :mod:`app.agents.graph_def`, which owns the control
flow -- ordering, conditional routing, retry budgets and the auditor's feedback
edges. This module owns the work; it does not decide what runs next.

Two properties matter throughout:

* **Every node is idempotent.** The auditor can send the run back to the
  quality or semantic agent, so a node must be able to execute twice within a
  run. Each one deletes its own artefacts for the run before writing new ones.
* **Numbers come from Polars, DuckDB and validated SQL.** The LLM, when
  configured, interprets evidence and may propose additional KPIs, but every
  value shown to a user was computed deterministically and can be traced to the
  SQL that produced it.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
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
from app.agents.state import PipelineState
from app.analytics.kpi_catalog import InstantiatedKPI, generic_fallback, instantiate_catalog
from app.analytics.kpi_engine import (
    CompiledKPI,
    FormulaError,
    compile_formula,
    describe_grammar,
    quote_ident,
)
from app.analytics import recommendations
from app.analytics.roles import SemanticBinding, bind_roles
from app.analytics.stats import (
    concentration,
    correlation_matrix,
    iqr_outliers,
    linear_trend,
    pareto,
    seasonality,
    zscore_anomalies,
)
from app.config import get_settings
from app.data.etl import execute_plan, plan_from_issues
from app.data.joins import discover_joins
from app.data.pii import detect_pii
from app.data.profiler import TableProfile, profile_frame
from app.data.quality import QualityIssue, assess_quality, referential_issues
from app.data.schema_infer import SchemaInference
from app.data.store import AnalyticalStore
from app.evaluation import metrics
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

# The auditor sends the run back when results are not defensible. These are the
# thresholds it judges against.
MIN_ACCEPTABLE_QUALITY = 55.0
MIN_KPI_SUCCESS_RATIO = 0.6


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")[:80]


def _as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def load_project_tables(db: Session, project_id: UUID) -> dict[str, tuple[Dataset, pl.DataFrame, Path, SchemaInference]]:
    from app.data.adapters import adapter_for_file

    datasets = db.query(Dataset).filter(Dataset.project_id == project_id, Dataset.layer == "raw").all()
    loaded: dict[str, tuple[Dataset, pl.DataFrame, Path, SchemaInference]] = {}
    for dataset in datasets:
        file = db.query(DatasetFile).filter(DatasetFile.dataset_id == dataset.id).first()
        if not file:
            continue
        adapter = adapter_for_file(file.storage_path, name=dataset.table_name)
        frame, inference = adapter.load_with_inference()
        loaded[dataset.table_name] = (dataset, frame, Path(file.storage_path), inference)
    return loaded


def persist_parquet(run_id: UUID, tables: dict[str, pl.DataFrame]) -> Path:
    settings = get_settings()
    out = settings.processed_dir / str(run_id)
    out.mkdir(parents=True, exist_ok=True)
    for name, frame in tables.items():
        frame.write_parquet(out / f"{name}.parquet")
    return out


class PipelineExecutor:
    """Holds the run's working data and implements each agent.

    The heavy objects -- DataFrames, profiles, the DuckDB store -- live here
    rather than in the graph state, which carries only summaries so it stays
    small and serialisable.
    """

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
        self.inferences: dict[str, SchemaInference] = {}
        self.joins: list[Any] = []
        self.binding: SemanticBinding | None = None
        self.parquet_dir: Path | None = None
        self.attempts: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Schema exposed to the formula compiler, so an invented column is
    # rejected at compile time rather than becoming a wrong number.
    # ------------------------------------------------------------------
    @property
    def schema(self) -> dict[str, list[str]]:
        return {name: list(frame.columns) for name, frame in self.tables.items()}

    def load(self) -> None:
        loaded = load_project_tables(self.db, self.project_id)
        if not loaded:
            raise RuntimeError("No datasets uploaded for this project")
        for name, (dataset, frame, _, inference) in loaded.items():
            self.tables[name] = frame
            self.raw_tables[name] = frame
            self.dataset_map[name] = dataset
            self.inferences[name] = inference

    # ------------------------------------------------------------------
    # Step bookkeeping
    # ------------------------------------------------------------------
    def _begin_step(self, name: str):
        from app.models import AgentRun, PipelineStep

        attempt = self.attempts.get(name, 0) + 1
        self.attempts[name] = attempt
        step = (
            self.db.query(PipelineStep)
            .filter(PipelineStep.run_id == self.run_id, PipelineStep.name == name)
            .one_or_none()
        )
        started = datetime.now(timezone.utc)
        if step is not None:
            step.status = "running"
            step.started_at = started
            step.error = None
        self.run.current_step = name
        self.db.commit()
        publish_event(str(self.run_id), "agent.started", {"agent": name, "attempt": attempt})
        agent = AgentRun(
            run_id=self.run_id,
            step_id=step.id if step else None,
            agent_name=name,
            status="running",
            started_at=started,
            retry_count=attempt - 1,
        )
        self.db.add(agent)
        self.db.commit()
        return step, agent, started

    def run_step(self, name: str, fn: Callable[[], dict[str, Any]], state: PipelineState) -> dict[str, Any]:
        """Execute one agent, recording timing, tokens and failures.

        A failure is recorded and returned as state rather than raised, so the
        graph can route to the auditor and still produce a partial, clearly
        labelled result instead of losing the whole run.
        """
        step, agent, started = self._begin_step(name)
        try:
            summary = fn() or {}
            ended = datetime.now(timezone.utc)
            duration = int((ended - started).total_seconds() * 1000)
            if step is not None:
                step.status = "completed"
                step.completed_at = ended
                step.duration_ms = duration
                step.output_summary = summary
            agent.status = "completed"
            agent.completed_at = ended
            agent.latency_ms = duration
            agent.output_summary = summary
            llm_meta = summary.get("llm") or {}
            agent.llm_model = llm_meta.get("model")
            agent.prompt_tokens = llm_meta.get("prompt_tokens")
            agent.completion_tokens = llm_meta.get("completion_tokens")
            self.db.commit()
            publish_event(str(self.run_id), "agent.completed", {"agent": name, "summary": summary})
            return summary
        except Exception as exc:  # noqa: BLE001 - recorded, then routed
            self.db.rollback()
            logger.exception("agent_failed", agent=name, run_id=str(self.run_id), error=str(exc))
            ended = datetime.now(timezone.utc)
            if step is not None:
                step.status = "failed"
                step.error = str(exc)
                step.completed_at = ended
            agent.status = "failed"
            agent.error = str(exc)
            agent.completed_at = ended
            self.db.commit()
            publish_event(str(self.run_id), "agent.failed", {"agent": name, "error": str(exc)})
            errors = list(state.get("errors") or [])
            errors.append(f"{name}: {exc}")
            state["errors"] = errors
            return {"error": str(exc)}

    # ------------------------------------------------------------------
    # Agents
    # ------------------------------------------------------------------
    def orchestrator(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            columns = [c for frame in self.tables.values() for c in frame.columns]
            domain = infer_domain(self.project.business_objective, columns)
            self.project.domain = domain
            interpretation = interpret_orchestrator(
                {
                    "objective": self.project.business_objective,
                    "tables": {name: list(frame.columns) for name, frame in self.tables.items()},
                    "row_counts": {name: frame.height for name, frame in self.tables.items()},
                    "schema_inference": {
                        name: [c.model_dump() for c in inference.columns]
                        for name, inference in self.inferences.items()
                    },
                }
            )
            self.run.configuration = {
                "domain": domain,
                "table_count": len(self.tables),
                "plan": (interpretation or {}).get("plan_summary"),
                "risks": (interpretation or {}).get("risks"),
                "llm_enabled": get_settings().llm_configured,
                "kpi_grammar": describe_grammar(),
            }
            return {
                "domain": domain,
                "tables": list(self.tables),
                "rows": {n: f.height for n, f in self.tables.items()},
                "llm": (interpretation or {}).get("_llm"),
            }

        summary = self.run_step("orchestrator", run, state)
        state["domain"] = summary.get("domain", "general")
        state["datasets"] = [
            {"table": name, "rows": frame.height, "columns": frame.width}
            for name, frame in self.tables.items()
        ]
        state["status"] = "orchestrated"
        return state

    def profiler(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            self._clear(DataProfile, cascade_columns=True)
            all_pii: list[dict[str, Any]] = []
            compact: list[dict[str, Any]] = []
            for name, frame in self.tables.items():
                profile = profile_frame(frame, name)
                inference = self.inferences.get(name)
                if inference is not None:
                    profile.warnings.extend(inference.warnings)
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
                for column in profile.columns:
                    decision = inference.by_column(column.name) if inference else None
                    stats = dict(column.stats)
                    if decision is not None:
                        stats["type_inference"] = decision.model_dump()
                    self.db.add(
                        DataProfileColumn(
                            profile_id=row.id,
                            name=column.name,
                            inferred_type=column.inferred_type,
                            logical_type=column.logical_type,
                            null_count=column.null_count,
                            null_pct=column.null_pct,
                            distinct_count=column.distinct_count,
                            uniqueness_pct=column.uniqueness_pct,
                            is_candidate_pk=column.is_candidate_pk,
                            is_candidate_fk=column.is_candidate_fk,
                            semantic_hint=column.semantic_hint,
                            stats=stats,
                            warnings=column.warnings,
                        )
                    )
                compact.append(profile.model_dump())

            self.joins = discover_joins(self.tables)
            self.binding = bind_roles(self.profiles, self.tables)

            interpretation = interpret_profiler(
                {
                    "profiles": [
                        {
                            "name": p["name"],
                            "row_count": p["row_count"],
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
                        for p in compact
                    ],
                    "joins": [j.model_dump() for j in self.joins[:20]],
                    "roles": {r: b.ref for r, b in self.binding.roles.items()},
                    "returns_convention": self.binding.returns.model_dump(),
                    "pii": all_pii,
                }
            )
            if interpretation and interpretation.get("summary"):
                for record in self.db.query(DataProfile).filter(DataProfile.run_id == self.run_id):
                    record.summary = interpretation["summary"]

            return {
                "tables": len(self.tables),
                "rows": sum(p.row_count for p in self.profiles.values()),
                "joins": len(self.joins),
                "pii_flags": len(all_pii),
                "roles_bound": len(self.binding.roles),
                "returns_detected": self.binding.returns.detected,
                "llm": (interpretation or {}).get("_llm"),
            }

        summary = self.run_step("profiler", run, state)
        state["profiles"] = [{"table": n, "rows": p.row_count} for n, p in self.profiles.items()]
        state["joins"] = [j.model_dump() for j in self.joins]
        if self.binding is not None:
            state["roles"] = {role: b.ref for role, b in self.binding.roles.items()}
        state["status"] = "profiled"
        state.setdefault("summaries", {})["profiler"] = summary
        return state

    def quality(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            self._clear(DataQualityReport, cascade_issues=True)
            self._clear(Transformation)
            # Quality always re-derives from the raw tables, so a retry is not
            # applied on top of an already-cleaned frame.
            self.tables = {name: frame.clone() for name, frame in self.raw_tables.items()}
            self.profiles = {name: profile_frame(frame, name) for name, frame in self.tables.items()}

            join_issues = referential_issues(self.tables, self.joins)
            reports = []
            for name, frame in self.tables.items():
                scorecard = assess_quality(
                    frame,
                    self.profiles[name],
                    join_issues=[i for i in join_issues if i.table_name == name],
                    inference=self.inferences.get(name),
                )
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

            issues = [issue for report in reports for issue in report.issues]
            plan = plan_from_issues(issues)
            interpretation = interpret_quality(
                {
                    "issues": [i.model_dump() for i in issues[:80]],
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
            # Profiles and role bindings describe the cleaned layer from here on.
            self.profiles = {name: profile_frame(frame, name) for name, frame in self.tables.items()}
            self.binding = bind_roles(self.profiles, self.tables)
            self.parquet_dir = persist_parquet(self.run_id, self.tables)
            overall = round(sum(r.overall for r in reports) / max(len(reports), 1), 2)
            return {
                "issues": len(issues),
                "transformations": len(results),
                "overall_score": overall,
                "llm": (interpretation or {}).get("_llm"),
            }

        summary = self.run_step("quality", run, state)
        state["quality_report"] = {"overall_score": summary.get("overall_score"), "issues": summary.get("issues")}
        state["transformations"] = [{"count": summary.get("transformations", 0)}]
        state["status"] = "cleaned"
        state.setdefault("summaries", {})["quality"] = summary
        return state

    # ------------------------------------------------------------------
    def semantic(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            self._clear(KPI, cascade_results=True)
            self._clear(SemanticModel, cascade_semantic=True)

            retried = int((state.get("retry") or {}).get("semantic", 0)) + int(
                (state.get("retry") or {}).get("audit_semantic", 0)
            )
            domain_profile = get_domain(self.project.domain or "general")
            dimensions, measures = self._infer_semantic()
            assert self.binding is not None
            specs = instantiate_catalog(self.binding, self.project.domain or "general")
            if not specs:
                identifiers = [
                    f"{name}.{column.name}"
                    for name, profile in self.profiles.items()
                    for column in profile.columns
                    if column.is_candidate_pk or column.logical_type == "identifier"
                ]
                specs = generic_fallback(measures, identifiers)

            llm_meta = None
            # On a retry the auditor has already rejected LLM-proposed KPIs, so
            # the agent falls back to the catalog alone rather than asking again
            # and risking the same rejection.
            if retried == 0:
                llm = interpret_semantic(
                    {
                        "objective": self.project.business_objective,
                        "domain": domain_profile.model_dump(),
                        "grammar": describe_grammar(),
                        "roles": {r: b.ref for r, b in self.binding.roles.items()},
                        "schema": self.schema,
                        "existing_kpis": [{"name": s.name, "formula": s.formula} for s in specs],
                        "joins": [j.model_dump() for j in self.joins if j.validated][:30],
                    }
                )
                if llm:
                    llm_meta = llm.get("_llm")
                    if isinstance(llm.get("kpis"), list):
                        specs = self._merge_llm_kpis(specs, llm["kpis"])

            model = SemanticModel(
                run_id=self.run_id,
                project_id=self.project_id,
                version=1 + retried,
                domain=self.project.domain,
                summary=(
                    f"{len(dimensions)} dimensions, {len(measures)} measures, "
                    f"{len(specs)} KPIs, {len(self.binding.roles)} business roles bound"
                ),
                grain=self.binding.ref("order_id"),
            )
            self.db.add(model)
            self.db.flush()
            for dimension in dimensions:
                self.db.add(Dimension(semantic_model_id=model.id, **dimension))
            for measure in measures:
                self.db.add(Measure(semantic_model_id=model.id, **measure))
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
            computed = failed = 0
            try:
                for spec in specs:
                    if self._compute_kpi(store, model, spec, join_dicts):
                        computed += 1
                    else:
                        failed += 1
            finally:
                store.close()

            return {
                "dimensions": len(dimensions),
                "measures": len(measures),
                "kpis_computed": computed,
                "kpis_failed": failed,
                "attempt": self.attempts.get("semantic", 1),
                "llm": llm_meta,
            }

        summary = self.run_step("semantic", run, state)
        if not summary.get("kpis_computed"):
            retries = dict(state.get("retry") or {})
            used = int(retries.get("semantic", 0))
            if used < get_settings().pipeline_max_retries:
                retries["semantic"] = used + 1
                state["retry"] = retries
        kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
        state["kpis"] = [
            {"name": k.name, "slug": k.slug, "formula": k.formula, "status": k.validation_status}
            for k in kpis
        ]
        state["status"] = "modelled"
        state.setdefault("summaries", {})["semantic"] = summary
        return state

    def _compute_kpi(
        self,
        store: AnalyticalStore,
        model: SemanticModel,
        spec: InstantiatedKPI,
        joins: list[dict[str, Any]],
    ) -> bool:
        try:
            compiled = compile_formula(spec.formula, joins, schema=self.schema)
        except FormulaError as exc:
            logger.warning("kpi_formula_rejected", formula=spec.formula, error=str(exc))
            self.db.add(
                KPI(
                    run_id=self.run_id,
                    semantic_model_id=model.id,
                    name=spec.name,
                    slug=spec.slug or _slug(spec.name),
                    description=spec.description,
                    business_meaning=spec.business_meaning,
                    formula=spec.formula,
                    unit=spec.unit,
                    confidence=0.0,
                    validation_status="invalid_formula",
                    filters={"error": str(exc), **spec.provenance},
                    query_sql=None,
                )
            )
            return False

        try:
            frame = store.query(compiled.sql)
            value = _as_float(frame[0, 0]) if frame.height else None
        except Exception as exc:  # noqa: BLE001 - recorded on the KPI itself
            logger.warning("kpi_execution_failed", formula=spec.formula, error=str(exc))
            self.db.add(
                KPI(
                    run_id=self.run_id,
                    semantic_model_id=model.id,
                    name=spec.name,
                    slug=spec.slug or _slug(spec.name),
                    description=spec.description,
                    business_meaning=spec.business_meaning,
                    formula=spec.formula,
                    unit=spec.unit,
                    confidence=0.0,
                    validation_status="execution_failed",
                    filters={"error": str(exc), **spec.provenance},
                    query_sql=compiled.sql,
                )
            )
            return False

        kpi = KPI(
            run_id=self.run_id,
            semantic_model_id=model.id,
            name=spec.name,
            slug=spec.slug or _slug(spec.name),
            description=spec.description,
            business_meaning=spec.business_meaning,
            formula=spec.formula,
            unit=spec.unit,
            dimensions=spec.dimensions,
            data_sources=compiled.tables,
            confidence=spec.confidence,
            filters={**spec.provenance, "additivity": compiled.additivity, "higher_is_better": spec.higher_is_better},
            validation_status="computed" if value is not None else "null_result",
            query_sql=compiled.sql,
        )
        self.db.add(kpi)
        self.db.flush()

        series = self._time_series(store, compiled)
        breakdown = self._breakdown(store, compiled)

        # Compare only complete periods. A trailing part-month against a full
        # one manufactures a collapse in every single metric.
        comparable = _complete_points(series)
        previous = current = change = None
        if len(comparable) >= 2:
            previous = _as_float(comparable[-2]["value"])
            current = _as_float(comparable[-1]["value"])
            if previous not in (None, 0) and current is not None:
                change = (current - previous) / previous
        partial_tail = bool(series) and bool(series[-1].get("partial"))

        self.db.add(
            KPIResult(
                kpi_id=kpi.id,
                run_id=self.run_id,
                value=value,
                query_sql=compiled.sql,
                row_count=1,
                breakdown=breakdown,
                time_series=series,
                filters={
                    "format": spec.format,
                    "additivity": compiled.additivity,
                    "comparison_period": comparable[-1]["period"] if comparable else None,
                    "baseline_period": comparable[-2]["period"] if len(comparable) >= 2 else None,
                    "partial_period_excluded": series[-1]["period"] if partial_tail else None,
                },
                status="computed" if value is not None else "null_result",
                computed_at=datetime.now(timezone.utc),
                previous_value=previous,
                change_pct=change,
            )
        )
        publish_event(str(self.run_id), "kpi.calculated", {"name": kpi.name, "value": value})
        return value is not None

    def _time_series(self, store: AnalyticalStore, compiled: CompiledKPI) -> list[dict[str, Any]]:
        assert self.binding is not None
        date_ref = self.binding.ref("event_date")
        if not date_ref:
            return []
        table, column = date_ref.split(".", 1)
        if table not in compiled.tables:
            return []
        grain = self._time_grain(table, column)
        dimension_sql = f"date_trunc('{grain}', {quote_ident(table)}.{quote_ident(column)})"
        sql = compiled.grouped_sql(dimension_sql, alias="period", order_by="1 ASC")
        try:
            frame = store.query(sql)
        except Exception as exc:  # noqa: BLE001
            logger.warning("time_series_failed", error=str(exc))
            return []

        last_observation = self._last_observation(table, column)
        series: list[dict[str, Any]] = []
        for row in frame.to_dicts():
            period = row.get("period")
            if period is None:
                continue
            series.append(
                {
                    "period": str(period),
                    "value": _as_float(row["value"]),
                    # The final bucket is usually cut short by the extract date.
                    # Flagged, so nothing compares a part-month against a full one.
                    "partial": _is_partial_period(period, grain, last_observation),
                }
            )
        return series

    def _last_observation(self, table: str, column: str) -> datetime | None:
        frame = self.tables.get(table)
        if frame is None or column not in frame.columns:
            return None
        value = frame[column].drop_nulls().max()
        if isinstance(value, datetime):
            return value
        try:
            return datetime.combine(value, datetime.min.time())  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

    def _time_grain(self, table: str, column: str) -> str:
        """Pick a grain that yields a readable number of points."""
        frame = self.tables.get(table)
        if frame is None or column not in frame.columns:
            return "month"
        series = frame[column].drop_nulls()
        if series.len() < 2:
            return "month"
        try:
            span_days = (series.max() - series.min()).days  # type: ignore[operator]
        except Exception:  # noqa: BLE001
            return "month"
        if span_days <= 2:
            return "hour"
        if span_days <= 62:
            return "day"
        if span_days <= 365 * 2:
            return "month"
        return "quarter" if span_days <= 365 * 8 else "year"

    def _breakdown(self, store: AnalyticalStore, compiled: CompiledKPI) -> list[dict[str, Any]]:
        assert self.binding is not None
        for candidate in self.binding.dimensions:
            if candidate.evidence.get("logical_type") == "datetime":
                continue
            if candidate.table not in compiled.tables:
                continue
            dimension_sql = f"{quote_ident(candidate.table)}.{quote_ident(candidate.column)}"
            sql = compiled.grouped_sql(dimension_sql, alias="dimension", limit=15)
            try:
                frame = store.query(sql)
            except Exception:  # noqa: BLE001
                continue
            rows = [
                {"dimension": str(row["dimension"]), "value": _as_float(row["value"])}
                for row in frame.to_dicts()
                if row.get("dimension") is not None
            ]
            if rows:
                return rows
        return []

    # ------------------------------------------------------------------
    def analyst(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            self._clear(AnalysisResult)
            self._clear(Insight)
            kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
            evidence: list[dict[str, Any]] = []
            insights: list[Insight] = []

            for kpi in kpis:
                result = self.db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first()
                if not result or result.value is None:
                    continue
                # Statistics run on complete periods only; the truncated final
                # bucket would otherwise read as a crash in every series.
                complete = _complete_points(result.time_series or [])
                values = [p["value"] for p in complete]
                trend = linear_trend(values)
                anomalies = zscore_anomalies(values) + iqr_outliers(values)
                season = seasonality(complete)

                self.db.add(
                    AnalysisResult(
                        run_id=self.run_id,
                        analysis_type="trend",
                        metric=kpi.name,
                        details=trend,
                        evidence={"series_points": len(values), "sql": kpi.query_sql},
                    )
                )
                if anomalies:
                    # Attach the period to each flagged point: "1,069,368 was
                    # unusual" is only actionable once you know when.
                    dated = [
                        {
                            **anomaly,
                            "period": complete[anomaly["index"]]["period"]
                            if anomaly["index"] < len(complete)
                            else None,
                            "unit": kpi.unit,
                        }
                        for anomaly in anomalies[:10]
                    ]
                    self.db.add(
                        AnalysisResult(
                            run_id=self.run_id,
                            analysis_type="anomaly",
                            metric=kpi.name,
                            details={"anomalies": dated},
                            evidence={"method": "zscore+iqr", "periods_tested": len(complete)},
                        )
                    )
                if season:
                    self.db.add(
                        AnalysisResult(
                            run_id=self.run_id,
                            analysis_type="seasonality",
                            metric=kpi.name,
                            details=season,
                            evidence={"series_points": len(values)},
                        )
                    )

                evidence.append(
                    {
                        "kpi": kpi.name,
                        "value": result.value,
                        "unit": kpi.unit,
                        "previous": result.previous_value,
                        "change_pct": result.change_pct,
                        "formula": kpi.formula,
                        "trend": trend,
                        "anomalies": anomalies[:5],
                        "top_breakdown": (result.breakdown or [])[:5],
                    }
                )
                insights.extend(self._insights_for(kpi, result, trend, anomalies, season, values))

            insights.extend(self._structural_insights())
            insights.extend(self._caveat_insights())

            llm = interpret_analyst(
                {
                    "objective": self.project.business_objective,
                    "domain": self.project.domain,
                    "evidence": evidence,
                }
            )
            llm_added = 0
            if llm and isinstance(llm.get("insights"), list):
                for item in llm["insights"]:
                    if not _insight_grounded(item, evidence):
                        publish_event(
                            str(self.run_id),
                            "insight.rejected",
                            {"title": item.get("title"), "reason": "not supported by computed evidence"},
                        )
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
                    llm_added += 1

            generated = len(insights)
            insights = _rank_insights(insights)
            for insight in insights:
                self.db.add(insight)
                publish_event(str(self.run_id), "insight.generated", {"title": insight.title})

            return {
                "insights": len(insights),
                "insights_generated": generated,
                "llm_insights_accepted": llm_added,
                "metrics_analysed": len(evidence),
                "llm": (llm or {}).get("_llm"),
            }

        summary = self.run_step("analyst", run, state)
        state["status"] = "analysed"
        state.setdefault("summaries", {})["analyst"] = summary
        return state

    def _insights_for(self, kpi, result, trend, anomalies, season, values) -> list[Insight]:
        produced: list[Insight] = []
        unit = kpi.unit or ""

        meta = result.filters or {}
        comparison_period = meta.get("comparison_period")
        baseline_period = meta.get("baseline_period")
        excluded = meta.get("partial_period_excluded")

        if result.change_pct is not None:
            direction = "increased" if result.change_pct > 0 else "decreased"
            favourable = None
            meaning = (kpi.filters or {}).get("higher_is_better")
            if isinstance(meaning, bool):
                favourable = (result.change_pct > 0) == meaning
            severity = "info" if abs(result.change_pct) < 0.2 else "warning"
            latest_value = _as_float(
                next(
                    (p["value"] for p in reversed(result.time_series or []) if not p.get("partial")),
                    result.value,
                )
            )
            produced.append(
                Insight(
                    run_id=self.run_id,
                    kpi_id=kpi.id,
                    title=(
                        f"{kpi.name} {direction} {abs(result.change_pct) * 100:.1f}% "
                        f"in {comparison_period or 'the latest period'}"
                    ),
                    description=(
                        f"{kpi.name} moved from {_humanize(result.previous_value)} in {baseline_period} "
                        f"to {_humanize(latest_value)} in {comparison_period} "
                        f"({result.change_pct * 100:+.1f}%). Computed as {kpi.formula}."
                        + ("" if favourable is None else f" This is {'favourable' if favourable else 'unfavourable'}.")
                        + (
                            f" {excluded} is excluded from this comparison because the data "
                            "stops part-way through it."
                            if excluded
                            else ""
                        )
                    ),
                    category="trend",
                    evidence={
                        "previous": result.previous_value,
                        "current": result.value,
                        "sql": kpi.query_sql,
                    },
                    metric=kpi.name,
                    value=result.value,
                    comparison=f"{result.change_pct * 100:+.1f}% vs {baseline_period}",
                    period=str(comparison_period or "period-over-period"),
                    severity=severity,
                    confidence=0.85 if (trend.get("r2") or 0) > 0.3 else 0.7,
                    query_sql=kpi.query_sql,
                    grounded=True,
                )
            )
            # The direction that matters is the business one, not the sign.
            recommendations.attach(
                produced[-1],
                recommendations.adverse_move(
                    metric=kpi.name,
                    change_pct=result.change_pct,
                    previous=result.previous_value,
                    current=latest_value,
                    period=str(comparison_period or "the latest period"),
                )
                if favourable is False
                else recommendations.favourable_move(
                    metric=kpi.name,
                    change_pct=result.change_pct,
                    period=str(comparison_period or "the latest period"),
                    r2=trend.get("r2"),
                )
                if favourable is True
                else None,
            )
        else:
            produced.append(
                Insight(
                    run_id=self.run_id,
                    kpi_id=kpi.id,
                    title=f"{kpi.name} is {_humanize(result.value)} {unit}".strip(),
                    description=f"{kpi.name} was computed as {_humanize(result.value)} using {kpi.formula}.",
                    category="finding",
                    evidence={"current": result.value, "sql": kpi.query_sql},
                    metric=kpi.name,
                    value=result.value,
                    severity="info",
                    confidence=0.75,
                    query_sql=kpi.query_sql,
                    grounded=True,
                )
            )

        if trend.get("direction") in {"up", "down"} and len(values) >= 4:
            produced.append(
                Insight(
                    run_id=self.run_id,
                    kpi_id=kpi.id,
                    title=f"{kpi.name} trends {trend['direction']} across {len(values)} periods",
                    description=(
                        f"A least-squares fit over {len(values)} periods gives a slope of "
                        f"{_humanize(trend['slope'])} per period with R^2 = {trend['r2']:.2f}."
                    ),
                    category="trend",
                    evidence={"trend": trend, "series_points": len(values)},
                    metric=kpi.name,
                    value=result.value,
                    period=f"{len(values)} periods",
                    severity="info",
                    confidence=min(0.95, 0.5 + float(trend.get("r2") or 0) / 2),
                    query_sql=kpi.query_sql,
                    grounded=True,
                )
            )

        if anomalies:
            top = max(anomalies, key=lambda a: abs(a.get("zscore", 0)))
            series = _complete_points(result.time_series or [])
            period = series[top["index"]]["period"] if top["index"] < len(series) else "unknown period"
            produced.append(
                Insight(
                    run_id=self.run_id,
                    kpi_id=kpi.id,
                    title=f"Anomalous {kpi.name} in {period}",
                    description=(
                        f"{kpi.name} reached {_humanize(top['value'])} in {period}, flagged by the "
                        f"{top['method']} test"
                        + (f" at z = {top['zscore']:.2f}." if "zscore" in top else ".")
                    ),
                    category="anomaly",
                    evidence={"anomaly": top, "period": period, "series_len": len(series)},
                    metric=kpi.name,
                    value=top["value"],
                    period=str(period),
                    severity="warning",
                    confidence=0.75,
                    query_sql=kpi.query_sql,
                    grounded=True,
                )
            )
            recommendations.attach(
                produced[-1],
                recommendations.anomaly(
                    metric=kpi.name,
                    period=str(period),
                    value=top["value"],
                    method=top["method"],
                    periods_tested=len(series),
                ),
            )

        # A material return rate is an operational risk in its own right, and
        # deserves its own row rather than being buried in the KPI catalog.
        if kpi.slug == "order_return_rate" and (result.value or 0) >= 5:
            returned = (
                self.db.query(KPIResult)
                .join(KPI, KPI.id == KPIResult.kpi_id)
                .filter(KPI.run_id == self.run_id, KPI.slug == "returned_value")
                .first()
            )
            produced.append(
                Insight(
                    run_id=self.run_id,
                    kpi_id=kpi.id,
                    title=f"{result.value:.1f}% of orders are cancellations",
                    description=(
                        f"{kpi.name} is {result.value:.1f}%, computed as {kpi.formula}. "
                        "Returns are netted out of revenue, so this rate erodes the top line "
                        "even when gross sales look healthy."
                    ),
                    category="risk",
                    evidence={
                        "return_rate_pct": result.value,
                        "returned_value": returned.value if returned else None,
                        "sql": kpi.query_sql,
                    },
                    metric=kpi.name,
                    value=result.value,
                    severity="warning",
                    confidence=0.85,
                    query_sql=kpi.query_sql,
                    grounded=True,
                )
            )
            recommendations.attach(
                produced[-1],
                recommendations.return_rate(
                    rate_pct=float(result.value or 0),
                    returned_value=returned.value if returned else None,
                ),
            )

        breakdown = result.breakdown or []
        additivity = (result.filters or {}).get("additivity", "additive")
        # "X accounts for N% of the total" is only meaningful when the segment
        # values actually sum to the total. Averages and ratios never do.
        if len(breakdown) >= 3 and additivity == "additive":
            total = sum(abs(_as_float(b["value"]) or 0) for b in breakdown)
            top = breakdown[0]
            share = (abs(_as_float(top["value"]) or 0) / total) if total else 0
            if share >= 0.4:
                produced.append(
                    Insight(
                        run_id=self.run_id,
                        kpi_id=kpi.id,
                        title=f"{top['dimension']} accounts for {share * 100:.1f}% of {kpi.name}",
                        description=(
                            f"Of the top {len(breakdown)} segments, {top['dimension']} contributes "
                            f"{_humanize(top['value'])} of {_humanize(total)} ({share * 100:.1f}%). "
                            "Concentration this high makes the metric sensitive to a single segment."
                        ),
                        category="risk" if share >= 0.6 else "finding",
                        evidence={"breakdown": breakdown[:5], "share": share},
                        metric=kpi.name,
                        value=_as_float(top["value"]),
                        comparison=f"{share * 100:.1f}% of the top {len(breakdown)} segments",
                        severity="warning" if share >= 0.6 else "info",
                        confidence=0.8,
                        query_sql=kpi.query_sql,
                        grounded=True,
                    )
                )
                recommendations.attach(
                    produced[-1],
                    recommendations.concentration(
                        segment=str(top["dimension"]),
                        share=share,
                        metric=kpi.name,
                        segment_value=_as_float(top["value"]),
                    ),
                )

        if season and season.get("peak_period"):
            produced.append(
                Insight(
                    run_id=self.run_id,
                    kpi_id=kpi.id,
                    title=f"{kpi.name} peaks in {season['peak_period']}",
                    description=(
                        f"Across the series, {season['peak_period']} is the strongest period "
                        f"({_humanize(season['peak_value'])}) and {season['trough_period']} the weakest "
                        f"({_humanize(season['trough_value'])}), a {season['amplitude_pct']:.1f}% spread."
                    ),
                    category="trend",
                    evidence=season,
                    metric=kpi.name,
                    value=season["peak_value"],
                    period=str(season["peak_period"]),
                    severity="info",
                    confidence=0.7,
                    query_sql=kpi.query_sql,
                    grounded=True,
                )
            )
            recommendations.attach(
                produced[-1],
                recommendations.seasonality(
                    metric=kpi.name,
                    peak=str(season["peak_period"]),
                    trough=str(season["trough_period"]),
                    amplitude_pct=float(season["amplitude_pct"]),
                ),
            )
        return produced

    def _caveat_insights(self) -> list[Insight]:
        """Turn type-inference and role-binding limits into stated caveats.

        These conditions already gate the auditor's verdict; surfacing them as
        findings means a reader sees the limits of the numbers next to the
        numbers, instead of only in the audit record.
        """
        produced: list[Insight] = []
        notes = [note for inference in self.inferences.values() for note in inference.warnings]
        if self.binding is not None:
            notes.extend(self.binding.unbound_notes)

        for note in notes[:6]:
            text, basis = recommendations.data_caveat(issue=note)
            produced.append(
                Insight(
                    run_id=self.run_id,
                    title=note.split(":")[0].strip()[:120] or "Data quality caveat",
                    description=note,
                    category="quality_caveat",
                    evidence={"source": "schema inference / role binding"},
                    severity="warning",
                    confidence=1.0,
                    grounded=True,
                    recommendation=text,
                    recommendation_basis=basis,
                )
            )
        return produced

    def _structural_insights(self) -> list[Insight]:
        """Pareto, concentration and correlation findings over the cleaned tables."""
        produced: list[Insight] = []
        assert self.binding is not None
        measure = self.binding.roles.get("amount") or self.binding.roles.get("quantity")
        for name, frame in self.tables.items():
            dimension = next(
                (d for d in self.binding.dimensions if d.table == name and d.evidence.get("logical_type") != "datetime"),
                None,
            )
            if dimension and measure and measure.table == name and measure.column in frame.columns:
                result = pareto(frame, dimension.column, measure.column)
                self.db.add(
                    AnalysisResult(
                        run_id=self.run_id,
                        analysis_type="pareto",
                        metric=f"{measure.column} by {dimension.column}",
                        details=result,
                        evidence={"table": name},
                    )
                )
                if result.get("items") and result.get("cutoff_count"):
                    total_segments = len(result["items"])
                    produced.append(
                        Insight(
                            run_id=self.run_id,
                            title=(
                                f"{result['cutoff_count']} of {total_segments} {dimension.column} values "
                                f"drive 80% of {measure.column}"
                            ),
                            description=(
                                f"Cumulative share of {measure.column} by {dimension.column} reaches 80% "
                                f"after {result['cutoff_count']} segments out of the {total_segments} shown."
                            ),
                            category="opportunity",
                            evidence={"pareto": result["items"][:8]},
                            metric=f"{measure.column} by {dimension.column}",
                            value=float(result["cutoff_count"]),
                            severity="info",
                            confidence=0.8,
                            grounded=True,
                        )
                    )
                    recommendations.attach(
                        produced[-1],
                        recommendations.pareto(
                            dimension=dimension.column,
                            measure=measure.column,
                            cutoff=int(result["cutoff_count"]),
                            total_segments=total_segments,
                        ),
                    )
                focus = concentration(frame, dimension.column)
                if focus:
                    self.db.add(
                        AnalysisResult(
                            run_id=self.run_id,
                            analysis_type="concentration",
                            metric=dimension.column,
                            details=focus,
                            evidence={"table": name},
                        )
                    )
            pairs = correlation_matrix(frame)
            if pairs:
                self.db.add(
                    AnalysisResult(
                        run_id=self.run_id,
                        analysis_type="correlation",
                        metric=name,
                        details={"pairs": pairs},
                        evidence={"table": name},
                    )
                )
                strongest = pairs[0]
                if abs(strongest["correlation"]) >= 0.5:
                    produced.append(
                        Insight(
                            run_id=self.run_id,
                            title=(
                                f"{strongest['left']} and {strongest['right']} move together "
                                f"(r = {strongest['correlation']:.2f})"
                            ),
                            description=(
                                f"Pearson correlation of {strongest['correlation']:.3f} between "
                                f"{strongest['left']} and {strongest['right']} in {name}. "
                                "Correlation is not causation; treat this as a lead for investigation."
                            ),
                            category="finding",
                            evidence={"correlation": strongest, "table": name},
                            metric=f"{strongest['left']} ~ {strongest['right']}",
                            value=strongest["correlation"],
                            severity="info",
                            confidence=0.65,
                            grounded=True,
                        )
                    )
                    recommendations.attach(
                        produced[-1],
                        recommendations.correlation(
                            left=strongest["left"],
                            right=strongest["right"],
                            coefficient=float(strongest["correlation"]),
                        ),
                    )
        return produced

    # ------------------------------------------------------------------
    def dashboard(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            self._clear(DashboardDefinition, cascade_widgets=True)
            kpis = (
                self.db.query(KPI)
                .filter(KPI.run_id == self.run_id, KPI.validation_status == "computed")
                .all()
            )
            specs = self._default_dashboard(kpis)
            llm = interpret_dashboard(
                {
                    "objective": self.project.business_objective,
                    "kpis": [
                        {"name": k.name, "slug": k.slug, "formula": k.formula, "unit": k.unit}
                        for k in kpis
                    ],
                }
            )
            if llm and isinstance(llm.get("widgets"), list):
                specs = self._merge_dashboard(specs, llm["widgets"], kpis)

            dashboard = DashboardDefinition(
                run_id=self.run_id,
                project_id=self.project_id,
                title=(llm or {}).get("title") or f"{self.project.name} — {self.project.domain} overview",
                layout={"columns": 12},
                published=False,
                audit_status="pending",
            )
            self.db.add(dashboard)
            self.db.flush()

            by_slug = {k.slug: k for k in kpis}
            for spec in specs:
                kpi = by_slug.get(spec.get("kpi_slug") or "")
                result = (
                    self.db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first() if kpi else None
                )
                data: dict[str, Any] = {}
                if result:
                    data = {
                        "value": result.value,
                        "previous_value": result.previous_value,
                        "change_pct": result.change_pct,
                        "series": result.time_series,
                        "breakdown": result.breakdown,
                        "unit": kpi.unit if kpi else None,
                        "format": (result.filters or {}).get("format", {}),
                    }
                if spec["type"] == "table":
                    data["rows"] = [
                        {
                            "name": k.name,
                            "value": (
                                self.db.query(KPIResult)
                                .filter(KPIResult.kpi_id == k.id)
                                .first()
                                .value
                            ),
                            "unit": k.unit,
                            "formula": k.formula,
                        }
                        for k in kpis
                    ]
                if spec["type"] == "anomaly":
                    data["anomalies"] = [
                        {"metric": a.metric, **(a.details or {})}
                        for a in self.db.query(AnalysisResult)
                        .filter(
                            AnalysisResult.run_id == self.run_id,
                            AnalysisResult.analysis_type == "anomaly",
                        )
                        .all()
                    ]
                position = spec.get("position") or {}
                self.db.add(
                    DashboardWidget(
                        dashboard_id=dashboard.id,
                        widget_type=spec["type"],
                        title=spec["title"],
                        kpi_id=kpi.id if kpi else None,
                        query_sql=kpi.query_sql if kpi else None,
                        dimensions=spec.get("dimensions") or [],
                        measures=spec.get("measures") or [],
                        format=spec.get("format") or {},
                        position_x=int(position.get("x", 0)),
                        position_y=int(position.get("y", 0)),
                        width=int(position.get("w", 3)),
                        height=int(position.get("h", 2)),
                        data=data,
                        explanation=spec.get("reason"),
                    )
                )
            publish_event(str(self.run_id), "dashboard.generated", {"widgets": len(specs)})
            return {"widgets": len(specs), "kpis": len(kpis), "llm": (llm or {}).get("_llm")}

        summary = self.run_step("dashboard", run, state)
        state["status"] = "dashboard_built"
        state.setdefault("summaries", {})["dashboard"] = summary
        return state

    def _default_dashboard(self, kpis: list[KPI]) -> list[dict[str, Any]]:
        widgets: list[dict[str, Any]] = []
        headline = kpis[:4]
        for index, kpi in enumerate(headline):
            widgets.append(
                {
                    "type": "kpi",
                    "title": kpi.name,
                    "kpi_slug": kpi.slug,
                    "format": (kpi.filters or {}).get("format", {}),
                    "position": {"x": index * 3, "y": 0, "w": 3, "h": 2},
                    "reason": kpi.business_meaning,
                }
            )
        primary = next((k for k in kpis if k.unit == "currency"), kpis[0] if kpis else None)
        if primary is not None:
            widgets.append(
                {
                    "type": "line",
                    "title": f"{primary.name} over time",
                    "kpi_slug": primary.slug,
                    "position": {"x": 0, "y": 2, "w": 8, "h": 4},
                    "reason": "Trend of the primary monetary metric at the detected time grain.",
                }
            )
            widgets.append(
                {
                    "type": "bar",
                    "title": f"{primary.name} by segment",
                    "kpi_slug": primary.slug,
                    "position": {"x": 8, "y": 2, "w": 4, "h": 4},
                    "reason": "Breakdown across the highest-confidence chartable dimension.",
                }
            )
        if len(kpis) > 1:
            widgets.append(
                {
                    "type": "table",
                    "title": "KPI catalog",
                    "kpi_slug": kpis[0].slug,
                    "position": {"x": 0, "y": 6, "w": 12, "h": 3},
                    "reason": "Every computed KPI with its formula, for inspection.",
                }
            )
        widgets.append(
            {
                "type": "anomaly",
                "title": "Statistical anomalies",
                "kpi_slug": kpis[0].slug if kpis else None,
                "position": {"x": 0, "y": 9, "w": 12, "h": 3},
                "reason": "Points flagged by the z-score and IQR tests on KPI series.",
            }
        )
        return widgets

    def _merge_dashboard(self, base, proposed, kpis: list[KPI]) -> list[dict[str, Any]]:
        slugs = {k.slug for k in kpis}
        allowed = {"kpi", "line", "bar", "area", "scatter", "map", "table", "ranking", "anomaly"}
        extra = [
            item
            for item in proposed
            if item.get("type") in allowed and (not item.get("kpi_slug") or item["kpi_slug"] in slugs)
        ]
        return extra or base

    # ------------------------------------------------------------------
    def auditor(self, state: PipelineState) -> PipelineState:
        def run() -> dict[str, Any]:
            self._clear(AuditEvent)
            self._clear(XAIExplanation)
            kpis = self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
            insights = self.db.query(Insight).filter(Insight.run_id == self.run_id).all()
            dashboard = (
                self.db.query(DashboardDefinition)
                .filter(DashboardDefinition.run_id == self.run_id)
                .first()
            )

            findings: list[dict[str, Any]] = []
            for kpi in kpis:
                valid = kpi.validation_status == "computed" and kpi.query_sql is not None
                findings.append(
                    {
                        "entity_type": "kpi",
                        "entity": kpi.name,
                        "status": "VALID" if valid else "INVALID",
                        "message": kpi.validation_status,
                    }
                )
                self.db.add(
                    AuditEvent(
                        run_id=self.run_id,
                        event_type="kpi_validation",
                        severity="info" if valid else "error",
                        message=f"KPI {kpi.name}: {kpi.validation_status}",
                        entity_type="kpi",
                        entity_id=str(kpi.id),
                        details={"formula": kpi.formula, "sql": kpi.query_sql, "provenance": kpi.filters},
                        status="VALID" if valid else "INVALID",
                    )
                )
                self.db.add(self._explain(kpi))

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

            computed = sum(1 for k in kpis if k.validation_status == "computed")
            ratio = computed / len(kpis) if kpis else 0.0
            quality_score = _as_float((state.get("quality_report") or {}).get("overall_score")) or 0.0
            retries = state.get("retry") or {}

            # The verdict decides the next edge in the graph.
            if computed == 0 or ratio < MIN_KPI_SUCCESS_RATIO:
                status = "retry_semantic"
                reason = (
                    f"Only {computed} of {len(kpis)} KPIs computed "
                    f"({ratio:.0%}, below the {MIN_KPI_SUCCESS_RATIO:.0%} bar)."
                )
            elif quality_score and quality_score < MIN_ACCEPTABLE_QUALITY:
                status = "retry_quality"
                reason = (
                    f"Data quality scored {quality_score:.1f}, below the "
                    f"{MIN_ACCEPTABLE_QUALITY} threshold for publishing."
                )
            elif not (dashboard and dashboard.widgets):
                status = "INVALID"
                reason = "No dashboard widgets were produced."
            else:
                status = "VALID"
                reason = (
                    f"{computed} of {len(kpis)} KPIs computed, quality {quality_score:.1f}, "
                    f"{len(dashboard.widgets)} widgets bound to computed metrics."
                )

            caveats = [
                note
                for inference in self.inferences.values()
                for note in inference.warnings
            ]
            if self.binding is not None:
                caveats.extend(self.binding.unbound_notes)

            llm = interpret_auditor(
                {
                    "kpis": [
                        {"name": k.name, "formula": k.formula, "status": k.validation_status}
                        for k in kpis
                    ],
                    "insight_count": len(insights),
                    "verdict": status,
                    "reason": reason,
                }
            )
            return {
                "status": status,
                "reason": reason,
                "findings": len(findings),
                "kpi_success_ratio": round(ratio, 4),
                "caveats": caveats,
                "llm": (llm or {}).get("_llm"),
            }

        summary = self.run_step("auditor", run, state)
        status = summary.get("status", "INVALID")
        reason = summary.get("reason", "")

        # The retry budget is consumed here, inside the node, because LangGraph
        # only persists state a node returns -- a counter incremented in a
        # routing function is thrown away, and the graph loops forever.
        budget = get_settings().pipeline_max_retries
        retries = dict(state.get("retry") or {})
        if status.startswith("retry"):
            key = "audit_quality" if status == "retry_quality" else "audit_semantic"
            used = int(retries.get(key, 0))
            if used >= budget:
                status = "VALID"
                reason += (
                    f" Retry budget for {key} exhausted after {used} attempts; "
                    "published with the caveats above rather than retried further."
                )
            else:
                retries[key] = used + 1
                state["retry"] = retries

        summary["status"] = status
        summary["reason"] = reason
        summary["retry"] = retries
        self._record_verdict(summary)

        state["audit"] = summary
        state["status"] = "audited"
        state.setdefault("summaries", {})["auditor"] = summary
        return state

    def _record_verdict(self, summary: dict[str, Any]) -> None:
        """Persist the final verdict once the retry budget has been applied."""
        status = summary.get("status", "INVALID")
        self.db.query(AuditEvent).filter(
            AuditEvent.run_id == self.run_id, AuditEvent.event_type == "run_verdict"
        ).delete(synchronize_session=False)
        self.db.add(
            AuditEvent(
                run_id=self.run_id,
                event_type="run_verdict",
                severity="info" if status == "VALID" else "warning",
                message=summary.get("reason", ""),
                entity_type="run",
                entity_id=str(self.run_id),
                details={
                    "kpi_success_ratio": summary.get("kpi_success_ratio"),
                    "caveats": summary.get("caveats", []),
                    "retries": summary.get("retry", {}),
                },
                status=status,
            )
        )
        dashboard = (
            self.db.query(DashboardDefinition)
            .filter(DashboardDefinition.run_id == self.run_id)
            .first()
        )
        if dashboard is not None:
            dashboard.audit_status = "VALID" if status == "VALID" else "PENDING"
            dashboard.published = status == "VALID"
        self.db.commit()
        publish_event(
            str(self.run_id), "audit.completed", {"status": status, "reason": summary.get("reason")}
        )

    def _explain(self, kpi: KPI) -> XAIExplanation:
        result = self.db.query(KPIResult).filter(KPIResult.kpi_id == kpi.id).first()
        provenance = kpi.filters or {}
        roles = provenance.get("roles") or {}
        role_text = ", ".join(f"{role} = {column}" for role, column in roles.items()) or "none bound"
        transformations = (
            self.db.query(Transformation).filter(Transformation.run_id == self.run_id).all()
        )
        applied = ", ".join(
            f"{t.operation} on {t.table_name}"
            + (f".{t.column_name}" if t.column_name else "")
            + f" ({t.rows_affected} rows)"
            for t in transformations
        ) or "none"
        caveats = [
            note for inference in self.inferences.values() for note in inference.warnings
        ]
        return XAIExplanation(
            run_id=self.run_id,
            entity_type="kpi",
            entity_id=str(kpi.id),
            what_happened=(
                f"{kpi.name} evaluated to "
                # Full float precision is an artefact of binary arithmetic, not
                # a measurement: "481.32644506882264" reads as false precision.
                + (f"{result.value:,.2f}" if result and result.value is not None else "no value")
                + (f" {kpi.unit}" if kpi.unit else "")
                + "."
            ),
            how_calculated=(
                f"The formula {kpi.formula} was parsed, checked against the table schema, and "
                f"compiled to the SQL below, then executed on the cleaned Parquet layer. "
                f"SQL: {kpi.query_sql}"
            ),
            data_used=", ".join(kpi.data_sources or []) or "n/a",
            kpi_relevance=kpi.business_meaning,
            assumptions=(
                f"Business roles were bound as: {role_text}. "
                + (
                    f"Revenue basis: {provenance['revenue_basis']}. "
                    if provenance.get("revenue_basis")
                    else ""
                )
                + (
                    f"Row filter applied: {'; '.join(provenance['filters'])}. "
                    if provenance.get("filters")
                    else ""
                )
                + "Division by zero yields NULL rather than an error."
            ),
            quality_limitations="; ".join(caveats) or "No type-inference caveats were raised.",
            transformations=applied,
            producer_agent="semantic",
            validator_agent="auditor",
            extra={"sql": kpi.query_sql, "provenance": provenance},
        )

    # ------------------------------------------------------------------
    def publish(self, state: PipelineState) -> PipelineState:
        self._evaluate(state)
        verdict = (state.get("audit") or {}).get("status", "VALID")
        self.run.status = "completed"
        self.run.completed_at = datetime.now(timezone.utc)
        self.run.current_step = "completed"
        self.project.status = "ready" if verdict == "VALID" else "audited_with_issues"
        self.db.commit()
        publish_event(str(self.run_id), "pipeline.completed", {"status": "completed", "verdict": verdict})
        state["status"] = "published"
        return state

    def _evaluate(self, state: PipelineState) -> None:
        """Score each agent and compare the run to a naive baseline.

        The scoring lives in :mod:`app.evaluation.metrics` so the same
        definitions back this table, the Audit screen and the exported report.
        """
        self._clear(EvaluationResult)
        kpis = [
            {"validation_status": k.validation_status, "query_sql": k.query_sql, "filters": k.filters}
            for k in self.db.query(KPI).filter(KPI.run_id == self.run_id).all()
        ]
        insights = [
            {"grounded": i.grounded}
            for i in self.db.query(Insight).filter(Insight.run_id == self.run_id).all()
        ]
        widgets = [
            {"query_sql": w.query_sql, "data": w.data}
            for w in self.db.query(DashboardWidget)
            .join(DashboardDefinition)
            .filter(DashboardDefinition.run_id == self.run_id)
            .all()
        ]
        decisions = [
            column.model_dump()
            for inference in self.inferences.values()
            for column in inference.columns
        ]
        profiles = self.db.query(DataProfile).filter(DataProfile.run_id == self.run_id).count()

        def record(agent: str, metric: str, score: float, details: dict[str, Any]) -> None:
            self.db.add(
                EvaluationResult(
                    run_id=self.run_id,
                    agent_name=agent,
                    metric_name=metric,
                    score=round(float(score), 4),
                    details=details,
                )
            )

        computed = sum(1 for k in kpis if k["validation_status"] == "computed")
        record(
            "semantic",
            "kpi_formula_validity",
            metrics.formula_validity(kpis),
            {"valid": computed, "total": len(kpis)},
        )
        record(
            "analyst",
            "insight_groundedness",
            metrics.insight_groundedness(insights),
            {
                "grounded": sum(1 for i in insights if i["grounded"]),
                "total": len(insights),
                "hallucination_rate": round(metrics.hallucination_rate(insights), 4),
            },
        )
        record(
            "dashboard",
            "widgets_bound_to_data",
            metrics.dashboard_validity(widgets),
            {"widgets": len(widgets)},
        )
        record(
            "profiler",
            "type_inference_resolution",
            metrics.type_inference_resolution(decisions),
            {
                "columns": len(decisions),
                "lossless": sum(1 for d in decisions if (d.get("parse_rate") or 1.0) >= 1.0),
                "tables_profiled": profiles,
                "decisions": decisions,
            },
        )

        baseline_kpis = sum(
            1
            for profile in self.profiles.values()
            for column in profile.columns
            if column.logical_type in {"currency", "quantity", "numeric"}
            and not column.is_candidate_pk
        )
        catalog_kpis = sum(1 for k in kpis if (k["filters"] or {}).get("template"))
        record(
            "semantic",
            "vs_naive_baseline",
            metrics.baseline_lift(catalog_kpis, baseline_kpis),
            {
                "baseline_kpis": baseline_kpis,
                "baseline_method": "one SUM/AVG per numeric column, no business meaning",
                "catalog_kpis": catalog_kpis,
                "note": (
                    "The baseline cannot express row-level arithmetic, so it has no revenue, "
                    "no average order value and no return rate."
                ),
            },
        )
        record(
            "auditor",
            "verdict_confidence",
            1.0 if (state.get("audit") or {}).get("status") == "VALID" else 0.5,
            {"verdict": (state.get("audit") or {}).get("status")},
        )
        self.db.commit()

    def _infer_semantic(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        dimensions: list[dict[str, Any]] = []
        measures: list[dict[str, Any]] = []
        assert self.binding is not None
        chartable = {(d.table, d.column) for d in self.binding.dimensions}
        for name, profile in self.profiles.items():
            for column in profile.columns:
                if (name, column.name) in chartable:
                    dimensions.append(
                        {
                            "name": f"{name}.{column.name}",
                            "table_name": name,
                            "column_name": column.name,
                            "dim_type": column.logical_type
                            if column.logical_type in {"datetime", "categorical", "geo"}
                            else "categorical",
                            "grain": column.stats.get("granularity")
                            if column.logical_type == "datetime"
                            else None,
                            "description": column.semantic_hint,
                        }
                    )
                if column.logical_type in {"currency", "quantity", "numeric"} and not column.is_candidate_pk:
                    measures.append(
                        {
                            "name": f"{name}.{column.name}",
                            "table_name": name,
                            "column_name": column.name,
                            "aggregation": "SUM"
                            if column.logical_type in {"currency", "quantity"}
                            else "AVG",
                            "unit": "currency" if column.logical_type == "currency" else None,
                            "description": column.semantic_hint,
                        }
                    )
        return dimensions[:80], measures[:80]

    def _merge_llm_kpis(
        self, base: list[InstantiatedKPI], proposed: list[dict[str, Any]]
    ) -> list[InstantiatedKPI]:
        """Accept LLM KPIs only if they compile against the real schema."""
        merged = {spec.formula: spec for spec in base}
        for item in proposed:
            formula = (item.get("formula") or "").strip()
            if not formula or formula in merged:
                continue
            try:
                compile_formula(formula, [], schema=self.schema)
            except FormulaError as exc:
                publish_event(
                    str(self.run_id),
                    "kpi.rejected",
                    {"formula": formula, "reason": str(exc)},
                )
                continue
            name = item.get("name") or formula
            merged[formula] = InstantiatedKPI(
                slug=_slug(name),
                name=name,
                description=item.get("description") or name,
                business_meaning=item.get("business_meaning") or item.get("description") or name,
                formula=formula,
                unit=item.get("unit") or "units",
                confidence=min(0.9, float(item.get("confidence") or 0.6)),
                priority=80,
                dimensions=item.get("dimensions") or [],
                source="llm",
                provenance={"proposed_by": "llm", "validated_against_schema": True},
            )
        return list(merged.values())[:24]

    # ------------------------------------------------------------------
    def _clear(self, model, **cascades: bool) -> None:
        """Delete this run's rows for a model so a retry does not duplicate them."""
        if model is DataProfile:
            profiles = self.db.query(DataProfile).filter(DataProfile.run_id == self.run_id).all()
            for profile in profiles:
                self.db.query(DataProfileColumn).filter(
                    DataProfileColumn.profile_id == profile.id
                ).delete(synchronize_session=False)
            self.db.query(DataProfile).filter(DataProfile.run_id == self.run_id).delete(
                synchronize_session=False
            )
        elif model is DataQualityReport:
            reports = (
                self.db.query(DataQualityReport)
                .filter(DataQualityReport.run_id == self.run_id)
                .all()
            )
            for report in reports:
                self.db.query(DataQualityIssue).filter(
                    DataQualityIssue.report_id == report.id
                ).delete(synchronize_session=False)
            self.db.query(DataQualityReport).filter(
                DataQualityReport.run_id == self.run_id
            ).delete(synchronize_session=False)
        elif model is KPI:
            self.db.query(KPIResult).filter(KPIResult.run_id == self.run_id).delete(
                synchronize_session=False
            )
            self.db.query(Insight).filter(Insight.run_id == self.run_id).update(
                {Insight.kpi_id: None}, synchronize_session=False
            )
            self.db.query(DashboardWidget).filter(
                DashboardWidget.kpi_id.in_(
                    self.db.query(KPI.id).filter(KPI.run_id == self.run_id)
                )
            ).update({DashboardWidget.kpi_id: None}, synchronize_session=False)
            self.db.query(KPI).filter(KPI.run_id == self.run_id).delete(synchronize_session=False)
        elif model is SemanticModel:
            models = self.db.query(SemanticModel).filter(SemanticModel.run_id == self.run_id).all()
            for item in models:
                for child in (Dimension, Measure, Relationship):
                    self.db.query(child).filter(child.semantic_model_id == item.id).delete(
                        synchronize_session=False
                    )
            self.db.query(SemanticModel).filter(SemanticModel.run_id == self.run_id).delete(
                synchronize_session=False
            )
        elif model is DashboardDefinition:
            dashboards = (
                self.db.query(DashboardDefinition)
                .filter(DashboardDefinition.run_id == self.run_id)
                .all()
            )
            for dashboard in dashboards:
                self.db.query(DashboardWidget).filter(
                    DashboardWidget.dashboard_id == dashboard.id
                ).delete(synchronize_session=False)
            self.db.query(DashboardDefinition).filter(
                DashboardDefinition.run_id == self.run_id
            ).delete(synchronize_session=False)
        else:
            self.db.query(model).filter(model.run_id == self.run_id).delete(
                synchronize_session=False
            )
        self.db.flush()

    # ------------------------------------------------------------------
    def handlers(self) -> dict[str, Callable[[PipelineState], PipelineState]]:
        return {
            "orchestrator": self.orchestrator,
            "profiler": self.profiler,
            "quality": self.quality,
            "semantic": self.semantic,
            "analyst": self.analyst,
            "dashboard": self.dashboard,
            "auditor": self.auditor,
            "publish": self.publish,
        }

    def fail(self, error: str) -> None:
        self.run.status = "failed"
        self.run.error = error
        self.run.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        publish_event(str(self.run_id), "pipeline.failed", {"error": error})


# Ranking weights. A report of sixty mechanical observations is not an
# analysis; the point of the analyst agent is to decide what is worth saying.
MAX_INSIGHTS = 24
MAX_INSIGHTS_PER_KPI = 3
# The same rule firing on four correlated metrics restates one fact four times
# ("the UK dominates revenue, gross revenue, units and lines"). Keep the
# strongest couple and drop the echoes.
MAX_INSIGHTS_PER_RULE = 2
CATEGORY_WEIGHT = {
    "risk": 1.0,
    "anomaly": 0.9,
    "opportunity": 0.8,
    "trend": 0.6,
    "quality_caveat": 0.55,
    "finding": 0.4,
}
SEVERITY_WEIGHT = {"critical": 1.0, "warning": 0.75, "info": 0.4}


def _insight_score(insight: Insight) -> float:
    score = CATEGORY_WEIGHT.get(insight.category, 0.4) + SEVERITY_WEIGHT.get(insight.severity, 0.4)
    score += float(insight.confidence or 0) * 0.5
    # A finding that carries an action outranks one that only states a fact.
    if getattr(insight, "recommendation", None):
        score += 0.3
    # A 2% move is technically a trend and practically noise.
    comparison = insight.comparison or ""
    match = re.search(r"([-+]?\d+(?:\.\d+)?)%", comparison)
    if match:
        score += min(0.6, abs(float(match.group(1))) / 100)
    return score


def _rank_insights(insights: list[Insight]) -> list[Insight]:
    """Keep the strongest insights, spread across metrics.

    Without the per-KPI cap a single volatile metric crowds out every other
    finding, which is how an insight list becomes unreadable.
    """
    ordered = sorted(insights, key=_insight_score, reverse=True)
    kept: list[Insight] = []
    per_kpi: dict[Any, int] = {}
    per_rule: dict[str, int] = {}
    seen_titles: set[str] = set()
    for insight in ordered:
        title_key = insight.title.lower()
        if title_key in seen_titles:
            continue
        key = insight.kpi_id or insight.metric or id(insight)
        if per_kpi.get(key, 0) >= MAX_INSIGHTS_PER_KPI:
            continue
        basis = getattr(insight, "recommendation_basis", None)
        if basis and per_rule.get(basis, 0) >= MAX_INSIGHTS_PER_RULE:
            continue
        kept.append(insight)
        seen_titles.add(title_key)
        per_kpi[key] = per_kpi.get(key, 0) + 1
        if basis:
            per_rule[basis] = per_rule.get(basis, 0) + 1
        if len(kept) >= MAX_INSIGHTS:
            break
    return kept


def _humanize(value: Any) -> str:
    """Format a number the way a person writes it in a sentence.

    ``format(9601159.72, ",.4g")`` produces "9.601e+06", which is correct and
    unreadable. Insight text is prose, so it gets thousands separators and a
    decimal place only where one carries information.
    """
    number = _as_float(value)
    if number is None:
        return "n/a"
    magnitude = abs(number)
    if magnitude >= 1000:
        return f"{number:,.0f}"
    if magnitude >= 1:
        return f"{number:,.2f}".rstrip("0").rstrip(".")
    return f"{number:,.4g}"


def _next_period_start(start: datetime, grain: str) -> datetime:
    if grain == "hour":
        return start + timedelta(hours=1)
    if grain == "day":
        return start + timedelta(days=1)
    if grain == "month":
        return _add_months(start, 1)
    if grain == "quarter":
        return _add_months(start, 3)
    return _add_months(start, 12)


def _add_months(start: datetime, months: int) -> datetime:
    month_index = start.month - 1 + months
    year = start.year + month_index // 12
    month = month_index % 12 + 1
    return start.replace(year=year, month=month, day=1)


# A period is judged complete once the data reaches within one unit of its
# end. Without this tolerance the final period is flagged partial almost
# always: a month "ends" at midnight on the 1st of the next month, and a
# dataset whose last row is the 31st never contains that instant.
_COMPLETENESS_TOLERANCE = {
    "hour": timedelta(minutes=1),
    "day": timedelta(hours=1),
    "week": timedelta(days=1),
    "month": timedelta(days=1),
    "quarter": timedelta(days=1),
    "year": timedelta(days=1),
}


def _is_partial_period(period: Any, grain: str, last_observation: datetime | None) -> bool:
    """True when the data stops meaningfully before this bucket's period ends."""
    if last_observation is None:
        return False
    if isinstance(period, datetime):
        start = period
    else:
        try:
            start = datetime.combine(period, datetime.min.time())
        except (TypeError, ValueError):
            return False
    if start.tzinfo is not None:
        start = start.replace(tzinfo=None)
    reference = last_observation.replace(tzinfo=None) if last_observation.tzinfo else last_observation
    tolerance = _COMPLETENESS_TOLERANCE.get(grain, timedelta(days=1))
    return _next_period_start(start, grain) - tolerance > reference


def _complete_points(series: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Series points safe to compare against each other."""
    return [p for p in series if not p.get("partial") and p.get("value") is not None]


def _insight_grounded(item: dict[str, Any], evidence: list[dict[str, Any]]) -> bool:
    """An LLM insight is kept only if its metric and value match a computed one."""
    metric = (item.get("metric") or "").strip().lower()
    if not metric:
        return False
    value = _as_float(item.get("value"))
    for row in evidence:
        name = row["kpi"].lower()
        if metric != name and metric not in name and name not in metric:
            continue
        if value is None:
            return True
        actual = _as_float(row.get("value"))
        if actual is None:
            continue
        if actual == 0:
            return abs(value) < 1e-6
        return abs(value - actual) / abs(actual) < 0.05
    return False
