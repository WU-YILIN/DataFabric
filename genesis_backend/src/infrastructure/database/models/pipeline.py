from enum import Enum
from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, JSON, String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class PipelineStatus(str, Enum):
    PENDING = "PENDING"
    PROVISIONING = "PROVISIONING"
    RUNNING = "RUNNING"
    FAILED = "FAILED"
    ROLLING_BACK = "ROLLING_BACK"
    STOPPED = "STOPPED"


class Pipeline(Base, TimestampMixin):
    __tablename__ = "pipelines"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    event_code: Mapped[str] = mapped_column(String(100), nullable=False)
    topic_name: Mapped[str] = mapped_column(String(255), nullable=False)
    flink_job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default=PipelineStatus.PENDING.value, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship(back_populates="pipelines")
    status_history: Mapped[list["PipelineStatusHistory"]] = relationship(
        back_populates="pipeline", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<Pipeline(id={self.id}, project_id={self.project_id}, "
            f"event_code='{self.event_code}', status='{self.status}')>"
        )
