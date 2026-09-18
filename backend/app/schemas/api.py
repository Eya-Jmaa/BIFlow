from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str
    business_objective: str
    description: str | None = None
    domain: str = "general"


class ProjectOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    business_objective: str
    domain: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DatasetOut(BaseModel):
    id: UUID
    name: str
    table_name: str
    layer: str
    source_type: str
    row_count: int | None
    column_count: int | None
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineRunOut(BaseModel):
    id: UUID
    project_id: UUID
    status: str
    business_objective: str
    current_step: str | None
    llm_provider: str | None
    llm_model: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class PipelineStepOut(BaseModel):
    id: UUID
    name: str
    display_name: str
    status: str
    sequence: int
    duration_ms: int | None
    output_summary: dict = Field(default_factory=dict)
    error: str | None

    model_config = {"from_attributes": True}


class KPIOut(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str
    business_meaning: str
    formula: str
    unit: str | None
    confidence: float
    validation_status: str
    query_sql: str | None
    value: float | None = None
    previous_value: float | None = None
    change_pct: float | None = None

    model_config = {"from_attributes": True}


class InsightOut(BaseModel):
    id: UUID
    title: str
    description: str
    category: str
    evidence: dict
    metric: str | None
    value: float | None
    comparison: str | None
    period: str | None
    severity: str
    confidence: float
    query_sql: str | None
    grounded: bool

    model_config = {"from_attributes": True}


class WidgetOut(BaseModel):
    id: UUID
    widget_type: str
    title: str
    query_sql: str | None
    kpi_id: UUID | None
    dimensions: list
    measures: list
    format: dict
    position_x: int
    position_y: int
    width: int
    height: int
    data: dict
    explanation: str | None

    model_config = {"from_attributes": True}


class DashboardOut(BaseModel):
    id: UUID
    title: str
    layout: dict
    published: bool
    audit_status: str
    widgets: list[WidgetOut]

    model_config = {"from_attributes": True}


class QualityIssueOut(BaseModel):
    id: UUID
    severity: str
    issue_type: str
    table_name: str | None
    column_name: str | None
    rows_affected: int
    detection_method: str
    recommended_action: str
    status: str
    evidence: dict

    model_config = {"from_attributes": True}


class QualityReportOut(BaseModel):
    id: UUID
    overall_score: float
    completeness: float
    uniqueness: float
    consistency: float
    validity: float
    referential_integrity: float
    summary: str | None
    issues: list[QualityIssueOut]

    model_config = {"from_attributes": True}
