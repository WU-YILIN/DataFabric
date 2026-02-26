from enum import Enum
from typing import Optional

from sqlalchemy import ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.infrastructure.database.models.base import Base, TimestampMixin


class DataAssetType(str, Enum):
    TABLE = "TABLE"
    TOPIC = "TOPIC"
    VIEW = "VIEW"
    METRIC = "METRIC"


class DataAssetStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DRAFT = "DRAFT"
    DEPRECATED = "DEPRECATED"


class DataAsset(Base, TimestampMixin):
    __tablename__ = "data_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_system: Mapped[str] = mapped_column(String(100), nullable=False)
    database_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    object_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(100), nullable=False)
    owner: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default=DataAssetStatus.ACTIVE.value)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    description: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    schema_definition: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    version: Mapped[str] = mapped_column(String(20), nullable=False, default="1.0.0")

    project: Mapped["Project"] = relationship(back_populates="data_assets")
    upstream_edges: Mapped[list["DataAssetLineage"]] = relationship(
        "DataAssetLineage",
        foreign_keys="DataAssetLineage.downstream_asset_id",
        back_populates="downstream_asset",
        cascade="all, delete-orphan",
    )
    downstream_edges: Mapped[list["DataAssetLineage"]] = relationship(
        "DataAssetLineage",
        foreign_keys="DataAssetLineage.upstream_asset_id",
        back_populates="upstream_asset",
        cascade="all, delete-orphan",
    )
    changes: Mapped[list["DataAssetChangeLog"]] = relationship(
        "DataAssetChangeLog",
        back_populates="asset",
        cascade="all, delete-orphan",
    )
    data_quality_rules: Mapped[list["DataQualityRule"]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return (
            f"<DataAsset(id={self.id}, project_id={self.project_id}, "
            f"type='{self.asset_type}', name='{self.name}')>"
        )
