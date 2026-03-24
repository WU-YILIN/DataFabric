from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceAssetSnapshot(Base, TimestampMixin):
    __tablename__ = "source_asset_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("source_instances.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("source_assets.id"), nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCOVERY")
    schema_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stats_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    asset: Mapped["SourceAsset"] = relationship(back_populates="snapshots")
