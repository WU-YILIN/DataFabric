from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceChangeEvent(Base, TimestampMixin):
    __tablename__ = "source_change_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("source_instances.id"), nullable=False, index=True)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("source_assets.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    brief_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="source_change_events")
    instance: Mapped["SourceInstance"] = relationship(back_populates="change_events")
    asset: Mapped[Optional["SourceAsset"]] = relationship(back_populates="change_events")
    candidates: Mapped[list["SourceCandidate"]] = relationship(back_populates="change_event")
