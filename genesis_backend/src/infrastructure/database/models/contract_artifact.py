from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class ContractArtifact(Base, TimestampMixin):
    __tablename__ = "contract_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracking_events.id"), nullable=True, index=True
    )

    event_code: Mapped[str] = mapped_column(String(255), nullable=False)
    contract_name: Mapped[str] = mapped_column(String(255), nullable=False)
    serving_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLISHED")
    approved_rule_count: Mapped[int] = mapped_column(nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="contract_artifacts")
    event: Mapped["TrackingEvent"] = relationship()

    __table_args__ = (
        Index("uq_contract_artifact_scope", "project_id", "event_id", unique=True),
    )
