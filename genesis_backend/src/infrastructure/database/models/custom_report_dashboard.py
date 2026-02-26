from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CustomReportDashboard(Base, TimestampMixin):
    __tablename__ = "custom_report_dashboards"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)

    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="DASHBOARD")
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    scenario: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    template_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_personal: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    layout_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    query_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    filter_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    refresh_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    permission_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)

    cached_result_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_data_refresh_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(255), nullable=False)

    tenant: Mapped["Tenant"] = relationship(back_populates="custom_report_dashboards")
    project: Mapped["Project"] = relationship(back_populates="custom_report_dashboards")
    versions: Mapped[list["CustomReportDashboardVersion"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )
    saved_views: Mapped[list["CustomReportSavedView"]] = relationship(
        back_populates="dashboard", cascade="all, delete-orphan"
    )

