from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class QueryPlan(Base, TimestampMixin):
    __tablename__ = "query_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    intent_id: Mapped[int] = mapped_column(ForeignKey("query_intents.id"), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    selected_path: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    engine_strategy: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    plan_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    matched_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="query_plans")
    intent: Mapped["QueryIntent"] = relationship(back_populates="plans")
    runs: Mapped[list["QueryRun"]] = relationship(back_populates="plan", cascade="all, delete-orphan")
    materialization_artifacts: Mapped[list["MaterializationArtifact"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )
