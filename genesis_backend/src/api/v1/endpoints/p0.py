from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.domain.p0 import P0ControlPlaneService
from src.infrastructure.database.session import get_async_session

router = APIRouter()


@router.get("/overview")
async def get_p0_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    overview = await service.get_overview(context.project.id)
    return success_response(overview)


@router.get("/source-profiles")
async def get_p0_source_profiles(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    heat: str | None = Query(default=None),
    q: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    data = await service.list_source_profiles(context.project.id, limit=limit, offset=offset, heat=heat, q=q)
    return success_response(data)


@router.get("/source-profiles/{source_profile_id}")
async def get_p0_source_profile_detail(
    source_profile_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    item = await service.get_source_profile_detail(context.project.id, source_profile_id)
    if item is None:
        raise HTTPException(status_code=404, detail="P0 source profile not found")
    return success_response(item)


@router.get("/inference-candidates")
async def get_p0_inference_candidates(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    candidate_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    data = await service.list_inference_candidates(
        context.project.id,
        limit=limit,
        offset=offset,
        candidate_type=candidate_type,
        status=status,
        q=q,
    )
    return success_response(data)


@router.get("/inference-candidates/{candidate_id}")
async def get_p0_inference_candidate_detail(
    candidate_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    item = await service.get_inference_candidate_detail(context.project.id, candidate_id)
    if item is None:
        raise HTTPException(status_code=404, detail="P0 inference candidate not found")
    return success_response(item)


@router.get("/governance-records")
async def get_p0_governance_records(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    queue_status: str | None = Query(default=None),
    decision_status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    data = await service.list_governance_records(
        context.project.id,
        limit=limit,
        offset=offset,
        queue_status=queue_status,
        decision_status=decision_status,
        q=q,
    )
    return success_response(data)


@router.get("/governance-records/{record_id}")
async def get_p0_governance_record_detail(
    record_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    item = await service.get_governance_record_detail(context.project.id, record_id)
    if item is None:
        raise HTTPException(status_code=404, detail="P0 governance record not found")
    return success_response(item)


@router.get("/contract-artifacts")
async def get_p0_contract_artifacts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    serving_status: str | None = Query(default=None),
    q: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    data = await service.list_contract_artifacts(
        context.project.id,
        limit=limit,
        offset=offset,
        serving_status=serving_status,
        q=q,
    )
    return success_response(data)


@router.get("/contract-artifacts/{artifact_id}")
async def get_p0_contract_artifact_detail(
    artifact_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = P0ControlPlaneService(db)
    item = await service.get_contract_artifact_detail(context.project.id, artifact_id)
    if item is None:
        raise HTTPException(status_code=404, detail="P0 contract artifact not found")
    return success_response(item)
