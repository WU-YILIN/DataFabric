from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SemanticCandidate(Base, TimestampMixin):
    __tablename__ = "semantic_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int | None] = mapped_column(ForeignKey("source_instances.id"), nullable=True, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("source_assets.id"), nullable=True, index=True)
    field_id: Mapped[int | None] = mapped_column(ForeignKey("source_fields.id"), nullable=True, index=True)
    object_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    candidate_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    candidate_value: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    reasoning: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    evidence_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="semantic_candidates")
    instance: Mapped["SourceInstance"] = relationship(back_populates="semantic_candidates")
    asset: Mapped["SourceAsset"] = relationship(back_populates="semantic_candidates")
    field: Mapped["SourceField"] = relationship(back_populates="semantic_candidates")
