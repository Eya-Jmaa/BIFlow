from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, String
from app.db.types import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EvaluationResult(TimestampMixin, Base):
    __tablename__ = "evaluation_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id"), index=True)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    metric_name: Mapped[str] = mapped_column(String(120))
    score: Mapped[float] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
