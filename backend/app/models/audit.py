from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class AuditEvent(TimestampMixin, Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info")
    message: Mapped[str] = mapped_column(Text)
    entity_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(40), default="recorded")


class XAIExplanation(TimestampMixin, Base):
    __tablename__ = "xai_explanations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(80))
    what_happened: Mapped[str] = mapped_column(Text)
    how_calculated: Mapped[str] = mapped_column(Text)
    data_used: Mapped[str] = mapped_column(Text)
    visualization_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    kpi_relevance: Mapped[str | None] = mapped_column(Text, nullable=True)
    assumptions: Mapped[str | None] = mapped_column(Text, nullable=True)
    quality_limitations: Mapped[str | None] = mapped_column(Text, nullable=True)
    transformations: Mapped[str | None] = mapped_column(Text, nullable=True)
    producer_agent: Mapped[str] = mapped_column(String(80))
    validator_agent: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)
