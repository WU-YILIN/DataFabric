from typing import Optional

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataQualityRule(Base, TimestampMixin):
    __tablename__ = "data_quality_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    event_id: Mapped[int] = mapped_column(ForeignKey("tracking_events.id"), nullable=False)
    asset_id: Mapped[int | None] = mapped_column(ForeignKey("data_assets.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_field: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    operator: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    threshold: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    alert_channels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")

    project: Mapped["Project"] = relationship(back_populates="data_quality_rules")
    event: Mapped["TrackingEvent"] = relationship(back_populates="data_quality_rules")
    asset: Mapped["DataAsset"] = relationship(back_populates="data_quality_rules")
    executions: Mapped[list["DataQualityExecutionLog"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )
    changes: Mapped[list["DataQualityRuleChangeLog"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<DataQualityRule(id={self.id}, project_id={self.project_id}, "
            f"event_id={self.event_id}, name='{self.name}')>"
        )
