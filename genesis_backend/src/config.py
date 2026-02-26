from enum import Enum
from typing import Optional

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True
    )

    PROJECT_NAME: str = "Genesis-Tracking"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DATABASE_URL: str | None = "sqlite+aiosqlite:///./genesis_local.db"

    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "genesis_db"

    @computed_field
    @property
    def ASYNC_DATABASE_URL(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"

    # Data Plane (Kafka/Flink)
    KAFKA_BOOTSTRAP_SERVERS: str = "localhost:9092"
    FLINK_REST_URL: str = "http://localhost:8081"
    PIPELINE_PROVISION_MODE: str = "mock"
    FLINK_PIPELINE_JAR_ID: str | None = None
    FLINK_PIPELINE_ENTRY_CLASS: str | None = None
    PIPELINE_AUTO_SYNC_ENABLED: bool = True
    PIPELINE_SYNC_INTERVAL_SECONDS: int = 30

    # Worker Broker (defaults to in-memory for local dev)
    CELERY_BROKER_URL: str = "memory://"
    CELERY_RESULT_BACKEND: str = "cache+memory://"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334

    # LLM
    OPENAI_API_KEY: Optional[str] = None

    # Auth
    AUTH_SECRET_KEY: str = "dev-only-change-me"
    AUTH_TOKEN_EXPIRE_HOURS: int = 24

    # Observability
    LOG_LEVEL: str = "INFO"
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4317"


settings = Settings()
