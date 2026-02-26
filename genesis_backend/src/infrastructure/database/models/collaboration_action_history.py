from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CollaborationActionHistory(Base, TimestampMixin):
    __tablename__ = "collaboration_action_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("collaboration_workflows.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    workflow: Mapped["CollaborationWorkflow"] = relationship(back_populates="action_history")
