from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class ExecutedSQL(Base, TimestampMixin):
    __tablename__ = "executed_sqls"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("query_runs.id"), nullable=False, index=True)
    stage_id: Mapped[int | None] = mapped_column(ForeignKey("execution_stages.id"), nullable=True, index=True)
    engine_key: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_role: Mapped[str] = mapped_column(String(64), nullable=False, default="PREPARED")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    sql_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    metrics_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="executed_sqls")
    run: Mapped["QueryRun"] = relationship(back_populates="executed_sqls")
    stage: Mapped["ExecutionStage"] = relationship(back_populates="executed_sqls")
