from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CollaborationTask(Base, TimestampMixin):
    __tablename__ = "collaboration_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("collaboration_workflows.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False, default="REVIEW")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    assignee_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assignee_role: Mapped[str | None] = mapped_column(String(64), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    workflow: Mapped["CollaborationWorkflow"] = relationship(back_populates="tasks")
