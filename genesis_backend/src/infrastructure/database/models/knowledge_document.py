from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class KnowledgeDocument(Base, TimestampMixin):
    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    tenant_id: Mapped[int | None] = mapped_column(nullable=True)
    doc_type: Mapped[str] = mapped_column(String(64), nullable=False)
    module: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_level: Mapped[str] = mapped_column(String(32), nullable=False, default="BRIEF")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(32), nullable=False, default="MARKDOWN")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    related_objects: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    object_refs: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    fact_refs: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    last_editor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    last_editor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    comment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    project: Mapped["Project"] = relationship(back_populates="knowledge_documents")
    versions: Mapped[list["KnowledgeDocumentVersion"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    comments: Mapped[list["KnowledgeDocumentComment"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
