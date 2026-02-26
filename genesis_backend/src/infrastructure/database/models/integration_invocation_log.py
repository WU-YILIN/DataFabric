from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class IntegrationInvocationLog(Base, TimestampMixin):
    __tablename__ = "integration_invocation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    integration_type: Mapped[str] = mapped_column(String(64), nullable=False)
    caller_module: Mapped[str] = mapped_column(String(64), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="SUCCESS")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    latency_ms: Mapped[int] = mapped_column(nullable=False, default=0)
    request_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)

    project: Mapped["Project"] = relationship(back_populates="integration_invocation_logs")

