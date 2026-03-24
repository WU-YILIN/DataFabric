from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class ObservationSourceProfile(Base, TimestampMixin):
    __tablename__ = "observation_source_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_channel_configs.id"), nullable=True, index=True
    )

    event_name: Mapped[str] = mapped_column(String(255), nullable=False)
    heat: Mapped[str] = mapped_column(String(16), nullable=False, default="COLD")
    total_events: Mapped[int] = mapped_column(nullable=False, default=0)
    accepted_events: Mapped[int] = mapped_column(nullable=False, default=0)
    sdk_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    profile_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="observation_source_profiles")
    channel: Mapped["IngestionChannelConfig"] = relationship()

    __table_args__ = (
        Index(
            "uq_observation_source_profile_scope",
            "project_id",
            "channel_id",
            "event_name",
            unique=True,
        ),
    )
