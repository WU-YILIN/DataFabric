from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base


class SourceFieldProfile(Base):
    __tablename__ = "source_field_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("source_fields.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("source_assets.id"), nullable=False, index=True)
    snapshot_id: Mapped[int | None] = mapped_column(ForeignKey("source_asset_snapshots.id"), nullable=True, index=True)
    null_ratio: Mapped[float] = mapped_column(nullable=False, default=0.0)
    distinct_ratio: Mapped[float] = mapped_column(nullable=False, default=0.0)
    sample_values: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    min_value: Mapped[str | None] = mapped_column(nullable=True)
    max_value: Mapped[str | None] = mapped_column(nullable=True)
    observed_row_count: Mapped[int] = mapped_column(nullable=False, default=0)
    profile_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    profiled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="source_field_profiles")
    field: Mapped["SourceField"] = relationship(back_populates="profiles")
    asset: Mapped["SourceAsset"] = relationship()
