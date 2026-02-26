import asyncio

from src.config import settings
from src.domain.pipeline.orchestration_service import PipelineOrchestrationService
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.database.repositories.pipeline_history_repo import (
    PipelineHistoryRepository,
)
from src.infrastructure.database.repositories.pipeline_repo import PipelineRepository
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.dataplane.flink import FlinkProvisioner
from src.infrastructure.dataplane.kafka import KafkaProvisioner
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def sync_pipeline_loop(stop_event: asyncio.Event) -> None:
    interval = max(5, settings.PIPELINE_SYNC_INTERVAL_SECONDS)
    logger.info("Pipeline sync loop started", interval_seconds=interval)
    while not stop_event.is_set():
        try:
            async with async_session_factory() as session:
                pipeline_repo = PipelineRepository(session)
                candidates = await pipeline_repo.get_sync_candidates()
                if candidates:
                    service = PipelineOrchestrationService(
                        event_repo=EventRepository(session),
                        pipeline_repo=pipeline_repo,
                        pipeline_history_repo=PipelineHistoryRepository(session),
                        audit_repo=BaseRepository(AuditLog, session),
                        alert_repo=BaseRepository(Alert, session),
                        kafka=KafkaProvisioner(),
                        flink=FlinkProvisioner(),
                    )
                    for pipeline in candidates:
                        await service.sync_pipeline_state(pipeline.project_id, pipeline)
                await session.commit()
        except Exception as exc:
            logger.error("Pipeline sync loop iteration failed", error=str(exc))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue

    logger.info("Pipeline sync loop stopped")
