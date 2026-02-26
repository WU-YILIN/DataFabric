from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class EventChangeLog(Base, TimestampMixin):
    __tablename__ = "event_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("tracking_events.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    from_version: Mapped[str] = mapped_column(String(20), nullable=False)
    to_version: Mapped[str] = mapped_column(String(20), nullable=False)
    diff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)

    event: Mapped["TrackingEvent"] = relationship(back_populates="changes")

    def __repr__(self) -> str:
        return (
            f"<EventChangeLog(id={self.id}, event_id={self.event_id}, "
            f"from='{self.from_version}', to='{self.to_version}')>"
        )
