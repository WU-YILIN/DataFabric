from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class IngestionChannelConfig(Base, TimestampMixin):
    __tablename__ = "ingestion_channel_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    app_name: Mapped[str] = mapped_column(String(255), nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")

    app_id: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    ingest_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    endpoint_domain: Mapped[str] = mapped_column(String(255), nullable=False)
    endpoint_path: Mapped[str] = mapped_column(String(255), nullable=False, default="/api/v1/ingestion/gateway/events")
    auth_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="HEADER_KEY")

    sampling_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="ALL")
    sampling_rate: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    switches_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    blocked_events: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    sdk_version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0.0")
    sdk_config_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    quickstart_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    accepted_events_count: Mapped[int] = mapped_column(nullable=False, default=0)
    rejected_events_count: Mapped[int] = mapped_column(nullable=False, default=0)

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="ingestion_channels")
    project: Mapped["Project"] = relationship(back_populates="ingestion_channels")
    event_logs: Mapped[list["IngestionEventLog"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )
