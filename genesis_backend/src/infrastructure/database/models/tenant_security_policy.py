from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class TenantSecurityPolicy(Base, TimestampMixin):
    __tablename__ = "tenant_security_policies"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_tenant_security_policy"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)

    sso_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mfa_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    password_min_length: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    password_require_upper: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_require_lower: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_require_number: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    password_require_symbol: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    audit_log_retention_days: Mapped[int] = mapped_column(Integer, default=180, nullable=False)
    audit_export_requires_approval: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_exports_per_day: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="security_policy")
