from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.domain.source_onboarding_service import SourceOnboardingService
from src.infrastructure.database.session import get_async_session

router = APIRouter()


class SourceOnboardingCreateRequest(BaseModel):
    source_name: str = Field(..., min_length=2, max_length=255)
    source_type: str = Field(..., min_length=3, max_length=32)
    config: dict = Field(default_factory=dict)


class SourceOnboardingUpdateRequest(BaseModel):
    source_name: str | None = Field(default=None, min_length=2, max_length=255)
    config: dict | None = None


@router.get("/sources")
async def list_sources(
    q: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    heat: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.list_sources(
        context.project.id,
        q=q,
        source_type=source_type,
        status=status,
        heat=heat,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.post("/sources")
async def create_source(
    request: SourceOnboardingCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.create_source(
        context.project.id,
        source_name=request.source_name,
        source_type=request.source_type,
        config=request.config,
    )
    return success_response(data, code="SOURCE_CREATED", message="Source created")


@router.get("/sources/{source_id}")
async def get_source(
    source_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.get_source(context.project.id, source_id)
    return success_response(data)


@router.put("/sources/{source_id}")
async def update_source(
    source_id: int,
    request: SourceOnboardingUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.update_source(
        context.project.id,
        source_id,
        source_name=request.source_name,
        config=request.config,
    )
    return success_response(data, code="SOURCE_UPDATED", message="Source updated")


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.delete_source(context.project.id, source_id)
    return success_response(data, code="SOURCE_DELETED", message="Source deleted")


@router.post("/sources/{source_id}/test")
async def test_source_connection(
    source_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.test_connection(context.project.id, source_id)
    return success_response(data, code="SOURCE_TESTED", message="Source connection tested")


@router.post("/sources/{source_id}/scan")
async def scan_source(
    source_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    service = SourceOnboardingService(db)
    data = await service.scan_source_with_memory(
        context.project.id,
        source_id,
        actor_id=context.actor_id,
        tenant_id=context.project.tenant_id,
        user_id=context.user.id if context.user else None,
    )
    return success_response(data, code="SOURCE_SCANNED", message="Source scanned")
