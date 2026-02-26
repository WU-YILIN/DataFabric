from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class TenantStatus(str):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Tenant(Base, TimestampMixin):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default=TenantStatus.ACTIVE, nullable=False)

    projects: Mapped[list["Project"]] = relationship(back_populates="tenant", cascade="all, delete-orphan")
    user_roles: Mapped[list["UserTenantRole"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    security_policy: Mapped["TenantSecurityPolicy"] = relationship(
        back_populates="tenant", cascade="all, delete-orphan", uselist=False
    )
    member_invitations: Mapped[list["ProjectMemberInvitation"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    role_templates: Mapped[list["RoleTemplatePolicy"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    policy_rules: Mapped[list["PolicyRule"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    ingestion_channels: Mapped[list["IngestionChannelConfig"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    release_changes: Mapped[list["ReleaseChangeRequest"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    custom_report_dashboards: Mapped[list["CustomReportDashboard"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    data_products: Mapped[list["DataProduct"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )
    incident_cases: Mapped[list["IncidentCase"]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Tenant(id={self.id}, name='{self.name}')>"
