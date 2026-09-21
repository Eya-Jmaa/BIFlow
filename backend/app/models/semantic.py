from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class SemanticModel(TimestampMixin, Base):
    __tablename__ = "semantic_models"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    domain: Mapped[str] = mapped_column(String(80), default="general")
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    grain: Mapped[str | None] = mapped_column(String(200), nullable=True)

    dimensions = relationship("Dimension", back_populates="semantic_model", cascade="all, delete-orphan")
    measures = relationship("Measure", back_populates="semantic_model", cascade="all, delete-orphan")
    relationships = relationship("Relationship", back_populates="semantic_model", cascade="all, delete-orphan")


class Dimension(TimestampMixin, Base):
    __tablename__ = "dimensions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_models.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    table_name: Mapped[str] = mapped_column(String(200))
    column_name: Mapped[str] = mapped_column(String(300))
    dim_type: Mapped[str] = mapped_column(String(40))
    grain: Mapped[str | None] = mapped_column(String(80), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    semantic_model = relationship("SemanticModel", back_populates="dimensions")


class Measure(TimestampMixin, Base):
    __tablename__ = "measures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_models.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200))
    table_name: Mapped[str] = mapped_column(String(200))
    column_name: Mapped[str] = mapped_column(String(300))
    aggregation: Mapped[str] = mapped_column(String(40), default="SUM")
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    semantic_model = relationship("SemanticModel", back_populates="measures")


class Relationship(TimestampMixin, Base):
    __tablename__ = "relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    semantic_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_models.id"), index=True
    )
    source_table: Mapped[str] = mapped_column(String(200))
    source_column: Mapped[str] = mapped_column(String(300))
    target_table: Mapped[str] = mapped_column(String(200))
    target_column: Mapped[str] = mapped_column(String(300))
    cardinality: Mapped[str] = mapped_column(String(40))
    confidence: Mapped[float] = mapped_column(Float)
    validated: Mapped[bool] = mapped_column(default=False)
    overlap_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    extra: Mapped[dict] = mapped_column(JSONB, default=dict)

    semantic_model = relationship("SemanticModel", back_populates="relationships")
