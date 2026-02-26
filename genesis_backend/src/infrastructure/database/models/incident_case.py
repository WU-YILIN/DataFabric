from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class IncidentCase(Base, TimestampMixin):
    __tablename__ = "incident_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    runbook_doc_id: Mapped[int | None] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=True)

    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN")
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)

    context_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    impact_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resolution_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    mitigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="incident_cases")
    project: Mapped["Project"] = relationship(back_populates="incident_cases")
    runbook_doc: Mapped["KnowledgeDocument"] = relationship()
    timeline: Mapped[list["IncidentTimelineEntry"]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )

