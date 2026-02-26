from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class PolicyRule(Base, TimestampMixin):
    __tablename__ = "policy_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)

    rule_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PROJECT")
    scope_value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    conditions_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actions_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    content_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    prompt_text: Mapped[str | None] = mapped_column(String(4000), nullable=True)

    version_no: Mapped[int] = mapped_column(nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="policy_rules")
    project: Mapped["Project"] = relationship(back_populates="policy_rules")
    versions: Mapped[list["PolicyRuleVersion"]] = relationship(
        back_populates="rule", cascade="all, delete-orphan"
    )
