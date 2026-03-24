from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class GovernanceDecisionRecord(Base, TimestampMixin):
    __tablename__ = "governance_decision_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracking_events.id"), nullable=True, index=True
    )
    mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("schema_field_mappings.id"), nullable=True, index=True
    )

    target_field: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    queue_status: Mapped[str] = mapped_column(String(16), nullable=False, default="OPEN")
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    field_frequency: Mapped[int] = mapped_column(nullable=False, default=0)
    recommended_action: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW")
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="governance_decision_records")
    event: Mapped["TrackingEvent"] = relationship()
    mapping: Mapped["SchemaFieldMapping"] = relationship()

    __table_args__ = (
        Index("uq_governance_record_mapping", "project_id", "mapping_id", unique=True),
    )
