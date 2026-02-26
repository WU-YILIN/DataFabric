import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset, DataAssetStatus, DataAssetType
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.data_asset_change_log_repo import (
    DataAssetChangeLogRepository,
)
from src.infrastructure.database.repositories.data_asset_lineage_repo import (
    DataAssetLineageRepository,
)
from src.infrastructure.database.repositories.data_asset_repo import DataAssetRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()


class DataAssetCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    asset_type: str = Field(..., min_length=3, max_length=32)
    source_system: str = Field(..., min_length=2, max_length=100)
    database_name: str | None = None
    object_name: str = Field(..., min_length=2, max_length=255)
    domain: str = Field(..., min_length=2, max_length=100)
    owner: str | None = None
    status: str = DataAssetStatus.ACTIVE.value
    tags: list[str] = Field(default_factory=list)
    description: str | None = None
    schema_definition: dict = Field(default_factory=dict)
    upstream_asset_ids: list[int] = Field(default_factory=list)
    downstream_asset_ids: list[int] = Field(default_factory=list)


class DataAssetUpdate(BaseModel):
    name: str | None = None
    source_system: str | None = None
    database_name: str | None = None
    object_name: str | None = None
    domain: str | None = None
    owner: str | None = None
    status: str | None = None
    tags: list[str] | None = None
    description: str | None = None
    schema_definition: dict | None = None
    upstream_asset_ids: list[int] | None = None
    downstream_asset_ids: list[int] | None = None


def _asset_to_dict(asset: DataAsset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "project_id": asset.project_id,
        "name": asset.name,
        "asset_type": asset.asset_type,
        "source_system": asset.source_system,
        "database_name": asset.database_name,
        "object_name": asset.object_name,
        "domain": asset.domain,
        "owner": asset.owner,
        "status": asset.status,
        "tags": asset.tags,
        "description": asset.description,
        "schema_definition": asset.schema_definition,
        "version": asset.version,
        "created_at": asset.created_at.isoformat(),
        "updated_at": asset.updated_at.isoformat(),
    }


def _bump_patch_version(version: str) -> str:
    try:
        major, minor, patch = [int(item) for item in version.split(".")]
    except Exception:
        major, minor, patch = 1, 0, 0
    patch += 1
    return f"{major}.{minor}.{patch}"


def _build_diff(before: dict[str, Any], patch_data: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key, value in patch_data.items():
        old = before.get(key)
        if old != value:
            changed[key] = {"before": old, "after": value}
    return changed


async def _validate_lineage_asset_ids(
    repo: DataAssetRepository,
    project_id: int,
    asset_ids: list[int],
) -> None:
    for asset_id in asset_ids:
        item = await repo.get(asset_id)
        if not item or item.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid lineage asset id: {asset_id}")


@router.post("/assets", status_code=status.HTTP_201_CREATED)
async def create_data_asset(
    request: DataAssetCreate,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = DataAssetRepository(db)
    lineage_repo = DataAssetLineageRepository(db)
    audit_repo = BaseRepository(AuditLog, db)

    asset_type = request.asset_type.upper()
    status_value = request.status.upper()
    if asset_type not in {item.value for item in DataAssetType}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported asset_type: {request.asset_type}")
    if status_value not in {item.value for item in DataAssetStatus}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported status: {request.status}")

    existing = await repo.get_by_project_and_object(
        project_id=context.project.id,
        asset_type=asset_type,
        object_name=request.object_name,
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Asset already exists in current project")

    await _validate_lineage_asset_ids(repo, context.project.id, request.upstream_asset_ids)
    await _validate_lineage_asset_ids(repo, context.project.id, request.downstream_asset_ids)

    asset = await repo.create(
        {
            "project_id": context.project.id,
            "name": request.name,
            "asset_type": asset_type,
            "source_system": request.source_system,
            "database_name": request.database_name,
            "object_name": request.object_name,
            "domain": request.domain,
            "owner": request.owner,
            "status": status_value,
            "tags": request.tags,
            "description": request.description,
            "schema_definition": request.schema_definition,
        }
    )

    if request.upstream_asset_ids:
        await lineage_repo.replace_upstream(context.project.id, asset.id, request.upstream_asset_ids)
    if request.downstream_asset_ids:
        await lineage_repo.replace_downstream(context.project.id, asset.id, request.downstream_asset_ids)

    await audit_repo.create(
        {
            "action": "DATA_ASSET_CREATE",
            "entity_type": "DATA_ASSET",
            "entity_id": str(asset.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "name": asset.name,
                    "asset_type": asset.asset_type,
                    "object_name": asset.object_name,
                },
                ensure_ascii=True,
            ),
        }
    )
    return success_response(_asset_to_dict(asset), message="Data asset created", code="DATA_ASSET_CREATED")


@router.get("/assets")
async def list_data_assets(
    q: str | None = Query(default=None),
    asset_type: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    source_system: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = DataAssetRepository(db)
    rows = await repo.get_by_project_filtered(
        project_id=context.project.id,
        q=q,
        asset_type=asset_type.upper() if asset_type else None,
        domain=domain,
        source_system=source_system,
        owner=owner,
        status=status_filter.upper() if status_filter else None,
        limit=limit,
    )
    return success_response([_asset_to_dict(item) for item in rows])


@router.get("/assets/{asset_id}/detail")
async def get_data_asset_detail(
    asset_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    asset_repo = DataAssetRepository(db)
    lineage_repo = DataAssetLineageRepository(db)
    change_repo = DataAssetChangeLogRepository(db)

    asset = await asset_repo.get(asset_id)
    if not asset or asset.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")

    upstream_edges = await lineage_repo.get_upstream(context.project.id, asset.id)
    downstream_edges = await lineage_repo.get_downstream(context.project.id, asset.id)
    upstream_ids = [edge.upstream_asset_id for edge in upstream_edges]
    downstream_ids = [edge.downstream_asset_id for edge in downstream_edges]

    upstream_assets: list[DataAsset] = []
    downstream_assets: list[DataAsset] = []
    if upstream_ids:
        result = await db.execute(
            select(DataAsset).where(
                DataAsset.project_id == context.project.id,
                DataAsset.id.in_(upstream_ids),
            )
        )
        upstream_assets = list(result.scalars().all())
    if downstream_ids:
        result = await db.execute(
            select(DataAsset).where(
                DataAsset.project_id == context.project.id,
                DataAsset.id.in_(downstream_ids),
            )
        )
        downstream_assets = list(result.scalars().all())

    related_pipelines_result = await db.execute(
        select(Pipeline).where(
            Pipeline.project_id == context.project.id,
            Pipeline.topic_name == asset.object_name,
        )
    )
    related_pipelines = list(related_pipelines_result.scalars().all())

    related_event_codes = sorted({item.event_code for item in related_pipelines})
    related_events: list[TrackingEvent] = []
    if related_event_codes:
        events_result = await db.execute(
            select(TrackingEvent).where(
                TrackingEvent.project_id == context.project.id,
                TrackingEvent.code.in_(related_event_codes),
            )
        )
        related_events = list(events_result.scalars().all())

    related_event_ids = [item.id for item in related_events]
    quality_rules: list[DataQualityRule] = []
    rule_conditions = [DataQualityRule.asset_id == asset.id]
    if related_event_ids:
        rule_conditions.append(DataQualityRule.event_id.in_(related_event_ids))
    rules_result = await db.execute(
        select(DataQualityRule).where(
            DataQualityRule.project_id == context.project.id,
            or_(*rule_conditions),
        )
    )
    quality_rules = list(rules_result.scalars().all())

    pipeline_ids = [item.id for item in related_pipelines]
    alerts: list[Alert] = []
    if pipeline_ids:
        alerts_result = await db.execute(
            select(Alert)
            .where(
                Alert.project_id == context.project.id,
                Alert.source_type == "PIPELINE",
                Alert.source_id.in_([str(item) for item in pipeline_ids]),
            )
            .order_by(Alert.created_at.desc())
            .limit(30)
        )
        alerts = list(alerts_result.scalars().all())

    changes = await change_repo.get_by_asset(asset.id)

    return success_response(
        {
            "asset": _asset_to_dict(asset),
            "lineage": {
                "upstream": [_asset_to_dict(item) for item in upstream_assets],
                "downstream": [_asset_to_dict(item) for item in downstream_assets],
            },
            "quality": {
                "rules": [
                    {
                        "id": rule.id,
                        "name": rule.name,
                        "rule_type": rule.rule_type,
                        "target_field": rule.target_field,
                        "operator": rule.operator,
                        "threshold": rule.threshold,
                        "severity": rule.severity,
                        "status": rule.status,
                        "version": rule.version,
                        "updated_at": rule.updated_at.isoformat(),
                    }
                    for rule in quality_rules
                ],
                "alerts": [
                    {
                        "id": alert.id,
                        "source_type": alert.source_type,
                        "source_id": alert.source_id,
                        "severity": alert.severity,
                        "title": alert.title,
                        "description": alert.description,
                        "status": alert.status,
                        "created_at": alert.created_at.isoformat(),
                    }
                    for alert in alerts
                ],
            },
            "relations": {
                "events": [
                    {
                        "id": item.id,
                        "code": item.code,
                        "name": item.name,
                        "governance_status": item.governance_status,
                    }
                    for item in related_events
                ],
                "pipelines": [
                    {
                        "id": item.id,
                        "event_code": item.event_code,
                        "topic_name": item.topic_name,
                        "flink_job_name": item.flink_job_name,
                        "status": item.status,
                        "updated_at": item.updated_at.isoformat(),
                    }
                    for item in related_pipelines
                ],
            },
            "version_history": [
                {
                    "id": item.id,
                    "from_version": item.from_version,
                    "to_version": item.to_version,
                    "diff": item.diff,
                    "actor_id": item.actor_id,
                    "created_at": item.created_at.isoformat(),
                }
                for item in changes
            ],
        }
    )


@router.patch("/assets/{asset_id}")
async def update_data_asset(
    asset_id: int,
    request: DataAssetUpdate,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    asset_repo = DataAssetRepository(db)
    lineage_repo = DataAssetLineageRepository(db)
    change_repo = DataAssetChangeLogRepository(db)
    audit_repo = BaseRepository(AuditLog, db)

    asset = await asset_repo.get(asset_id)
    if not asset or asset.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")

    patch_data = {k: v for k, v in request.model_dump().items() if v is not None}
    patch_data.pop("upstream_asset_ids", None)
    patch_data.pop("downstream_asset_ids", None)
    if "status" in patch_data:
        patch_data["status"] = str(patch_data["status"]).upper()
        if patch_data["status"] not in {item.value for item in DataAssetStatus}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported status: {patch_data['status']}")

    before = _asset_to_dict(asset)
    diff = _build_diff(before, patch_data)

    lineage_diff: dict[str, Any] = {}
    if request.upstream_asset_ids is not None:
        await _validate_lineage_asset_ids(asset_repo, context.project.id, request.upstream_asset_ids)
        old_upstream = sorted([item.upstream_asset_id for item in await lineage_repo.get_upstream(context.project.id, asset.id)])
        new_upstream = sorted(set(request.upstream_asset_ids))
        if old_upstream != new_upstream:
            await lineage_repo.replace_upstream(context.project.id, asset.id, new_upstream)
            lineage_diff["upstream_asset_ids"] = {"before": old_upstream, "after": new_upstream}
    if request.downstream_asset_ids is not None:
        await _validate_lineage_asset_ids(asset_repo, context.project.id, request.downstream_asset_ids)
        old_downstream = sorted([item.downstream_asset_id for item in await lineage_repo.get_downstream(context.project.id, asset.id)])
        new_downstream = sorted(set(request.downstream_asset_ids))
        if old_downstream != new_downstream:
            await lineage_repo.replace_downstream(context.project.id, asset.id, new_downstream)
            lineage_diff["downstream_asset_ids"] = {"before": old_downstream, "after": new_downstream}

    if not diff and not lineage_diff:
        return success_response(_asset_to_dict(asset), message="No changes detected", code="DATA_ASSET_NO_CHANGES")

    next_version = _bump_patch_version(asset.version)
    patch_data["version"] = next_version
    updated = await asset_repo.update(asset, patch_data)

    merged_diff = {**diff, **lineage_diff}
    await change_repo.create(
        {
            "asset_id": updated.id,
            "project_id": updated.project_id,
            "from_version": before["version"],
            "to_version": next_version,
            "diff": merged_diff,
            "actor_id": context.actor_id,
        }
    )
    await audit_repo.create(
        {
            "action": "DATA_ASSET_UPDATE",
            "entity_type": "DATA_ASSET",
            "entity_id": str(updated.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "from_version": before["version"],
                    "to_version": next_version,
                    "diff": merged_diff,
                },
                ensure_ascii=True,
            ),
        }
    )
    return success_response(_asset_to_dict(updated), message="Data asset updated", code="DATA_ASSET_UPDATED")
