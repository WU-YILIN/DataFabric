import asyncio

from kafka import KafkaAdminClient
from kafka.admin import NewTopic
from kafka.errors import TopicAlreadyExistsError

from src.config import settings
from src.domain.exceptions import AppError
from src.utils.logger import get_logger

logger = get_logger(__name__)


class KafkaProvisioner:
    def _create_admin_client(self) -> KafkaAdminClient:
        return KafkaAdminClient(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            client_id="genesis-control-plane",
        )

    async def ensure_topic(
        self,
        topic_name: str,
        partitions: int,
        replication_factor: int,
        retention_hours: int,
    ) -> dict:
        if settings.PIPELINE_PROVISION_MODE == "mock":
            logger.info(
                "Kafka topic provisioned (mock)",
                topic=topic_name,
                partitions=partitions,
                replication_factor=replication_factor,
                retention_hours=retention_hours,
                bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            )
            return {
                "topic": topic_name,
                "partitions": partitions,
                "replication_factor": replication_factor,
                "retention_hours": retention_hours,
            }

        try:
            await asyncio.to_thread(
                self._create_or_validate_topic,
                topic_name,
                partitions,
                replication_factor,
                retention_hours,
            )
        except AppError:
            raise
        except Exception as exc:
            raise AppError(f"Kafka provisioning failed: {exc}", code="KAFKA_PROVISION_FAILED", status_code=502) from exc

        return {
            "topic": topic_name,
            "partitions": partitions,
            "replication_factor": replication_factor,
            "retention_hours": retention_hours,
        }

    def _create_or_validate_topic(
        self,
        topic_name: str,
        partitions: int,
        replication_factor: int,
        retention_hours: int,
    ) -> None:
        admin = self._create_admin_client()
        try:
            existing_topics = set(admin.list_topics())
            if topic_name in existing_topics:
                logger.info("Kafka topic already exists", topic=topic_name)
                return

            admin.create_topics(
                new_topics=[
                    NewTopic(
                        name=topic_name,
                        num_partitions=partitions,
                        replication_factor=replication_factor,
                        topic_configs={
                            "retention.ms": str(retention_hours * 60 * 60 * 1000),
                            "cleanup.policy": "delete",
                        },
                    )
                ],
                validate_only=False,
            )
            logger.info("Kafka topic created", topic=topic_name)
        except TopicAlreadyExistsError:
            logger.info("Kafka topic already exists", topic=topic_name)
        finally:
            admin.close()

    async def delete_topic(self, topic_name: str) -> None:
        if settings.PIPELINE_PROVISION_MODE == "mock":
            logger.info("Kafka topic deleted (mock)", topic=topic_name)
            return

        try:
            await asyncio.to_thread(self._delete_topic_blocking, topic_name)
        except Exception as exc:
            raise AppError(f"Kafka topic delete failed: {exc}", code="KAFKA_DELETE_FAILED", status_code=502) from exc

    def _delete_topic_blocking(self, topic_name: str) -> None:
        admin = self._create_admin_client()
        try:
            admin.delete_topics([topic_name])
            logger.info("Kafka topic deleted", topic=topic_name)
        finally:
            admin.close()
