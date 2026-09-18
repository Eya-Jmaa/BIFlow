from __future__ import annotations

from typing import Any, TypedDict


class PipelineState(TypedDict, total=False):
    project_id: str
    run_id: str
    business_objective: str
    domain: str
    datasets: list[dict[str, Any]]
    profiles: list[dict[str, Any]]
    quality_report: dict[str, Any]
    etl_plan: dict[str, Any]
    transformations: list[dict[str, Any]]
    joins: list[dict[str, Any]]
    semantic_model: dict[str, Any]
    kpis: list[dict[str, Any]]
    kpi_results: list[dict[str, Any]]
    analysis: dict[str, Any]
    insights: list[dict[str, Any]]
    dashboard: dict[str, Any]
    audit: dict[str, Any]
    errors: list[str]
    warnings: list[str]
    status: str
    retry: dict[str, int]
    parquet_dir: str
