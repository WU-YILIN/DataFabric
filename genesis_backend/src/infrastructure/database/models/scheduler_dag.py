from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SchedulerDag(Base, TimestampMixin):
    __tablename__ = "scheduler_dags"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    trigger_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    cron_expr: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    dependency_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="ALL_SUCCESS")
    retry_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schedule_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")
    last_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="scheduler_dags")
    nodes: Mapped[list["SchedulerDagNode"]] = relationship(
        back_populates="dag", cascade="all, delete-orphan"
    )
    edges: Mapped[list["SchedulerDagEdge"]] = relationship(
        back_populates="dag", cascade="all, delete-orphan"
    )
    runs: Mapped[list["SchedulerRun"]] = relationship(back_populates="dag", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<SchedulerDag(id={self.id}, project_id={self.project_id}, name='{self.name}')>"
