from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class CustomReportDashboardVersion(Base, TimestampMixin):
    __tablename__ = "custom_report_dashboard_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    dashboard_id: Mapped[int] = mapped_column(ForeignKey("custom_report_dashboards.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False, default=1)
    change_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snapshot_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)

    dashboard: Mapped["CustomReportDashboard"] = relationship(back_populates="versions")

