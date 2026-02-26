from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class IncidentTimelineEntry(Base, TimestampMixin):
    __tablename__ = "incident_timeline_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    incident_id: Mapped[int] = mapped_column(ForeignKey("incident_cases.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    incident: Mapped["IncidentCase"] = relationship(back_populates="timeline")

