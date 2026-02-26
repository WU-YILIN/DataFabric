from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SchedulerNodeRun(Base, TimestampMixin):
    __tablename__ = "scheduler_node_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("scheduler_runs.id"), nullable=False)
    dag_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dags.id"), nullable=False)
    node_id: Mapped[int] = mapped_column(ForeignKey("scheduler_dag_nodes.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    attempt: Mapped[int] = mapped_column(nullable=False, default=1)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    log_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    upstream_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    run: Mapped["SchedulerRun"] = relationship(back_populates="node_runs")
    dag: Mapped["SchedulerDag"] = relationship("SchedulerDag")
    node: Mapped["SchedulerDagNode"] = relationship(back_populates="run_records")

    def __repr__(self) -> str:
        return (
            f"<SchedulerNodeRun(id={self.id}, run_id={self.run_id}, "
            f"node_id={self.node_id}, status='{self.status}')>"
        )
