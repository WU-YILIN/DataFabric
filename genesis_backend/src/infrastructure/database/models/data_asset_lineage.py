from typing import Optional

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataAssetLineage(Base, TimestampMixin):
    __tablename__ = "data_asset_lineage"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    upstream_asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id"), nullable=False)
    downstream_asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(64), nullable=False, default="DERIVED_FROM")
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    upstream_asset: Mapped["DataAsset"] = relationship(
        "DataAsset",
        foreign_keys=[upstream_asset_id],
        back_populates="downstream_edges",
    )
    downstream_asset: Mapped["DataAsset"] = relationship(
        "DataAsset",
        foreign_keys=[downstream_asset_id],
        back_populates="upstream_edges",
    )

    def __repr__(self) -> str:
        return (
            f"<DataAssetLineage(id={self.id}, project_id={self.project_id}, "
            f"upstream={self.upstream_asset_id}, downstream={self.downstream_asset_id})>"
        )
