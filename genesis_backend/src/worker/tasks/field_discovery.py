"""
Module 3 — AI 语义映射探针
Celery 后台任务：扫描原始事件日志中的未知字段，并调用 AI 语义服务自动生成映射草案。

流程：
  1. 扫描 IngestionEventLog.raw_payload，提取出现的 JSON 字段名
  2. 与 TrackingEvent.properties 中的标准字段对比，找出「未登记字段」
  3. 调用 SemanticMappingService 让 LLM 推断最佳匹配
  4. 将结果以 status=PENDING 写入 SchemaFieldMapping 表，等待人工审批
"""

import json
from collections import Counter
from typing import Any

from celery import shared_task

from src.utils.logger import get_logger

logger = get_logger(__name__)


@shared_task(name="tasks.scan_raw_fields", bind=True, max_retries=3)
def scan_raw_fields(self, project_id: int, event_id: int) -> dict[str, Any]:
    """
    扫描指定项目+事件的原始字段，发现未知 Key，生成映射候选草案。

    注意：Celery 任务无法直接使用 async/await，因此这里使用 asyncio.run() 驱动协程。
    """
    import asyncio
    try:
        result = asyncio.run(_scan_async(project_id=project_id, event_id=event_id))
        return result
    except Exception as exc:
        logger.error("scan_raw_fields failed", project_id=project_id, event_id=event_id, error=str(exc))
        raise self.retry(exc=exc, countdown=60)


async def _scan_async(project_id: int, event_id: int) -> dict[str, Any]:
    """异步扫描的核心实现。"""
    from sqlalchemy import select
    from src.infrastructure.database.session import get_async_session
    from src.infrastructure.database.models.ingestion_event_log import IngestionEventLog
    from src.infrastructure.database.models.event import TrackingEvent
    from src.infrastructure.database.models.schema_field_mapping import (
        SchemaFieldMapping, FieldMappingStatus,
    )
    from src.domain.mapping.service import SemanticMappingService

    mapping_service = SemanticMappingService()

    # ── Step 1: 取最近 500 条原始事件日志 ──────────────────────────────────────
    async for session in get_async_session():
        # 拉取事件的标准属性字典
        event_result = await session.execute(
            select(TrackingEvent).where(TrackingEvent.id == event_id)
        )
        event = event_result.scalar_one_or_none()
        if event is None:
            return {"error": f"TrackingEvent {event_id} not found"}

        standard_fields: set[str] = set(event.properties.keys()) if isinstance(event.properties, dict) else set()

        # 拉取最近 500 条原始日志
        logs_result = await session.execute(
            select(IngestionEventLog)
            .where(IngestionEventLog.project_id == project_id)
            .order_by(IngestionEventLog.created_at.desc())
            .limit(500)
        )
        logs = list(logs_result.scalars().all())

        # ── Step 2: 提取未知字段及其频率 ───────────────────────────────────────
        field_counter: Counter = Counter()
        field_samples: dict[str, list] = {}

        for log in logs:
            try:
                payload = log.payload if isinstance(log.payload, dict) else json.loads(log.payload or "{}")
            except Exception:
                continue
            for key, val in payload.items():
                if key not in standard_fields:
                    field_counter[key] += 1
                    if key not in field_samples:
                        field_samples[key] = []
                    if len(field_samples[key]) < 5:
                        field_samples[key].append(val)

        unknown_fields = {k: v for k, v in field_counter.items() if v >= 3}  # 至少出现 3 次才值得处理
        logger.info(
            "scan_raw_fields: discovered unknown fields",
            event_id=event_id,
            unknown_count=len(unknown_fields),
        )

        created_count = 0
        skipped_count = 0

        for field_name, freq in unknown_fields.items():
            # 检查是否已经有 PENDING/APPROVED 的映射条目
            from sqlalchemy import String, cast
            existing = await session.execute(
                select(SchemaFieldMapping).where(
                    SchemaFieldMapping.event_id == event_id,
                    cast(SchemaFieldMapping.source_paths, String).contains(field_name),
                    SchemaFieldMapping.status != FieldMappingStatus.REJECTED,
                )
            )
            if existing.scalar_one_or_none() is not None:
                skipped_count += 1
                continue

            # ── Step 3: 调用 AI 推断映射 ───────────────────────────────────────
            try:
                proposal = await mapping_service.propose(
                    unknown_field=field_name,
                    event=event,
                    sample_values=field_samples.get(field_name, []),
                )
            except Exception as ai_exc:
                logger.warning("AI mapping proposal failed", field=field_name, error=str(ai_exc))
                proposal = None

            # ── Step 4: 写入 PENDING 草案 ──────────────────────────────────────
            mapping_data: dict[str, Any] = {
                "project_id": project_id,
                "event_id": event_id,
                "target_field": proposal.matched_field if proposal and proposal.matched_field != "UNKNOWN" else f"_unmapped_{field_name}",
                "source_paths": [f"$.{field_name}"],
                "cast_type": "STRING",          # 默认 STRING，人工审批时可修改
                "status": FieldMappingStatus.PENDING,
                "confidence_score": proposal.confidence if proposal else 0.0,
                "proposed_by": "ai" if proposal else "scanner",
                "ai_reasoning": proposal.reasoning if proposal else None,
                "field_frequency": freq,
            }
            session.add(SchemaFieldMapping(**mapping_data))
            created_count += 1

        await session.commit()
        return {
            "event_id": event_id,
            "scanned_logs": len(logs),
            "unknown_fields_found": len(unknown_fields),
            "proposals_created": created_count,
            "proposals_skipped": skipped_count,
        }
