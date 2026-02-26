from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class ReleaseChangeRequest(Base, TimestampMixin):
    __tablename__ = "release_change_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    change_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_APPROVAL")

    impact_scope: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    diff_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    before_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    after_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    risk_assessment_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    release_plan_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rollback_plan_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    current_approver_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="release_changes")
    project: Mapped["Project"] = relationship(back_populates="release_changes")
    history: Mapped[list["ReleaseChangeActionHistory"]] = relationship(
        back_populates="change_request", cascade="all, delete-orphan"
    )
