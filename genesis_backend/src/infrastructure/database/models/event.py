from enum import Enum
from typing import Optional
from sqlalchemy import String, JSON, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.infrastructure.database.models.base import Base, TimestampMixin


class EventStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class EventGovernanceStatus(str, Enum):
    NOT_CHECKED = "NOT_CHECKED"
    APPROVED = "APPROVED"
    NEEDS_REVISION = "NEEDS_REVISION"
    REJECTED = "REJECTED"


class EventPattern(Base, TimestampMixin):
    __tablename__ = "event_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    template: Mapped[str] = mapped_column(String(255), nullable=False)  # e.g., evt_{action}_{obj}
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    def __repr__(self) -> str:
        return f"<EventPattern(id={self.id}, template='{self.template}')>"


class TrackingEvent(Base, TimestampMixin):
    __tablename__ = "tracking_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(1000))
    properties: Mapped[dict] = mapped_column(JSON, nullable=False)  # JSON Schema
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(50), default=EventStatus.DRAFT)
    version: Mapped[str] = mapped_column(String(20), default="1.0.0")
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    governance_status: Mapped[str] = mapped_column(
        String(32), default=EventGovernanceStatus.NOT_CHECKED.value, nullable=False
    )
    
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    project: Mapped["Project"] = relationship(back_populates="events")
    changes: Mapped[list["EventChangeLog"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )
    data_quality_rules: Mapped[list["DataQualityRule"]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TrackingEvent(code='{self.code}', name='{self.name}')>"
