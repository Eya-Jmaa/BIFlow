from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    business_objective: Mapped[str] = mapped_column(Text)
    domain: Mapped[str] = mapped_column(String(80), default="general")
    status: Mapped[str] = mapped_column(String(40), default="draft")

    datasets = relationship("Dataset", back_populates="project", cascade="all, delete-orphan")
    pipeline_runs = relationship("PipelineRun", back_populates="project", cascade="all, delete-orphan")
