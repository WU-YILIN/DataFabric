from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceCandidate(Base, TimestampMixin):
    __tablename__ = "source_candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("source_instances.id"), nullable=False, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("source_assets.id"), nullable=True, index=True)
    change_event_id: Mapped[int | None] = mapped_column(ForeignKey("source_change_events.id"), nullable=True, index=True)
    candidate_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    recommendation: Mapped[str | None] = mapped_column(String(64), nullable=True)
    memory_scope_target: Mapped[str] = mapped_column(String(32), nullable=False, default="PRIVATE")
    action_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="source_candidates")
    instance: Mapped["SourceInstance"] = relationship(back_populates="candidates")
    asset: Mapped[Optional["SourceAsset"]] = relationship(back_populates="candidates")
    change_event: Mapped[Optional["SourceChangeEvent"]] = relationship(back_populates="candidates")
