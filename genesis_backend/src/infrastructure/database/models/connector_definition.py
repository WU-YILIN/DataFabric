from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from src.infrastructure.database.models.base import Base, TimestampMixin


class ConnectorDefinition(Base, TimestampMixin):
    __tablename__ = "connector_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    connector_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    runtime_family: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE", index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    config_schema: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    capabilities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    auth_modes: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
