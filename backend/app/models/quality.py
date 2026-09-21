from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DataQualityReport(TimestampMixin, Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=True)
    overall_score: Mapped[float] = mapped_column(Float)
    completeness: Mapped[float] = mapped_column(Float)
    uniqueness: Mapped[float] = mapped_column(Float)
    consistency: Mapped[float] = mapped_column(Float)
    validity: Mapped[float] = mapped_column(Float)
    referential_integrity: Mapped[float] = mapped_column(Float)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    issues = relationship("DataQualityIssue", back_populates="report", cascade="all, delete-orphan")


class DataQualityIssue(TimestampMixin, Base):
    __tablename__ = "data_quality_issues"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("data_quality_reports.id"), index=True)
    severity: Mapped[str] = mapped_column(String(20))
    issue_type: Mapped[str] = mapped_column(String(80))
    table_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    column_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    rows_affected: Mapped[int] = mapped_column(Integer, default=0)
    detection_method: Mapped[str] = mapped_column(String(120))
    recommended_action: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="open")
    evidence: Mapped[dict] = mapped_column(JSONB, default=dict)

    report = relationship("DataQualityReport", back_populates="issues")


class Transformation(TimestampMixin, Base):
    __tablename__ = "transformations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    dataset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=True)
    table_name: Mapped[str] = mapped_column(String(200))
    column_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    operation: Mapped[str] = mapped_column(String(80))
    rows_affected: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text)
    before_example: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_example: Mapped[str | None] = mapped_column(Text, nullable=True)
    parameters: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="applied")
