from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class MaterializationArtifact(Base, TimestampMixin):
    __tablename__ = "materialization_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("query_plans.id"), nullable=True, index=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("query_runs.id"), nullable=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    artifact_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECOMMENDED", index=True)
    heat_level: Mapped[str] = mapped_column(String(16), nullable=False, default="COLD", index=True)
    engine_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    storage_strategy: Mapped[str | None] = mapped_column(String(128), nullable=True)
    retention_policy: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_accessed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="materialization_artifacts")
    plan: Mapped["QueryPlan"] = relationship(back_populates="materialization_artifacts")
    run: Mapped["QueryRun"] = relationship(back_populates="materialization_artifacts")
