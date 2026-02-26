from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataProductVersion(Base, TimestampMixin):
    __tablename__ = "data_product_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("data_products.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    version_no: Mapped[int] = mapped_column(nullable=False, default=1)
    change_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    snapshot_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)

    product: Mapped["DataProduct"] = relationship(back_populates="versions")

