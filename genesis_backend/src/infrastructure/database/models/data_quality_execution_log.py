from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataQualityExecutionLog(Base, TimestampMixin):
    __tablename__ = "data_quality_execution_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    rule_id: Mapped[int] = mapped_column(ForeignKey("data_quality_rules.id"), nullable=False)
    result: Mapped[str] = mapped_column(String(20), nullable=False)  # PASS / FAIL
    checked_count: Mapped[int] = mapped_column(nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(nullable=False, default=0)
    pass_rate: Mapped[float] = mapped_column(nullable=False, default=0.0)
    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(255), nullable=False, default="scheduler")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    rule: Mapped["DataQualityRule"] = relationship(back_populates="executions")

    def __repr__(self) -> str:
        return (
            f"<DataQualityExecutionLog(id={self.id}, rule_id={self.rule_id}, "
            f"result='{self.result}', pass_rate={self.pass_rate})>"
        )
