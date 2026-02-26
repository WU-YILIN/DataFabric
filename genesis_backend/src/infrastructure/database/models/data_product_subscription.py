from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataProductSubscription(Base, TimestampMixin):
    __tablename__ = "data_product_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("data_products.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    subscriber: Mapped[str] = mapped_column(String(255), nullable=False)
    request_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    decision_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    rejected_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token: Mapped[str | None] = mapped_column(String(255), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_quota_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    product: Mapped["DataProduct"] = relationship(back_populates="subscriptions")

