from sqlalchemy import Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class GovernanceCheck(Base, TimestampMixin):
    __tablename__ = "governance_checks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("tracking_events.id"), nullable=True)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    reasoning: Mapped[str] = mapped_column(String(2000), nullable=False)
    recommended_code: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, default="gpt-4o-mini")
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    result_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)

    project: Mapped["Project"] = relationship()

    def __repr__(self) -> str:
        return (
            f"<GovernanceCheck(id={self.id}, project_id={self.project_id}, "
            f"event_name='{self.event_name}', verdict='{self.verdict}')>"
        )
