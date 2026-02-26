from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CollaborationWorkflow(Base, TimestampMixin):
    __tablename__ = "collaboration_workflows"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(nullable=True)
    workflow_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_APPROVAL")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    initiator_id: Mapped[str] = mapped_column(String(255), nullable=False)
    initiator_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    current_assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    current_assignee_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    context_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    outcome: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="collaboration_workflows")
    tasks: Mapped[list["CollaborationTask"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    comments: Mapped[list["CollaborationComment"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
    action_history: Mapped[list["CollaborationActionHistory"]] = relationship(
        back_populates="workflow", cascade="all, delete-orphan"
    )
