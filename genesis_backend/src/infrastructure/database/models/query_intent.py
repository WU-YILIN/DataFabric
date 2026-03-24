from __future__ import annotations

from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class QueryIntent(Base, TimestampMixin):
    __tablename__ = "query_intents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    intent_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    time_scope: Mapped[str | None] = mapped_column(String(128), nullable=True)
    dimensions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    operation_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="READ")
    latency_expectation: Mapped[str] = mapped_column(String(32), nullable=False, default="INTERACTIVE")
    candidate_paths: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="query_intents")
    plans: Mapped[list["QueryPlan"]] = relationship(back_populates="intent", cascade="all, delete-orphan")
    runs: Mapped[list["QueryRun"]] = relationship(back_populates="intent", cascade="all, delete-orphan")
