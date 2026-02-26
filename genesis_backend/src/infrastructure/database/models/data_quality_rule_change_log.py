from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataQualityRuleChangeLog(Base, TimestampMixin):
    __tablename__ = "data_quality_rule_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("data_quality_rules.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    from_version: Mapped[str] = mapped_column(String(20), nullable=False)
    to_version: Mapped[str] = mapped_column(String(20), nullable=False)
    diff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)

    rule: Mapped["DataQualityRule"] = relationship(back_populates="changes")

    def __repr__(self) -> str:
        return (
            f"<DataQualityRuleChangeLog(id={self.id}, rule_id={self.rule_id}, "
            f"from='{self.from_version}', to='{self.to_version}')>"
        )
