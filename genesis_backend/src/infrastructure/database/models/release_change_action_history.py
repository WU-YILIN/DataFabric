from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class ReleaseChangeActionHistory(Base, TimestampMixin):
    __tablename__ = "release_change_action_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    change_request_id: Mapped[int] = mapped_column(ForeignKey("release_change_requests.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    change_request: Mapped["ReleaseChangeRequest"] = relationship(back_populates="history")
