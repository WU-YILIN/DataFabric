from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceSyncRun(Base, TimestampMixin):
    __tablename__ = "source_sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("source_instances.id"), nullable=False, index=True)
    run_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    trigger_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    brief_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    brief_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    brief_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="source_sync_runs")
    instance: Mapped["SourceInstance"] = relationship(back_populates="sync_runs")
