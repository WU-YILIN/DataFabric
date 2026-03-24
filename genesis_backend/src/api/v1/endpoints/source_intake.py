from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.domain.source_intake_service import SourceIntakeService
from src.infrastructure.database.session import get_async_session

router = APIRouter()


class SourceIntakeCreateRequest(BaseModel):
    instance_name: str = Field(..., min_length=2, max_length=255)
    connector_key: str = Field(..., min_length=2, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


class SourceIntakeUpdateRequest(BaseModel):
    instance_name: str | None = Field(default=None, min_length=2, max_length=255)
    config: dict[str, Any] | None = None
    memory_scope_default: str | None = Field(default=None, max_length=32)
    watch_enabled: bool | None = None
    watch_interval_seconds: int | None = Field(default=None, ge=30, le=86400)



def _service(db: AsyncSession) -> SourceIntakeService:
    return SourceIntakeService(db)


@router.get("/connectors")
async def list_connectors(
    q: str | None = Query(default=None),
    category: str | None = Query(default=None),
    status: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_connectors(q=q, category=category, status=status)
    return success_response(data)


@router.get("/instances")
async def list_instances(
    q: str | None = Query(default=None),
    connector_key: str | None = Query(default=None),
    status: str | None = Query(default=None),
    heat: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_instances(
        project_id=context.project.id,
        q=q,
        connector_key=connector_key,
        status=status,
        heat=heat,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.post("/instances")
async def create_instance(
    request: SourceIntakeCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.create_instance(
        project_id=context.project.id,
        instance_name=request.instance_name,
        connector_key=request.connector_key,
        config=request.config,
    )
    return success_response(data, code="SOURCE_INSTANCE_CREATED", message="实例创建成功")


@router.get("/instances/{instance_id}")
async def get_instance(
    instance_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.get_instance(project_id=context.project.id, instance_id=instance_id)
    return success_response(data)


@router.patch("/instances/{instance_id}")
async def update_instance(
    instance_id: int,
    request: SourceIntakeUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.update_instance(
        project_id=context.project.id,
        instance_id=instance_id,
        instance_name=request.instance_name,
        config=request.config,
        memory_scope_default=request.memory_scope_default,
        watch_enabled=request.watch_enabled,
        watch_interval_seconds=request.watch_interval_seconds,
    )
    return success_response(data, code="SOURCE_INSTANCE_UPDATED", message="实例已更新")


@router.delete("/instances/{instance_id}")
async def delete_instance(
    instance_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.delete_instance(project_id=context.project.id, instance_id=instance_id)
    return success_response(data, code="SOURCE_INSTANCE_DELETED", message="实例已删除")


@router.post("/instances/{instance_id}/test")
async def test_instance(
    instance_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.test_instance(project_id=context.project.id, instance_id=instance_id)
    return success_response(data, code="SOURCE_INSTANCE_TESTED", message="连接测试完成")


@router.post("/instances/{instance_id}/discover")
async def discover_instance(
    instance_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.discover_instance(project_id=context.project.id, instance_id=instance_id, trigger_mode="MANUAL")
    return success_response(data, code="SOURCE_INSTANCE_DISCOVERED", message="发现完成")


@router.post("/instances/{instance_id}/watch/run")
async def watch_instance(
    instance_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.discover_instance(project_id=context.project.id, instance_id=instance_id, trigger_mode="WATCH")
    return success_response(data, code="SOURCE_WATCH_COMPLETED", message="监听扫描完成")


@router.get("/instances/{instance_id}/assets")
async def list_instance_assets(
    instance_id: int,
    q: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    heat: str | None = Query(default=None),
    status: str | None = Query(default=None),
    updated_since: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_assets(
        project_id=context.project.id,
        instance_id=instance_id,
        q=q,
        asset_type=asset_type,
        heat=heat,
        status=status,
        updated_since=updated_since,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.get("/assets/{asset_id}/fields")
async def list_asset_fields(
    asset_id: int,
    q: str | None = Query(default=None),
    candidate_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_asset_fields(
        project_id=context.project.id,
        asset_id=asset_id,
        q=q,
        candidate_type=candidate_type,
        field_status=status,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.get("/fields/{field_id}")
async def get_field_detail(
    field_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.get_field_detail(project_id=context.project.id, field_id=field_id)
    return success_response(data)


@router.get("/fields/{field_id}/profiles")
async def list_field_profiles(
    field_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_field_profiles(project_id=context.project.id, field_id=field_id)
    return success_response(data)


@router.get("/fields/{field_id}/candidates")
async def list_field_candidates(
    field_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_field_candidates(project_id=context.project.id, field_id=field_id)
    return success_response(data)


@router.get("/instances/{instance_id}/telemetry")
async def get_instance_telemetry(
    instance_id: int,
    window: str = Query(default="24h"),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.get_instance_telemetry(project_id=context.project.id, instance_id=instance_id, window=window)
    return success_response(data)


@router.get("/assets")
async def list_assets(
    q: str | None = Query(default=None),
    instance_id: int | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    heat: str | None = Query(default=None),
    status: str | None = Query(default=None),
    updated_since: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_assets(
        project_id=context.project.id,
        q=q,
        instance_id=instance_id,
        asset_type=asset_type,
        heat=heat,
        status=status,
        updated_since=updated_since,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.get("/change-events")
async def list_change_events(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_change_events(
        project_id=context.project.id,
        q=q,
        status=status,
        severity=severity,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.get("/candidates")
async def list_candidates(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    candidate_type: str | None = Query(default=None),
    memory_scope_target: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_candidates(
        project_id=context.project.id,
        q=q,
        status=status,
        candidate_type=candidate_type,
        memory_scope_target=memory_scope_target,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.post("/candidates/{candidate_id}/promote")
async def promote_candidate(
    candidate_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.promote_candidate(
        project_id=context.project.id,
        candidate_id=candidate_id,
        tenant_id=context.project.tenant_id,
        actor_id=context.actor_id,
        user_id=context.user.id if context.user else None,
        share=False,
    )
    return success_response(data, code="SOURCE_CANDIDATE_PROMOTED", message="已纳入项目记忆")


@router.post("/candidates/{candidate_id}/share")
async def share_candidate(
    candidate_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.promote_candidate(
        project_id=context.project.id,
        candidate_id=candidate_id,
        tenant_id=context.project.tenant_id,
        actor_id=context.actor_id,
        user_id=context.user.id if context.user else None,
        share=True,
    )
    return success_response(data, code="SOURCE_CANDIDATE_SHARED", message="已提升为公共记忆")


@router.post("/candidates/{candidate_id}/dismiss")
async def dismiss_candidate(
    candidate_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.dismiss_candidate(project_id=context.project.id, candidate_id=candidate_id)
    return success_response(data, code="SOURCE_CANDIDATE_DISMISSED", message="候选变化已忽略")


@router.get("/briefs")
async def list_briefs(
    instance_id: int | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.list_briefs(
        project_id=context.project.id,
        instance_id=instance_id,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.get("/telemetry/overview")
async def get_telemetry_overview(
    instance_id: int | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.get_telemetry_overview(project_id=context.project.id, instance_id=instance_id)
    return success_response(data)


@router.get("/telemetry/source-series")
async def get_source_series(
    window: str = Query(default="24h"),
    instance_id: int | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.get_source_series(project_id=context.project.id, window=window, instance_id=instance_id)
    return success_response(data)


@router.get("/telemetry/node-series")
async def get_node_series(
    window: str = Query(default="24h"),
    instance_id: int | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = _service(db)
    data = await service.get_node_series(project_id=context.project.id, window=window, instance_id=instance_id)
    return success_response(data)
