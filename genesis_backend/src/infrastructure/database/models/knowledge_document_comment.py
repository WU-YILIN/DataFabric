from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class KnowledgeDocumentComment(Base, TimestampMixin):
    __tablename__ = "knowledge_document_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("knowledge_documents.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    content: Mapped[str] = mapped_column(String(2000), nullable=False)
    mentions: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    document: Mapped["KnowledgeDocument"] = relationship(back_populates="comments")
