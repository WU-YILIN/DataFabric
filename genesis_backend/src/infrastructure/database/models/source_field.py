from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceField(Base, TimestampMixin):
    __tablename__ = "source_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("source_instances.id"), nullable=False, index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("source_assets.id"), nullable=False, index=True)
    field_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    physical_type: Mapped[str] = mapped_column(String(128), nullable=False, default="TEXT")
    nullable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCOVERED", index=True)
    is_partition_key: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_primary_key_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_time_field_candidate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    discovered_from_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_asset_snapshots.id"),
        nullable=True,
        index=True,
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="source_fields")
    instance: Mapped["SourceInstance"] = relationship(back_populates="fields")
    asset: Mapped["SourceAsset"] = relationship(back_populates="fields")
    profiles: Mapped[list["SourceFieldProfile"]] = relationship(
        back_populates="field",
        cascade="all, delete-orphan",
    )
    semantic_candidates: Mapped[list["SemanticCandidate"]] = relationship(
        back_populates="field",
        cascade="all, delete-orphan",
    )
