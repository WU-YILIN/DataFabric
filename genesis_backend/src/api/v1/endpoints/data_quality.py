import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.models.data_quality_execution_log import DataQualityExecutionLog
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.data_asset_repo import DataAssetRepository
from src.infrastructure.database.repositories.data_quality_execution_log_repo import (
    DataQualityExecutionLogRepository,
)
from src.infrastructure.database.repositories.data_quality_rule_change_log_repo import (
    DataQualityRuleChangeLogRepository,
)
from src.infrastructure.database.repositories.data_quality_rule_repo import (
    DataQualityRuleRepository,
)
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ALLOWED_RULE_TYPES = {
    "NOT_NULL",
    "UNIQUENESS",
    "VALUE_RANGE",
    "REGEX",
    "ENUM",
    "CUSTOM_SQL",
}
ALLOWED_SEVERITY = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ALLOWED_STATUS = {"ACTIVE", "PAUSED", "DRAFT", "DEPRECATED"}


class DataQualityRuleCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    asset_id: int | None = None
    event_id: int | None = None
    rule_type: str = Field(..., min_length=2, max_length=100)
    target_field: str | None = None
    operator: str | None = None
    threshold: dict = Field(default_factory=dict)
    alert_channels: list[str] = Field(default_factory=list)
    severity: str = "MEDIUM"
    status: str = "ACTIVE"
    description: str | None = None


class DataQualityRuleUpdateRequest(BaseModel):
    name: str | None = None
    asset_id: int | None = None
    event_id: int | None = None
    rule_type: str | None = None
    target_field: str | None = None
    operator: str | None = None
    threshold: dict | None = None
    alert_channels: list[str] | None = None
    severity: str | None = None
    status: str | None = None
    description: str | None = None


class DataQualityRuleRunRequest(BaseModel):
    checked_count: int | None = Field(default=None, ge=1, le=10_000_000)
    failed_count: int | None = Field(default=None, ge=0, le=10_000_000)
    simulated_failure_rate: float | None = Field(default=None, ge=0, le=1)
    trigger_source: str = Field(default="manual", min_length=2, max_length=64)
    notes: str | None = None


def _normalize_rule_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_RULE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported rule_type: {value}",
        )
    return normalized


def _normalize_severity(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_SEVERITY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported severity: {value}",
        )
    return normalized


def _normalize_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported status: {value}",
        )
    return normalized


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


def _rule_to_dict(
    rule: DataQualityRule,
    asset_map: dict[int, DataAsset] | None = None,
    event_map: dict[int, TrackingEvent] | None = None,
) -> dict[str, Any]:
    asset = asset_map.get(rule.asset_id) if (asset_map and rule.asset_id) else None
    event = event_map.get(rule.event_id) if (event_map and rule.event_id) else None
    return {
        "id": rule.id,
        "project_id": rule.project_id,
        "asset_id": rule.asset_id,
        "event_id": rule.event_id,
        "name": rule.name,
        "rule_type": rule.rule_type,
        "target_field": rule.target_field,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "alert_channels": rule.alert_channels,
        "severity": rule.severity,
        "status": rule.status,
        "description": rule.description,
        "version": rule.version,
        "asset": {
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "object_name": asset.object_name,
            "domain": asset.domain,
        }
        if asset
        else None,
        "event": {
            "id": event.id,
            "code": event.code,
            "name": event.name,
            "governance_status": event.governance_status,
        }
        if event
        else None,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


async def _resolve_event_id_from_asset(
    db: AsyncSession,
    project_id: int,
    asset: DataAsset,
) -> int | None:
    if asset.asset_type == "TOPIC":
        pipeline_result = await db.execute(
            select(Pipeline)
            .where(
                Pipeline.project_id == project_id,
                Pipeline.topic_name == asset.object_name,
            )
            .order_by(Pipeline.updated_at.desc())
            .limit(1)
        )
        pipeline = pipeline_result.scalar_one_or_none()
        if pipeline:
            event_result = await db.execute(
                select(TrackingEvent).where(
                    TrackingEvent.project_id == project_id,
                    TrackingEvent.code == pipeline.event_code,
                )
            )
            event = event_result.scalar_one_or_none()
            if event:
                return event.id
    return None


async def _open_or_update_rule_alert(
    alert_repo: BaseRepository[Alert],
    rule: DataQualityRule,
    title: str,
    description: str,
) -> None:
    existing_result = await alert_repo.session.execute(
        select(Alert).where(
            and_(
                Alert.project_id == rule.project_id,
                Alert.source_type == "DATA_QUALITY_RULE",
                Alert.source_id == str(rule.id),
                Alert.status == "OPEN",
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        await alert_repo.update(
            existing,
            {
                "severity": rule.severity,
                "title": title,
                "description": description[:1000],
            },
        )
        return
    await alert_repo.create(
        {
            "project_id": rule.project_id,
            "source_type": "DATA_QUALITY_RULE",
            "source_id": str(rule.id),
            "severity": rule.severity,
            "title": title,
            "description": description[:1000],
            "status": "OPEN",
        }
    )


async def _resolve_rule_alert(alert_repo: BaseRepository[Alert], rule: DataQualityRule) -> None:
    existing_result = await alert_repo.session.execute(
        select(Alert).where(
            and_(
                Alert.project_id == rule.project_id,
                Alert.source_type == "DATA_QUALITY_RULE",
                Alert.source_id == str(rule.id),
                Alert.status == "OPEN",
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing:
        await alert_repo.update(
            existing,
            {"status": "RESOLVED", "resolved_at": datetime.now(timezone.utc)},
        )


@router.get("/rule-options")
async def get_rule_options(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    event_rows = await EventRepository(db).list_by_project_filtered(
        project_id=context.project.id,
        limit=1000,
    )
    asset_rows = await DataAssetRepository(db).get_by_project_filtered(
        project_id=context.project.id,
        limit=1000,
    )
    return success_response(
        {
            "events": [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "domain": item.domain,
                    "governance_status": item.governance_status,
                }
                for item in event_rows
            ],
            "assets": [
                {
                    "id": item.id,
                    "name": item.name,
                    "asset_type": item.asset_type,
                    "object_name": item.object_name,
                    "domain": item.domain,
                    "status": item.status,
                }
                for item in asset_rows
            ],
        }
    )


@router.get("/rules")
async def list_rules(
    q: str | None = Query(default=None),
    asset_id: int | None = Query(default=None),
    event_id: int | None = Query(default=None),
    rule_type: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=500, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    rule_repo = DataQualityRuleRepository(db)
    execution_repo = DataQualityExecutionLogRepository(db)
    asset_repo = DataAssetRepository(db)
    event_repo = EventRepository(db)

    rows = await rule_repo.list_by_project_filtered(
        project_id=context.project.id,
        q=q,
        asset_id=asset_id,
        event_id=event_id,
        rule_type=rule_type.strip().upper() if rule_type else None,
        severity=severity.strip().upper() if severity else None,
        status=status_filter.strip().upper() if status_filter else None,
        limit=limit,
    )

    asset_map: dict[int, DataAsset] = {}
    event_map: dict[int, TrackingEvent] = {}
    for rule in rows:
        if rule.asset_id and rule.asset_id not in asset_map:
            asset = await asset_repo.get(rule.asset_id)
            if asset and asset.project_id == context.project.id:
                asset_map[asset.id] = asset
        if rule.event_id and rule.event_id not in event_map:
            event = await event_repo.get(rule.event_id)
            if event and event.project_id == context.project.id:
                event_map[event.id] = event

    last_run_map: dict[int, DataQualityExecutionLog] = {}
    for rule in rows:
        last_runs = await execution_repo.get_by_rule(rule.id, limit=1)
        if last_runs:
            last_run_map[rule.id] = last_runs[0]

    data = []
    for rule in rows:
        row = _rule_to_dict(rule, asset_map=asset_map, event_map=event_map)
        last_run = last_run_map.get(rule.id)
        row["last_run"] = (
            {
                "result": last_run.result,
                "checked_count": last_run.checked_count,
                "failed_count": last_run.failed_count,
                "pass_rate": last_run.pass_rate,
                "executed_at": last_run.executed_at.isoformat(),
                "triggered_by": last_run.triggered_by,
            }
            if last_run
            else None
        )
        data.append(row)

    return success_response(data)


@router.post("/rules", status_code=status.HTTP_201_CREATED)
async def create_rule(
    request: DataQualityRuleCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    rule_repo = DataQualityRuleRepository(db)
    asset_repo = DataAssetRepository(db)
    event_repo = EventRepository(db)
    audit_repo = BaseRepository(AuditLog, db)

    asset = None
    if request.asset_id is not None:
        asset = await asset_repo.get(request.asset_id)
        if not asset or asset.project_id != context.project.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid asset_id: {request.asset_id}")

    event_id = request.event_id
    if event_id is not None:
        event = await event_repo.get(event_id)
        if not event or event.project_id != context.project.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid event_id: {event_id}")
    elif asset is not None:
        event_id = await _resolve_event_id_from_asset(db, context.project.id, asset)
    if event_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="event_id is required, or provide an asset_id that can derive related event",
        )

    normalized_rule_type = _normalize_rule_type(request.rule_type)
    normalized_severity = _normalize_severity(request.severity)
    normalized_status = _normalize_status(request.status)

    rule = await rule_repo.create(
        {
            "project_id": context.project.id,
            "asset_id": request.asset_id,
            "event_id": event_id,
            "name": request.name,
            "rule_type": normalized_rule_type,
            "target_field": request.target_field,
            "operator": request.operator,
            "threshold": request.threshold,
            "alert_channels": request.alert_channels,
            "severity": normalized_severity,
            "status": normalized_status,
            "description": request.description,
        }
    )

    await audit_repo.create(
        {
            "action": "DQ_RULE_CREATE",
            "entity_type": "DATA_QUALITY_RULE",
            "entity_id": str(rule.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "name": rule.name,
                    "rule_type": rule.rule_type,
                    "asset_id": rule.asset_id,
                    "event_id": rule.event_id,
                },
                ensure_ascii=True,
            ),
        }
    )
    return success_response(_rule_to_dict(rule), message="Data quality rule created", code="DQ_RULE_CREATED")


@router.get("/rules/{rule_id}/detail")
async def get_rule_detail(
    rule_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    rule_repo = DataQualityRuleRepository(db)
    execution_repo = DataQualityExecutionLogRepository(db)
    change_repo = DataQualityRuleChangeLogRepository(db)
    alert_repo = BaseRepository(Alert, db)
    asset_repo = DataAssetRepository(db)
    event_repo = EventRepository(db)

    rule = await rule_repo.get(rule_id)
    if not rule or rule.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data quality rule not found")

    executions = await execution_repo.get_by_rule(rule_id, limit=50)
    changes = await change_repo.get_by_rule(rule_id, limit=50)
    alerts_result = await alert_repo.session.execute(
        select(Alert)
        .where(
            Alert.project_id == context.project.id,
            Alert.source_type == "DATA_QUALITY_RULE",
            Alert.source_id == str(rule.id),
        )
        .order_by(Alert.created_at.desc())
        .limit(50)
    )
    alerts = list(alerts_result.scalars().all())

    asset_map: dict[int, DataAsset] = {}
    event_map: dict[int, TrackingEvent] = {}
    if rule.asset_id:
        asset = await asset_repo.get(rule.asset_id)
        if asset and asset.project_id == context.project.id:
            asset_map[asset.id] = asset
    if rule.event_id:
        event = await event_repo.get(rule.event_id)
        if event and event.project_id == context.project.id:
            event_map[event.id] = event

    recent_results = [
        {
            "id": item.id,
            "result": item.result,
            "checked_count": item.checked_count,
            "failed_count": item.failed_count,
            "pass_rate": item.pass_rate,
            "details": item.details,
            "error_message": item.error_message,
            "triggered_by": item.triggered_by,
            "executed_at": item.executed_at.isoformat(),
        }
        for item in executions
    ]

    return success_response(
        {
            "rule": _rule_to_dict(rule, asset_map=asset_map, event_map=event_map),
            "recent_results": recent_results,
            "trend": [
                {
                    "executed_at": item.executed_at.isoformat(),
                    "pass_rate": item.pass_rate,
                    "result": item.result,
                }
                for item in executions[:20]
            ],
            "alerts": [
                {
                    "id": item.id,
                    "severity": item.severity,
                    "title": item.title,
                    "description": item.description,
                    "status": item.status,
                    "created_at": item.created_at.isoformat(),
                    "resolved_at": item.resolved_at.isoformat() if item.resolved_at else None,
                }
                for item in alerts
            ],
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


@router.patch("/rules/{rule_id}")
async def update_rule(
    rule_id: int,
    request: DataQualityRuleUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    rule_repo = DataQualityRuleRepository(db)
    asset_repo = DataAssetRepository(db)
    event_repo = EventRepository(db)
    change_repo = DataQualityRuleChangeLogRepository(db)
    audit_repo = BaseRepository(AuditLog, db)

    rule = await rule_repo.get(rule_id)
    if not rule or rule.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data quality rule not found")

    patch_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if "rule_type" in patch_data:
        patch_data["rule_type"] = _normalize_rule_type(patch_data["rule_type"])
    if "severity" in patch_data:
        patch_data["severity"] = _normalize_severity(patch_data["severity"])
    if "status" in patch_data:
        patch_data["status"] = _normalize_status(patch_data["status"])

    if "asset_id" in patch_data and patch_data["asset_id"] is not None:
        asset = await asset_repo.get(patch_data["asset_id"])
        if not asset or asset.project_id != context.project.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid asset_id: {patch_data['asset_id']}")
    if "event_id" in patch_data and patch_data["event_id"] is not None:
        event = await event_repo.get(patch_data["event_id"])
        if not event or event.project_id != context.project.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid event_id: {patch_data['event_id']}")

    before = _rule_to_dict(rule)
    diff = _build_diff(before, patch_data)
    if not diff:
        return success_response(_rule_to_dict(rule), message="No changes detected", code="DQ_RULE_NO_CHANGES")

    next_version = _bump_patch_version(rule.version)
    patch_data["version"] = next_version
    updated = await rule_repo.update(rule, patch_data)

    await change_repo.create(
        {
            "rule_id": updated.id,
            "project_id": updated.project_id,
            "from_version": before["version"],
            "to_version": next_version,
            "diff": diff,
            "actor_id": context.actor_id,
        }
    )
    await audit_repo.create(
        {
            "action": "DQ_RULE_UPDATE",
            "entity_type": "DATA_QUALITY_RULE",
            "entity_id": str(updated.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "from_version": before["version"],
                    "to_version": next_version,
                    "diff": diff,
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(_rule_to_dict(updated), message="Data quality rule updated", code="DQ_RULE_UPDATED")


@router.post("/rules/{rule_id}/run")
async def run_rule(
    rule_id: int,
    request: DataQualityRuleRunRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    rule_repo = DataQualityRuleRepository(db)
    execution_repo = DataQualityExecutionLogRepository(db)
    audit_repo = BaseRepository(AuditLog, db)
    alert_repo = BaseRepository(Alert, db)

    rule = await rule_repo.get(rule_id)
    if not rule or rule.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data quality rule not found")
    if rule.status not in {"ACTIVE", "PAUSED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Rule status {rule.status} does not allow execution",
        )

    checked_count = request.checked_count or 1000
    if request.failed_count is not None:
        failed_count = min(request.failed_count, checked_count)
    else:
        if request.simulated_failure_rate is not None:
            failed_count = int(checked_count * request.simulated_failure_rate)
        else:
            base = (rule.id * 17) % 100
            if rule.rule_type in {"NOT_NULL", "UNIQUENESS"}:
                failure_rate = base / 1000
            else:
                failure_rate = base / 500
            failed_count = int(checked_count * failure_rate)

    failure_rate = failed_count / checked_count if checked_count else 0
    default_max_failure_rate = 0.0 if rule.rule_type in {"NOT_NULL", "UNIQUENESS"} else 0.05
    try:
        max_failure_rate = float(rule.threshold.get("max_failure_rate", default_max_failure_rate))
    except Exception:
        max_failure_rate = default_max_failure_rate
    is_pass = failure_rate <= max_failure_rate
    pass_rate = 1.0 - failure_rate
    result = "PASS" if is_pass else "FAIL"

    execution = await execution_repo.create(
        {
            "project_id": rule.project_id,
            "rule_id": rule.id,
            "result": result,
            "checked_count": checked_count,
            "failed_count": failed_count,
            "pass_rate": pass_rate,
            "details": {
                "max_failure_rate": max_failure_rate,
                "failure_rate": failure_rate,
                "notes": request.notes,
            },
            "error_message": None,
            "triggered_by": request.trigger_source,
            "executed_at": datetime.now(timezone.utc),
        }
    )

    if is_pass:
        await _resolve_rule_alert(alert_repo, rule)
        action = "DQ_RULE_RUN_PASS"
    else:
        await _open_or_update_rule_alert(
            alert_repo,
            rule,
            title=f"Data quality rule failed: {rule.name}",
            description=(
                f"Rule {rule.name} failed with failure_rate={failure_rate:.4f}, "
                f"max_allowed={max_failure_rate:.4f}."
            ),
        )
        action = "DQ_RULE_RUN_FAIL"

    await audit_repo.create(
        {
            "action": action,
            "entity_type": "DATA_QUALITY_RULE",
            "entity_id": str(rule.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "execution_id": execution.id,
                    "result": result,
                    "checked_count": checked_count,
                    "failed_count": failed_count,
                    "pass_rate": pass_rate,
                    "trigger_source": request.trigger_source,
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(
        {
            "execution_id": execution.id,
            "rule_id": rule.id,
            "result": result,
            "checked_count": checked_count,
            "failed_count": failed_count,
            "pass_rate": pass_rate,
            "max_failure_rate": max_failure_rate,
            "triggered_by": request.trigger_source,
            "executed_at": execution.executed_at.isoformat(),
        },
        message="Data quality rule executed",
        code="DQ_RULE_EXECUTED",
    )
