from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class SourceInstance(Base, TimestampMixin):
    __tablename__ = "source_instances"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    connector_definition_id: Mapped[int] = mapped_column(ForeignKey("connector_definitions.id"), nullable=False, index=True)
    legacy_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    instance_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    memory_scope_default: Mapped[str] = mapped_column(String(32), nullable=False, default="PRIVATE")
    encrypted_config: Mapped[str] = mapped_column(String(8000), nullable=False, default="")
    last_test_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_test_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_discover_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_discover_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_watch_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_watch_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_watched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watch_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    watch_interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    watch_next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    watch_last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watch_last_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    watch_failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_brief_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_brief_summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    last_brief_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="source_instances")
    connector_definition: Mapped["ConnectorDefinition"] = relationship()
    assets: Mapped[list["SourceAsset"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    fields: Mapped[list["SourceField"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    change_events: Mapped[list["SourceChangeEvent"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    candidates: Mapped[list["SourceCandidate"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    semantic_candidates: Mapped[list["SemanticCandidate"]] = relationship(
        back_populates="instance",
        cascade="all, delete-orphan",
    )
    sync_runs: Mapped[list["SourceSyncRun"]] = relationship(back_populates="instance", cascade="all, delete-orphan")
    telemetry_samples: Mapped[list["SourceTelemetrySample"]] = relationship(
        back_populates="instance", cascade="all, delete-orphan"
    )
