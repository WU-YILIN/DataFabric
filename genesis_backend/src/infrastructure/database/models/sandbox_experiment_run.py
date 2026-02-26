from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SandboxExperimentRun(Base, TimestampMixin):
    __tablename__ = "sandbox_experiment_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    experiment_id: Mapped[int] = mapped_column(ForeignKey("sandbox_experiments.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    run_no: Mapped[int] = mapped_column(nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False)
    triggered_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(nullable=True)
    run_context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    report_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    recommendation_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    experiment: Mapped["SandboxExperiment"] = relationship(back_populates="runs")
