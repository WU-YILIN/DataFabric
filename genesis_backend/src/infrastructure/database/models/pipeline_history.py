from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base


class PipelineStatusHistory(Base):
    __tablename__ = "pipeline_status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    pipeline_id: Mapped[int] = mapped_column(ForeignKey("pipelines.id"), nullable=False)
    from_status: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False, default="system")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    pipeline: Mapped["Pipeline"] = relationship(back_populates="status_history")

    def __repr__(self) -> str:
        return (
            f"<PipelineStatusHistory(id={self.id}, pipeline_id={self.pipeline_id}, "
            f"from='{self.from_status}', to='{self.to_status}', source='{self.source}')>"
        )
