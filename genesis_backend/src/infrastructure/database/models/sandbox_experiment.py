from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SandboxExperiment(Base, TimestampMixin):
    __tablename__ = "sandbox_experiments"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(nullable=True)
    experiment_type: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sandbox_source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sandbox_source_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    config_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    baseline_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    best_candidate_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    conclusion: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    promote_target_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    promote_target_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="sandbox_experiments")
    runs: Mapped[list["SandboxExperimentRun"]] = relationship(
        back_populates="experiment",
        cascade="all, delete-orphan",
    )
