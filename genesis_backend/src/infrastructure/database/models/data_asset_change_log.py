from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataAssetChangeLog(Base, TimestampMixin):
    __tablename__ = "data_asset_change_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("data_assets.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    from_version: Mapped[str] = mapped_column(String(20), nullable=False)
    to_version: Mapped[str] = mapped_column(String(20), nullable=False)
    diff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)

    asset: Mapped["DataAsset"] = relationship("DataAsset", back_populates="changes")

    def __repr__(self) -> str:
        return (
            f"<DataAssetChangeLog(id={self.id}, asset_id={self.asset_id}, "
            f"from='{self.from_version}', to='{self.to_version}')>"
        )
