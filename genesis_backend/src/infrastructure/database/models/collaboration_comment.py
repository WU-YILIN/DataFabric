from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CollaborationComment(Base, TimestampMixin):
    __tablename__ = "collaboration_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    workflow_id: Mapped[int] = mapped_column(ForeignKey("collaboration_workflows.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    mentions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    workflow: Mapped["CollaborationWorkflow"] = relationship(back_populates="comments")
