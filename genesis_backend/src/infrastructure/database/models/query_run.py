from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class QueryRun(Base, TimestampMixin):
    __tablename__ = "query_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    intent_id: Mapped[int] = mapped_column(ForeignKey("query_intents.id"), nullable=False, index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("query_plans.id"), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    execution_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="DIRECT")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    current_stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="query_runs")
    intent: Mapped["QueryIntent"] = relationship(back_populates="runs")
    plan: Mapped["QueryPlan"] = relationship(back_populates="runs")
    stages: Mapped[list["ExecutionStage"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    executed_sqls: Mapped[list["ExecutedSQL"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    materialization_artifacts: Mapped[list["MaterializationArtifact"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
