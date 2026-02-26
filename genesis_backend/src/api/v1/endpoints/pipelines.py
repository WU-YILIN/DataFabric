from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.domain.pipeline.orchestration_service import PipelineOrchestrationService
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.event import EventGovernanceStatus
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.database.repositories.pipeline_history_repo import (
    PipelineHistoryRepository,
)
from src.infrastructure.database.repositories.pipeline_repo import PipelineRepository
from src.infrastructure.database.session import get_async_session
from src.infrastructure.dataplane.flink import FlinkProvisioner
from src.infrastructure.dataplane.kafka import KafkaProvisioner

router = APIRouter()


class PipelineProvisionRequest(BaseModel):
    event_code: str = Field(..., min_length=3, max_length=100)
    partitions: int = Field(default=6, ge=1, le=256)
    replication_factor: int = Field(default=3, ge=1, le=5)
    retention_hours: int = Field(default=168, ge=1, le=24 * 365)
    resource_tier: str = Field(default="standard", min_length=2, max_length=32)
    topic_prefix: str = Field(default="tracking", min_length=2, max_length=64)
    job_name_template: str = Field(
        default="flink_{project_id}_{event_code}",
        min_length=5,
        max_length=128,
    )


def build_service(db: AsyncSession) -> PipelineOrchestrationService:
    return PipelineOrchestrationService(
        event_repo=EventRepository(db),
        pipeline_repo=PipelineRepository(db),
        pipeline_history_repo=PipelineHistoryRepository(db),
        audit_repo=BaseRepository(AuditLog, db),
        alert_repo=BaseRepository(Alert, db),
        kafka=KafkaProvisioner(),
        flink=FlinkProvisioner(),
    )


@router.get("/provision-options")
async def get_pipeline_provision_options(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    events = await EventRepository(db).list_by_project_filtered(
        project_id=context.project.id,
        governance_status=EventGovernanceStatus.APPROVED.value,
        limit=500,
    )
    return success_response(
        {
            "approved_events": [
                {
                    "id": event.id,
                    "code": event.code,
                    "name": event.name,
                    "domain": event.domain,
                    "status": event.status,
                    "governance_status": event.governance_status,
                }
                for event in events
            ]
        }
    )


@router.post("/provision", status_code=status.HTTP_201_CREATED)
async def provision_pipeline(
    request: PipelineProvisionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = build_service(db)
    try:
        pipeline = await service.provision_pipeline(
            project_id=context.project.id,
            event_code=request.event_code,
            partitions=request.partitions,
            replication_factor=request.replication_factor,
            retention_hours=request.retention_hours,
            resource_tier=request.resource_tier,
            topic_prefix=request.topic_prefix,
            job_name_template=request.job_name_template,
            actor_id=context.actor_id,
        )
        return success_response(
            pipeline,
            message="Pipeline provisioned",
            code="PIPELINE_PROVISIONED",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("/")
async def list_pipelines(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    event_code: str | None = Query(default=None),
    limit: int = Query(default=500, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = PipelineRepository(db)
    pipelines = await repo.list_by_project_filtered(
        project_id=context.project.id,
        q=q,
        status=status_filter,
        event_code=event_code,
        limit=limit,
    )
    return success_response(pipelines)


@router.get("/{pipeline_id}")
async def get_pipeline(
    pipeline_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = PipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline or pipeline.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")
    return success_response(pipeline)


@router.post("/{pipeline_id}/pause")
async def pause_pipeline(
    pipeline_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = PipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline or pipeline.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    service = build_service(db)
    paused = await service.pause_pipeline(
        context.project.id,
        pipeline,
        actor_id=context.actor_id,
    )
    return success_response(paused, message="Pipeline paused", code="PIPELINE_PAUSED")


@router.post("/{pipeline_id}/resume")
async def resume_pipeline(
    pipeline_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = PipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline or pipeline.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    service = build_service(db)
    resumed = await service.resume_pipeline(
        context.project.id,
        pipeline,
        actor_id=context.actor_id,
    )
    return success_response(resumed, message="Pipeline resumed", code="PIPELINE_RESUMED")


@router.post("/{pipeline_id}/rollback")
async def rollback_pipeline(
    pipeline_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = PipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline or pipeline.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    service = build_service(db)
    rolled_back = await service.rollback_pipeline(
        context.project.id,
        pipeline,
        actor_id=context.actor_id,
    )
    return success_response(rolled_back, message="Pipeline rolled back", code="PIPELINE_ROLLED_BACK")


@router.post("/{pipeline_id}/sync")
async def sync_pipeline(
    pipeline_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = PipelineRepository(db)
    pipeline = await repo.get(pipeline_id)
    if not pipeline or pipeline.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    service = build_service(db)
    synced = await service.sync_pipeline_state(
        context.project.id,
        pipeline,
        actor_id=context.actor_id,
    )
    return success_response(synced, message="Pipeline state synced", code="PIPELINE_SYNCED")


@router.get("/{pipeline_id}/history")
async def get_pipeline_history(
    pipeline_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    pipeline_repo = PipelineRepository(db)
    pipeline = await pipeline_repo.get(pipeline_id)
    if not pipeline or pipeline.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline not found")

    history_repo = PipelineHistoryRepository(db)
    rows = await history_repo.get_by_pipeline(pipeline_id)
    history = [
        {
            "id": row.id,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "reason": row.reason,
            "source": row.source,
            "synced_at": row.synced_at.isoformat(),
        }
        for row in rows
    ]
    return success_response(history)
