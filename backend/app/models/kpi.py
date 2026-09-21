from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class KPI(TimestampMixin, Base):
    __tablename__ = "kpis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    semantic_model_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_models.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str] = mapped_column(Text)
    business_meaning: Mapped[str] = mapped_column(Text)
    formula: Mapped[str] = mapped_column(Text)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    dimensions: Mapped[list] = mapped_column(JSONB, default=list)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    data_sources: Mapped[list] = mapped_column(JSONB, default=list)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    validation_status: Mapped[str] = mapped_column(String(40), default="pending")
    query_sql: Mapped[str | None] = mapped_column(Text, nullable=True)

    results = relationship("KPIResult", back_populates="kpi", cascade="all, delete-orphan")


class KPIResult(TimestampMixin, Base):
    __tablename__ = "kpi_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    kpi_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("kpis.id"), index=True)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    computed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    query_sql: Mapped[str] = mapped_column(Text)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    breakdown: Mapped[list] = mapped_column(JSONB, default=list)
    time_series: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(40), default="computed")
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    kpi = relationship("KPI", back_populates="results")
