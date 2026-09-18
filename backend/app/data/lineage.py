from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LineageNode(BaseModel):
    id: str
    type: str
    label: str
    details: dict[str, Any] = Field(default_factory=dict)


class LineageEdge(BaseModel):
    source: str
    target: str
    label: str


class LineageGraph(BaseModel):
    nodes: list[LineageNode]
    edges: list[LineageEdge]


def kpi_lineage(
    *,
    run_id: str,
    kpi_name: str,
    formula: str,
    query_sql: str,
    tables: list[str],
    columns: list[str],
    transformations: list[str],
    widget_title: str | None = None,
) -> LineageGraph:
    nodes = [
        LineageNode(id="run", type="pipeline_run", label=f"Run {run_id[:8]}"),
        LineageNode(id="raw", type="layer", label="RAW"),
        LineageNode(id="transform", type="transformation", label="TRANSFORM", details={"steps": transformations}),
        LineageNode(id="clean", type="layer", label="CLEAN"),
        LineageNode(id="semantic", type="semantic", label="SEMANTIC MODEL"),
        LineageNode(id="kpi", type="kpi", label=kpi_name, details={"formula": formula, "sql": query_sql, "tables": tables, "columns": columns}),
    ]
    edges = [
        LineageEdge(source="raw", target="transform", label="profiled"),
        LineageEdge(source="transform", target="clean", label="applied"),
        LineageEdge(source="clean", target="semantic", label="modeled"),
        LineageEdge(source="semantic", target="kpi", label="computed"),
        LineageEdge(source="run", target="raw", label="input"),
    ]
    if widget_title:
        nodes.append(LineageNode(id="chart", type="widget", label=widget_title))
        edges.append(LineageEdge(source="kpi", target="chart", label="visualized"))
    return LineageGraph(nodes=nodes, edges=edges)
