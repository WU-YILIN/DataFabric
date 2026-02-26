from sqlalchemy import ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class KnowledgeDocumentVersion(Base, TimestampMixin):
    __tablename__ = "knowledge_document_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False, default="UPDATE")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    related_objects: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    editor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    editor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    change_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="versions")
