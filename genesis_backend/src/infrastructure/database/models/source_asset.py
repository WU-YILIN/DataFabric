from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceAsset(Base, TimestampMixin):
    __tablename__ = "source_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    instance_id: Mapped[int] = mapped_column(ForeignKey("source_instances.id"), nullable=False, index=True)
    asset_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    qualified_name: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_asset_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCOVERED", index=True)
    heat_level: Mapped[str] = mapped_column(String(16), nullable=False, default="COLD", index=True)
    inferred_domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    schema_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    metrics_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="source_assets")
    instance: Mapped["SourceInstance"] = relationship(back_populates="assets")
    snapshots: Mapped[list["SourceAssetSnapshot"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    change_events: Mapped[list["SourceChangeEvent"]] = relationship(back_populates="asset")
    candidates: Mapped[list["SourceCandidate"]] = relationship(back_populates="asset")
    fields: Mapped[list["SourceField"]] = relationship(back_populates="asset", cascade="all, delete-orphan")
    semantic_candidates: Mapped[list["SemanticCandidate"]] = relationship(
        back_populates="asset",
        cascade="all, delete-orphan",
    )
