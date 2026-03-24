from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class ExecutionStage(Base, TimestampMixin):
    __tablename__ = "execution_stages"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("query_runs.id"), nullable=False, index=True)
    stage_no: Mapped[int] = mapped_column(nullable=False)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    engine_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    planning_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship(back_populates="execution_stages")
    run: Mapped["QueryRun"] = relationship(back_populates="stages")
    executed_sqls: Mapped[list["ExecutedSQL"]] = relationship(back_populates="stage", cascade="all, delete-orphan")
