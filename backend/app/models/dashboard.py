from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DashboardDefinition(TimestampMixin, Base):
    __tablename__ = "dashboard_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    title: Mapped[str] = mapped_column(String(300))
    layout: Mapped[dict] = mapped_column(JSONB, default=dict)
    published: Mapped[bool] = mapped_column(Boolean, default=False)
    audit_status: Mapped[str] = mapped_column(String(40), default="pending")
    version: Mapped[int] = mapped_column(Integer, default=1)

    widgets = relationship("DashboardWidget", back_populates="dashboard", cascade="all, delete-orphan")


class DashboardWidget(TimestampMixin, Base):
    __tablename__ = "dashboard_widgets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("dashboard_definitions.id"), index=True
    )
    widget_type: Mapped[str] = mapped_column(String(40))
    title: Mapped[str] = mapped_column(String(300))
    data_source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    query_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    kpi_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=True)
    dimensions: Mapped[list] = mapped_column(JSONB, default=list)
    measures: Mapped[list] = mapped_column(JSONB, default=list)
    filters: Mapped[dict] = mapped_column(JSONB, default=dict)
    format: Mapped[dict] = mapped_column(JSONB, default=dict)
    position_x: Mapped[int] = mapped_column(Integer, default=0)
    position_y: Mapped[int] = mapped_column(Integer, default=0)
    width: Mapped[int] = mapped_column(Integer, default=4)
    height: Mapped[int] = mapped_column(Integer, default=2)
    data: Mapped[dict] = mapped_column(JSONB, default=dict)
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)

    dashboard = relationship("DashboardDefinition", back_populates="widgets")
