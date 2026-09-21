"""Interactive dashboard queries.

The pipeline precomputes each KPI once. A dashboard people actually use needs
to ask follow-up questions of the same metric: this quarter only, this country,
broken down by product rather than region.

Rather than let the browser send SQL, this endpoint recompiles the KPI's stored
formula and appends predicates built from a whitelisted filter grammar. Every
column is checked against the run's real schema, every literal is escaped, and
the finished statement still goes through the read-only SQL validator. The SQL
is returned with the result so a user can see exactly what produced a number.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.analytics.kpi_engine import FormulaError, compile_formula, quote_ident, quote_literal
from app.config import get_settings
from app.data.store import AnalyticalStore
from app.db.session import get_db
from app.models import (
    DataProfile,
    DataProfileColumn,
    Dataset,
    KPI,
    KPIResult,
    PipelineRun,
    Relationship,
    SemanticModel,
)

router = APIRouter()

FilterOp = Literal[
    "eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "between", "contains", "is_null", "not_null"
]

GRAINS = {"hour", "day", "week", "month", "quarter", "year"}
MAX_GROUPS = 200


class Filter(BaseModel):
    column: str = Field(..., description="Qualified as table.column")
    op: FilterOp = "eq"
    values: list[Any] = Field(default_factory=list)


class QueryRequest(BaseModel):
    kpi_slug: str
    dimension: str | None = Field(None, description="table.column to group by")
    grain: str | None = Field(None, description="Time grain when the dimension is a date")
    filters: list[Filter] = Field(default_factory=list)
    limit: int = 25


class QueryResponse(BaseModel):
    kpi: str
    unit: str | None
    rows: list[dict[str, Any]]
    sql: str
    filters_applied: list[str]
    additivity: str
    truncated: bool = False


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


def _run_schema(db: Session, run_id: UUID) -> dict[str, list[str]]:
    """Table -> columns for this run, taken from what the profiler recorded."""
    schema: dict[str, list[str]] = {}
    profiles = db.query(DataProfile).filter(DataProfile.run_id == run_id).all()
    for profile in profiles:
        dataset = db.get(Dataset, profile.dataset_id)
        if dataset is None:
            continue
        columns = (
            db.query(DataProfileColumn)
            .filter(DataProfileColumn.profile_id == profile.id)
            .all()
        )
        schema[dataset.table_name] = [c.name for c in columns]
    return schema


def _column_types(db: Session, run_id: UUID) -> dict[str, str]:
    types: dict[str, str] = {}
    for profile in db.query(DataProfile).filter(DataProfile.run_id == run_id).all():
        dataset = db.get(Dataset, profile.dataset_id)
        if dataset is None:
            continue
        for column in (
            db.query(DataProfileColumn).filter(DataProfileColumn.profile_id == profile.id).all()
        ):
            types[f"{dataset.table_name}.{column.name}"] = column.logical_type
    return types


def _resolve(reference: str, schema: dict[str, list[str]]) -> tuple[str, str]:
    """Validate a table.column reference against the run's real schema."""
    if "." not in reference:
        matches = [t for t, columns in schema.items() if reference in columns]
        if len(matches) != 1:
            raise HTTPException(400, f"Ambiguous or unknown column {reference!r}")
        return matches[0], reference
    table, column = reference.split(".", 1)
    if table not in schema:
        raise HTTPException(400, f"Unknown table {table!r}")
    if column not in schema[table]:
        raise HTTPException(400, f"Unknown column {reference!r}")
    return table, column


def _literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return repr(value)
    return quote_literal(str(value))


def _predicate(item: Filter, schema: dict[str, list[str]]) -> str:
    table, column = _resolve(item.column, schema)
    target = f"{quote_ident(table)}.{quote_ident(column)}"

    if item.op == "is_null":
        return f"{target} IS NULL"
    if item.op == "not_null":
        return f"{target} IS NOT NULL"
    if not item.values:
        raise HTTPException(400, f"Filter on {item.column} with op {item.op} needs a value")

    if item.op in {"in", "not_in"}:
        keyword = "IN" if item.op == "in" else "NOT IN"
        rendered = ", ".join(_literal(v) for v in item.values)
        return f"{target} {keyword} ({rendered})"
    if item.op == "between":
        if len(item.values) != 2:
            raise HTTPException(400, "between needs exactly two values")
        return f"{target} BETWEEN {_literal(item.values[0])} AND {_literal(item.values[1])}"
    if item.op == "contains":
        pattern = f"%{item.values[0]}%"
        return f"{target} LIKE {quote_literal(pattern)}"

    operators = {"eq": "=", "ne": "<>", "gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
    return f"{target} {operators[item.op]} {_literal(item.values[0])}"


def _store_for(run: PipelineRun) -> AnalyticalStore:
    directory = Path(get_settings().processed_dir) / str(run.id)
    if not directory.exists():
        raise HTTPException(
            409, "The processed data for this run is no longer on disk. Re-run the pipeline."
        )
    return AnalyticalStore(directory)


@router.post("/projects/{project_id}/query", response_model=QueryResponse)
def query_kpi(project_id: UUID, request: QueryRequest, db: Session = Depends(get_db)):
    """Recompute one KPI under user-chosen filters and grouping."""
    run = _latest_run(db, project_id)
    kpi = (
        db.query(KPI)
        .filter(KPI.run_id == run.id, KPI.slug == request.kpi_slug)
        .first()
    )
    if kpi is None:
        raise HTTPException(404, f"KPI {request.kpi_slug!r} not found in the latest run")
    if kpi.validation_status != "computed":
        raise HTTPException(409, f"KPI {kpi.name} did not compute ({kpi.validation_status})")

    schema = _run_schema(db, run.id)
    model = db.query(SemanticModel).filter(SemanticModel.run_id == run.id).first()
    joins = []
    if model is not None:
        joins = [
            {
                "source_table": r.source_table,
                "source_column": r.source_column,
                "target_table": r.target_table,
                "target_column": r.target_column,
            }
            for r in db.query(Relationship)
            .filter(Relationship.semantic_model_id == model.id, Relationship.validated.is_(True))
            .all()
        ]

    try:
        compiled = compile_formula(kpi.formula, joins, schema=schema)
    except FormulaError as exc:
        raise HTTPException(500, f"Stored formula no longer compiles: {exc}") from exc

    predicates = [_predicate(f, schema) for f in request.filters]
    where = " AND ".join(f"({p})" for p in predicates) if predicates else None

    if request.dimension:
        table, column = _resolve(request.dimension, schema)
        if table not in compiled.tables:
            raise HTTPException(
                400,
                f"{request.dimension} is not reachable from this KPI, which reads "
                f"{', '.join(compiled.tables)}.",
            )
        target = f"{quote_ident(table)}.{quote_ident(column)}"
        if request.grain:
            if request.grain not in GRAINS:
                raise HTTPException(400, f"Unsupported grain {request.grain!r}")
            target = f"date_trunc('{request.grain}', {target})"
            order = "1 ASC"
        else:
            order = "value DESC"
        limit = max(1, min(request.limit, MAX_GROUPS))
        sql = compiled.grouped_sql(
            target, alias="dimension", where=where, order_by=order, limit=limit + 1
        )
    else:
        sql = compiled.scalar_sql(where=where)
        limit = 1

    store = _store_for(run)
    try:
        frame = store.query(sql)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"Query failed: {exc}") from exc
    finally:
        store.close()

    rows = [
        {key: (str(value) if hasattr(value, "isoformat") else value) for key, value in row.items()}
        for row in frame.to_dicts()
    ]
    truncated = bool(request.dimension) and len(rows) > limit
    if truncated:
        rows = rows[:limit]

    return QueryResponse(
        kpi=kpi.name,
        unit=kpi.unit,
        rows=rows,
        sql=sql,
        filters_applied=predicates,
        additivity=(kpi.filters or {}).get("additivity", "additive"),
        truncated=truncated,
    )


@router.get("/projects/{project_id}/filter-options")
def filter_options(project_id: UUID, db: Session = Depends(get_db)):
    """Dimensions a user may filter or group by, with their available values.

    Only low-cardinality dimensions get a value list; offering 25,000 invoice
    numbers in a dropdown is not a filter, it is a denial of service.
    """
    run = _latest_run(db, project_id)
    schema = _run_schema(db, run.id)
    types = _column_types(db, run.id)
    model = db.query(SemanticModel).filter(SemanticModel.run_id == run.id).first()
    if model is None:
        raise HTTPException(404, "Semantic model not available yet")

    store = _store_for(run)
    options: list[dict[str, Any]] = []
    try:
        for dimension in model.dimensions:
            reference = f"{dimension.table_name}.{dimension.column_name}"
            if dimension.table_name not in schema:
                continue
            target = (
                f"{quote_ident(dimension.table_name)}.{quote_ident(dimension.column_name)}"
            )
            entry: dict[str, Any] = {
                "name": reference,
                "label": dimension.column_name,
                "table": dimension.table_name,
                "column": dimension.column_name,
                "type": dimension.dim_type,
                "logical_type": types.get(reference),
            }
            try:
                if dimension.dim_type == "datetime":
                    frame = store.query(
                        f"SELECT MIN({target}) AS min_value, MAX({target}) AS max_value "
                        f"FROM {quote_ident(dimension.table_name)}"
                    )
                    row = frame.to_dicts()[0] if frame.height else {}
                    entry["min"] = str(row.get("min_value")) if row.get("min_value") else None
                    entry["max"] = str(row.get("max_value")) if row.get("max_value") else None
                    entry["grains"] = ["day", "week", "month", "quarter", "year"]
                else:
                    frame = store.query(
                        f"SELECT {target} AS value, COUNT(*) AS n "
                        f"FROM {quote_ident(dimension.table_name)} "
                        f"WHERE {target} IS NOT NULL GROUP BY 1 ORDER BY n DESC LIMIT 100"
                    )
                    entry["values"] = [str(r["value"]) for r in frame.to_dicts()]
            except Exception:  # noqa: BLE001 - a dimension that cannot be listed is skipped
                continue
            options.append(entry)
    finally:
        store.close()

    kpis = (
        db.query(KPI)
        .filter(KPI.run_id == run.id, KPI.validation_status == "computed")
        .all()
    )
    return {
        "run_id": str(run.id),
        "dimensions": options,
        "kpis": [
            {
                "slug": k.slug,
                "name": k.name,
                "unit": k.unit,
                "additivity": (k.filters or {}).get("additivity", "additive"),
                "tables": k.data_sources,
                "format": (
                    db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first().filters or {}
                ).get("format", {})
                if db.query(KPIResult).filter(KPIResult.kpi_id == k.id).first()
                else {},
            }
            for k in kpis
        ],
    }
