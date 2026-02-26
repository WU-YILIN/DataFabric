from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CustomReportSavedView(Base, TimestampMixin):
    __tablename__ = "custom_report_saved_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("custom_report_dashboards.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    filter_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    layout_override_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    share_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_export_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_export_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    dashboard: Mapped["CustomReportDashboard"] = relationship(back_populates="saved_views")

