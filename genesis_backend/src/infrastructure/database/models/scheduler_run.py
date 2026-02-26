from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SchedulerRun(Base, TimestampMixin):
    __tablename__ = "scheduler_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    dag_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dags.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    trigger_source: Mapped[str] = mapped_column(String(32), nullable=False, default="MANUAL")
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False, default="system")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    run_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="scheduler_runs")
    dag: Mapped["SchedulerDag"] = relationship(back_populates="runs")
    node_runs: Mapped[list["SchedulerNodeRun"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SchedulerRun(id={self.id}, dag_id={self.dag_id}, status='{self.status}')>"
