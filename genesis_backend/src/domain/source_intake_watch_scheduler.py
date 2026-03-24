from __future__ import annotations

import asyncio

from src.config import settings
from src.domain.source_intake_service import SourceIntakeService
from src.infrastructure.database.session import async_session_factory
from src.utils.logger import get_logger

logger = get_logger(__name__)


async def sync_source_watch_loop(stop_event: asyncio.Event) -> None:
    interval = max(5, settings.SOURCE_INTAKE_WATCH_TICK_SECONDS)
    batch_size = max(1, settings.SOURCE_INTAKE_WATCH_BATCH_SIZE)
    logger.info("Source intake watch loop started", interval_seconds=interval, batch_size=batch_size)
    while not stop_event.is_set():
        try:
            async with async_session_factory() as session:
                service = SourceIntakeService(session)
                summary = await service.run_due_watches(limit=batch_size)
                if summary["processed"]:
                    logger.info("Source intake watch loop processed instances", **summary)
                await session.commit()
        except Exception as exc:
            logger.error("Source intake watch loop iteration failed", error=str(exc))

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval)
        except TimeoutError:
            continue

    logger.info("Source intake watch loop stopped")
