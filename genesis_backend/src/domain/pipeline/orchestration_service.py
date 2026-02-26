import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select

from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.event import EventGovernanceStatus
from src.infrastructure.database.models.pipeline import Pipeline, PipelineStatus
from src.infrastructure.database.models.pipeline_history import PipelineStatusHistory
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.database.repositories.pipeline_history_repo import (
    PipelineHistoryRepository,
)
from src.infrastructure.database.repositories.pipeline_repo import PipelineRepository
from src.infrastructure.dataplane.flink import FlinkProvisioner
from src.infrastructure.dataplane.kafka import KafkaProvisioner


class PipelineOrchestrationService:
    def __init__(
        self,
        event_repo: EventRepository,
        pipeline_repo: PipelineRepository,
        pipeline_history_repo: PipelineHistoryRepository,
        audit_repo: BaseRepository[AuditLog],
        alert_repo: BaseRepository[Alert],
        kafka: KafkaProvisioner,
        flink: FlinkProvisioner,
    ):
        self.event_repo = event_repo
        self.pipeline_repo = pipeline_repo
        self.pipeline_history_repo = pipeline_history_repo
        self.audit_repo = audit_repo
        self.alert_repo = alert_repo
        self.kafka = kafka
        self.flink = flink
        self.max_retries = 3

    async def _record_status_change(
        self,
        pipeline: Pipeline,
        from_status: str | None,
        to_status: str,
        reason: str | None = None,
        source: str = "system",
    ) -> PipelineStatusHistory:
        return await self.pipeline_history_repo.create(
            {
                "pipeline_id": pipeline.id,
                "from_status": from_status,
                "to_status": to_status,
                "reason": reason,
                "source": source,
                "synced_at": datetime.now(timezone.utc),
            }
        )

    async def _audit(
        self,
        action: str,
        pipeline: Pipeline,
        actor: str,
        details: dict | None = None,
    ) -> None:
        await self.audit_repo.create(
            {
                "action": action,
                "entity_type": "PIPELINE",
                "entity_id": str(pipeline.id),
                "user_id": actor,
                "details": json.dumps(details or {}, ensure_ascii=True),
            }
        )

    async def _open_pipeline_alert(self, pipeline: Pipeline, reason: str) -> None:
        existing_alert_query = select(Alert).where(
            Alert.project_id == pipeline.project_id,
            Alert.source_type == "PIPELINE",
            Alert.source_id == str(pipeline.id),
            Alert.status == "OPEN",
        )
        existing_result = await self.alert_repo.session.execute(existing_alert_query)
        existing = existing_result.scalar_one_or_none()
        if existing:
            await self.alert_repo.update(
                existing,
                {
                    "severity": "HIGH",
                    "title": f"Pipeline #{pipeline.id} unavailable",
                    "description": reason[:1000],
                },
            )
            return

        await self.alert_repo.create(
            {
                "project_id": pipeline.project_id,
                "source_type": "PIPELINE",
                "source_id": str(pipeline.id),
                "severity": "HIGH",
                "title": f"Pipeline #{pipeline.id} unavailable",
                "description": reason[:1000],
                "status": "OPEN",
            }
        )

    async def _resolve_pipeline_alert(self, pipeline: Pipeline) -> None:
        existing_alert_query = select(Alert).where(
            Alert.project_id == pipeline.project_id,
            Alert.source_type == "PIPELINE",
            Alert.source_id == str(pipeline.id),
            Alert.status == "OPEN",
        )
        existing_result = await self.alert_repo.session.execute(existing_alert_query)
        existing = existing_result.scalar_one_or_none()
        if not existing:
            return
        await self.alert_repo.update(
            existing,
            {
                "status": "RESOLVED",
                "resolved_at": datetime.now(timezone.utc),
            },
        )

    @staticmethod
    def _build_topic_name(topic_prefix: str, project_id: int, event_code: str) -> str:
        return f"{topic_prefix}.{project_id}.{event_code}"

    @staticmethod
    def _build_job_name(job_name_template: str, project_id: int, event_code: str) -> str:
        return job_name_template.format(project_id=project_id, event_code=event_code)

    async def provision_pipeline(
        self,
        project_id: int,
        event_code: str,
        partitions: int,
        replication_factor: int,
        retention_hours: int,
        resource_tier: str = "standard",
        topic_prefix: str = "tracking",
        job_name_template: str = "flink_{project_id}_{event_code}",
        actor_id: str | None = None,
    ) -> Pipeline:
        event = await self.event_repo.get_by_code(event_code)
        if not event or event.project_id != project_id:
            raise ValueError(f"Event not found in project: {event_code}")
        if event.governance_status != EventGovernanceStatus.APPROVED.value:
            raise ValueError(
                f"Event must be governance approved before provisioning pipeline: {event_code}"
            )

        topic_name = self._build_topic_name(topic_prefix.strip() or "tracking", project_id, event_code)
        job_name = self._build_job_name(job_name_template.strip() or "flink_{project_id}_{event_code}", project_id, event_code)
        actor = actor_id or f"project:{project_id}"

        existing = await self.pipeline_repo.get_by_project_and_event(project_id, event_code)
        if existing:
            raise ValueError(f"Pipeline already exists for event: {event_code}")

        pipeline = await self.pipeline_repo.create(
            {
                "project_id": project_id,
                "event_code": event_code,
                "topic_name": topic_name,
                "flink_job_name": job_name,
                "status": PipelineStatus.PROVISIONING.value,
                "config": {
                    "partitions": partitions,
                    "replication_factor": replication_factor,
                    "retention_hours": retention_hours,
                    "resource_tier": resource_tier,
                    "topic_prefix": topic_prefix,
                    "job_name_template": job_name_template,
                },
                "error_message": None,
            }
        )
        await self._record_status_change(
            pipeline=pipeline,
            from_status=None,
            to_status=PipelineStatus.PROVISIONING.value,
            reason="Pipeline created",
            source="provision",
        )

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                await self.kafka.ensure_topic(
                    topic_name=topic_name,
                    partitions=partitions,
                    replication_factor=replication_factor,
                    retention_hours=retention_hours,
                )
                flink_meta = await self.flink.deploy_pipeline_job(
                    job_name=job_name,
                    topic_name=topic_name,
                )
                next_config = {
                    **pipeline.config,
                    "flink_job_id": flink_meta.get("job_id"),
                    "flink_state": flink_meta.get("state", "RUNNING"),
                }

                pipeline = await self.pipeline_repo.update(
                    pipeline,
                    {
                        "status": PipelineStatus.RUNNING.value,
                        "error_message": None,
                        "config": next_config,
                        "retry_count": attempt - 1,
                        "last_sync_at": datetime.now(timezone.utc),
                    },
                )
                await self._record_status_change(
                    pipeline=pipeline,
                    from_status=PipelineStatus.PROVISIONING.value,
                    to_status=PipelineStatus.RUNNING.value,
                    reason="Provision succeeded",
                    source="provision",
                )
                await self._resolve_pipeline_alert(pipeline)
                await self._audit(
                    "PIPELINE_PROVISION",
                    pipeline,
                    actor,
                    {
                        "event_code": event_code,
                        "topic_name": topic_name,
                        "job_name": job_name,
                        "resource_tier": resource_tier,
                    },
                )
                return pipeline
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue

        await self.pipeline_repo.update(
            pipeline,
            {
                "status": PipelineStatus.FAILED.value,
                "error_message": str(last_exc),
                "retry_count": self.max_retries,
                "last_sync_at": datetime.now(timezone.utc),
            },
        )
        await self._record_status_change(
            pipeline=pipeline,
            from_status=PipelineStatus.PROVISIONING.value,
            to_status=PipelineStatus.FAILED.value,
            reason=str(last_exc),
            source="provision",
        )
        await self._open_pipeline_alert(pipeline, str(last_exc))
        await self._audit(
            "PIPELINE_PROVISION_FAILED",
            pipeline,
            actor,
            {"error": str(last_exc)},
        )
        raise last_exc

    async def pause_pipeline(
        self,
        project_id: int,
        pipeline: Pipeline,
        actor_id: str | None = None,
    ) -> Pipeline:
        if pipeline.project_id != project_id:
            raise ValueError("Pipeline does not belong to current project")
        if pipeline.status in {PipelineStatus.STOPPED.value, PipelineStatus.ROLLING_BACK.value}:
            return pipeline

        previous_status = pipeline.status
        actor = actor_id or f"project:{project_id}"
        try:
            flink_job_id = pipeline.config.get("flink_job_id") if pipeline.config else None
            await self.flink.stop_pipeline_job(pipeline.flink_job_name, flink_job_id)
            stopped = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.STOPPED.value,
                    "error_message": None,
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != PipelineStatus.STOPPED.value:
                await self._record_status_change(
                    pipeline=stopped,
                    from_status=previous_status,
                    to_status=PipelineStatus.STOPPED.value,
                    reason="Manual pause",
                    source="manual_pause",
                )
            await self._resolve_pipeline_alert(stopped)
            await self._audit(
                "PIPELINE_PAUSE",
                stopped,
                actor,
                {"from_status": previous_status, "to_status": PipelineStatus.STOPPED.value},
            )
            return stopped
        except Exception as exc:
            failed = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.FAILED.value,
                    "error_message": str(exc),
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != PipelineStatus.FAILED.value:
                await self._record_status_change(
                    pipeline=failed,
                    from_status=previous_status,
                    to_status=PipelineStatus.FAILED.value,
                    reason=str(exc),
                    source="manual_pause",
                )
            await self._open_pipeline_alert(failed, str(exc))
            return failed

    async def resume_pipeline(
        self,
        project_id: int,
        pipeline: Pipeline,
        actor_id: str | None = None,
    ) -> Pipeline:
        if pipeline.project_id != project_id:
            raise ValueError("Pipeline does not belong to current project")
        if pipeline.status == PipelineStatus.RUNNING.value:
            return pipeline

        previous_status = pipeline.status
        actor = actor_id or f"project:{project_id}"
        try:
            flink_meta = await self.flink.deploy_pipeline_job(
                job_name=pipeline.flink_job_name,
                topic_name=pipeline.topic_name,
            )
            next_config = {
                **(pipeline.config or {}),
                "flink_job_id": flink_meta.get("job_id"),
                "flink_state": flink_meta.get("state", "RUNNING"),
            }
            running = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.RUNNING.value,
                    "error_message": None,
                    "config": next_config,
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != PipelineStatus.RUNNING.value:
                await self._record_status_change(
                    pipeline=running,
                    from_status=previous_status,
                    to_status=PipelineStatus.RUNNING.value,
                    reason="Manual resume",
                    source="manual_resume",
                )
            await self._resolve_pipeline_alert(running)
            await self._audit(
                "PIPELINE_RESUME",
                running,
                actor,
                {"from_status": previous_status, "to_status": PipelineStatus.RUNNING.value},
            )
            return running
        except Exception as exc:
            failed = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.FAILED.value,
                    "error_message": str(exc),
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != PipelineStatus.FAILED.value:
                await self._record_status_change(
                    pipeline=failed,
                    from_status=previous_status,
                    to_status=PipelineStatus.FAILED.value,
                    reason=str(exc),
                    source="manual_resume",
                )
            await self._open_pipeline_alert(failed, str(exc))
            return failed

    async def rollback_pipeline(
        self,
        project_id: int,
        pipeline: Pipeline,
        actor_id: str | None = None,
    ) -> Pipeline:
        previous_status = pipeline.status
        actor = actor_id or f"project:{project_id}"
        pipeline = await self.pipeline_repo.update(
            pipeline,
            {"status": PipelineStatus.ROLLING_BACK.value},
        )
        await self._record_status_change(
            pipeline=pipeline,
            from_status=previous_status,
            to_status=PipelineStatus.ROLLING_BACK.value,
            reason="Rollback started",
            source="rollback",
        )
        try:
            flink_job_id = pipeline.config.get("flink_job_id") if pipeline.config else None
            await self.flink.stop_pipeline_job(pipeline.flink_job_name, flink_job_id)
            await self.kafka.delete_topic(pipeline.topic_name)
            pipeline = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.STOPPED.value,
                    "error_message": None,
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            await self._record_status_change(
                pipeline=pipeline,
                from_status=PipelineStatus.ROLLING_BACK.value,
                to_status=PipelineStatus.STOPPED.value,
                reason="Rollback completed",
                source="rollback",
            )
            await self._resolve_pipeline_alert(pipeline)
            await self._audit(
                "PIPELINE_ROLLBACK",
                pipeline,
                actor,
                {"from_status": previous_status, "to_status": PipelineStatus.STOPPED.value},
            )
            return pipeline
        except Exception as exc:
            failed = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.FAILED.value,
                    "error_message": str(exc),
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            await self._record_status_change(
                pipeline=failed,
                from_status=PipelineStatus.ROLLING_BACK.value,
                to_status=PipelineStatus.FAILED.value,
                reason=str(exc),
                source="rollback",
            )
            await self._open_pipeline_alert(failed, str(exc))
            return failed

    async def sync_pipeline_state(
        self,
        project_id: int,
        pipeline: Pipeline,
        actor_id: str | None = None,
    ) -> Pipeline:
        if pipeline.project_id != project_id:
            raise ValueError("Pipeline does not belong to current project")

        previous_status = pipeline.status
        actor = actor_id or f"project:{project_id}"
        job_id = pipeline.config.get("flink_job_id") if pipeline.config else None
        if not job_id:
            failed = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.FAILED.value,
                    "error_message": "Missing flink_job_id",
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != PipelineStatus.FAILED.value:
                await self._record_status_change(
                    pipeline=failed,
                    from_status=previous_status,
                    to_status=PipelineStatus.FAILED.value,
                    reason="Missing flink_job_id",
                    source="sync",
                )
            await self._open_pipeline_alert(failed, "Missing flink_job_id")
            await self._audit(
                "PIPELINE_SYNC_FAILED",
                failed,
                actor,
                {"from_status": previous_status, "to_status": PipelineStatus.FAILED.value},
            )
            return failed

        try:
            flink_state = await self.flink.get_job_state(job_id)
            mapped = (
                PipelineStatus.RUNNING.value
                if flink_state == "RUNNING"
                else PipelineStatus.FAILED.value
            )
            next_config = {**pipeline.config, "flink_state": flink_state}
            updated = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": mapped,
                    "config": next_config,
                    "error_message": None if mapped == PipelineStatus.RUNNING.value else f"Flink state: {flink_state}",
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != mapped:
                await self._record_status_change(
                    pipeline=updated,
                    from_status=previous_status,
                    to_status=mapped,
                    reason=f"Flink state: {flink_state}",
                    source="sync",
                )
                await self._audit(
                    "PIPELINE_SYNC_STATUS_CHANGED",
                    updated,
                    actor,
                    {
                        "from_status": previous_status,
                        "to_status": mapped,
                        "flink_state": flink_state,
                    },
                )
            if mapped == PipelineStatus.RUNNING.value:
                await self._resolve_pipeline_alert(updated)
            else:
                await self._open_pipeline_alert(updated, f"Flink state: {flink_state}")
            return updated
        except Exception as exc:
            failed = await self.pipeline_repo.update(
                pipeline,
                {
                    "status": PipelineStatus.FAILED.value,
                    "error_message": str(exc),
                    "last_sync_at": datetime.now(timezone.utc),
                },
            )
            if previous_status != PipelineStatus.FAILED.value:
                await self._record_status_change(
                    pipeline=failed,
                    from_status=previous_status,
                    to_status=PipelineStatus.FAILED.value,
                    reason=str(exc),
                    source="sync",
                )
            await self._open_pipeline_alert(failed, str(exc))
            await self._audit(
                "PIPELINE_SYNC_FAILED",
                failed,
                actor,
                {"from_status": previous_status, "to_status": PipelineStatus.FAILED.value, "error": str(exc)},
            )
            return failed
