from sqlalchemy import String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    auth_provider: Mapped[str] = mapped_column(String(32), default="local", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    tenant_roles: Mapped[list["UserTenantRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    project_roles: Mapped[list["UserProjectRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sent_project_invitations: Mapped[list["ProjectMemberInvitation"]] = relationship(
        back_populates="invited_by_user"
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}')>"


class UserTenantRole(Base, TimestampMixin):
    __tablename__ = "user_tenant_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship(back_populates="tenant_roles")
    tenant: Mapped["Tenant"] = relationship(back_populates="user_roles")


class UserProjectRole(Base, TimestampMixin):
    __tablename__ = "user_project_roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)

    user: Mapped["User"] = relationship(back_populates="project_roles")
    project: Mapped["Project"] = relationship(back_populates="user_roles")
