from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.domain.fabric_architecture_service import FabricArchitectureService
from src.domain.fabric_execution_service import FabricExecutionService
from src.infrastructure.database.session import get_async_session

router = APIRouter()


class FabricPlanRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=4000)
    latency_target_ms: int = Field(default=800, ge=50, le=10000)


@router.get("/source-profiles")
async def get_fabric_source_profiles(
    q: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    heat: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricArchitectureService(db)
    data = await service.list_source_profiles(
        project_id=context.project.id,
        q=q,
        source_type=source_type,
        heat=heat,
        limit=limit,
        offset=offset,
    )
    return success_response(data)


@router.get("/update-semantics")
async def get_fabric_update_semantics(
    q: str | None = Query(default=None),
    mode: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricArchitectureService(db)
    data = await service.list_update_semantics(
        project_id=context.project.id,
        q=q,
        mode=mode,
        limit=limit,
        offset=offset,
    )
    return success_response(data)


@router.get("/semantic-domains")
async def get_fabric_semantic_domains(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricArchitectureService(db)
    data = await service.get_semantic_domains(
        project_id=context.project.id,
        tenant_id=context.project.tenant_id,
    )
    return success_response(data)


@router.post("/planner/plan")
async def plan_fabric_query(
    payload: FabricPlanRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricArchitectureService(db)
    data = await service.plan_query(
        project_id=context.project.id,
        tenant_id=context.project.tenant_id,
        question=payload.question,
        latency_target_ms=payload.latency_target_ms,
    )
    return success_response(data)


@router.post("/planner/submit")
async def submit_fabric_query(
    payload: FabricPlanRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricExecutionService(db)
    data = await service.submit_query(
        project_id=context.project.id,
        tenant_id=context.project.tenant_id,
        actor_id=context.actor_id,
        actor_user_id=context.user.id if context.user else None,
        question=payload.question,
        latency_target_ms=payload.latency_target_ms,
    )
    return success_response(data)


@router.get("/planner/runs")
async def list_fabric_query_runs(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    intent_type: str | None = Query(default=None),
    selected_path: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricExecutionService(db)
    data = await service.list_query_runs(
        project_id=context.project.id,
        q=q,
        status=status,
        intent_type=intent_type,
        selected_path=selected_path,
        limit=limit,
        offset=offset,
    )
    return success_response(data)


@router.get("/planner/runs/{run_id}")
async def get_fabric_query_run_detail(
    run_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricExecutionService(db)
    data = await service.get_query_run_detail(project_id=context.project.id, run_id=run_id)
    return success_response(data)


@router.get("/materializations")
async def get_fabric_materializations(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricArchitectureService(db)
    data = await service.list_materializations(
        project_id=context.project.id,
        q=q,
        status=status,
        limit=limit,
        offset=offset,
    )
    return success_response(data)


@router.get("/materialization-artifacts")
async def get_fabric_materialization_artifacts(
    q: str | None = Query(default=None),
    status: str | None = Query(default=None),
    heat: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricExecutionService(db)
    data = await service.list_materialization_artifacts(
        project_id=context.project.id,
        q=q,
        status=status,
        heat=heat,
        limit=limit,
        offset=offset,
    )
    return success_response(data)


@router.get("/traces/{trace_id}")
async def get_fabric_trace(
    trace_id: str,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricExecutionService(db)
    data = await service.get_trace(project_id=context.project.id, trace_id=trace_id)
    return success_response(data)


@router.get("/telemetry/overview")
async def get_fabric_telemetry_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = FabricArchitectureService(db)
    data = await service.get_telemetry_overview(project_id=context.project.id)
    return success_response(data)
