from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class DataProfile(TimestampMixin, Base):
    __tablename__ = "data_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dataset_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("datasets.id"), index=True)
    run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), nullable=True)
    row_count: Mapped[int] = mapped_column(Integer)
    column_count: Mapped[int] = mapped_column(Integer)
    quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    duplicate_row_count: Mapped[int] = mapped_column(Integer, default=0)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)
    relationships_found: Mapped[list] = mapped_column(JSONB, default=list)
    pii_flags: Mapped[list] = mapped_column(JSONB, default=list)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    columns = relationship("DataProfileColumn", back_populates="profile", cascade="all, delete-orphan")


class DataProfileColumn(TimestampMixin, Base):
    __tablename__ = "data_profile_columns"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("data_profiles.id"), index=True)
    name: Mapped[str] = mapped_column(String(300))
    inferred_type: Mapped[str] = mapped_column(String(80))
    logical_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    null_count: Mapped[int] = mapped_column(Integer, default=0)
    null_pct: Mapped[float] = mapped_column(Float, default=0)
    distinct_count: Mapped[int] = mapped_column(Integer, default=0)
    uniqueness_pct: Mapped[float] = mapped_column(Float, default=0)
    is_candidate_pk: Mapped[bool] = mapped_column(default=False)
    is_candidate_fk: Mapped[bool] = mapped_column(default=False)
    semantic_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    stats: Mapped[dict] = mapped_column(JSONB, default=dict)
    warnings: Mapped[list] = mapped_column(JSONB, default=list)

    profile = relationship("DataProfile", back_populates="columns")
