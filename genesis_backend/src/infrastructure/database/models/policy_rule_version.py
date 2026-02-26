from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class PolicyRuleVersion(Base, TimestampMixin):
    __tablename__ = "policy_rule_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    rule_id: Mapped[int] = mapped_column(ForeignKey("policy_rules.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False)
    change_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snapshot_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)

    rule: Mapped["PolicyRule"] = relationship(back_populates="versions")
