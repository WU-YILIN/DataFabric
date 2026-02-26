from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataProduct(Base, TimestampMixin):
    __tablename__ = "data_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    product_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(128), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    visibility: Mapped[str] = mapped_column(String(32), nullable=False, default="PROJECT")

    schema_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    asset_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False, default=list)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    sla_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    usage_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    access_policy_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="data_products")
    project: Mapped["Project"] = relationship(back_populates="data_products")
    versions: Mapped[list["DataProductVersion"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list["DataProductSubscription"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )

