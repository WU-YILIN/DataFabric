from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class IngestionEventLog(Base, TimestampMixin):
    __tablename__ = "ingestion_event_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("ingestion_channel_configs.id"), nullable=False)

    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    event_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reason_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sdk_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    channel: Mapped["IngestionChannelConfig"] = relationship(back_populates="event_logs")
    project: Mapped["Project"] = relationship(back_populates="ingestion_event_logs")
