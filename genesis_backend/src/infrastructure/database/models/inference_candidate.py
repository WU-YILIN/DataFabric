from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class InferenceCandidate(Base, TimestampMixin):
    __tablename__ = "inference_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracking_events.id"), nullable=True, index=True
    )
    mapping_id: Mapped[int | None] = mapped_column(
        ForeignKey("schema_field_mappings.id"), nullable=True, index=True
    )

    candidate_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PENDING")
    target_field: Mapped[str] = mapped_column(String(128), nullable=False)
    source_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    field_frequency: Mapped[int] = mapped_column(nullable=False, default=0)
    proposed_by: Mapped[str] = mapped_column(String(64), nullable=False, default="scanner")
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW")
    last_observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="inference_candidates")
    event: Mapped["TrackingEvent"] = relationship()
    mapping: Mapped["SchemaFieldMapping"] = relationship()

    __table_args__ = (
        Index("uq_inference_candidate_mapping", "project_id", "mapping_id", unique=True),
    )
