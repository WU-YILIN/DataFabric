import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import EventGovernanceStatus, EventStatus, TrackingEvent
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.data_quality_rule_repo import DataQualityRuleRepository
from src.infrastructure.database.repositories.event_change_log_repo import EventChangeLogRepository
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()


def _event_to_dict(event: TrackingEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "code": event.code,
        "name": event.name,
        "description": event.description,
        "properties": event.properties,
        "domain": event.domain,
        "status": event.status,
        "version": event.version,
        "owner": event.owner,
        "tags": event.tags,
        "governance_status": event.governance_status,
        "project_id": event.project_id,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


def _dq_rule_to_dict(rule: DataQualityRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "name": rule.name,
        "asset_id": rule.asset_id,
        "rule_type": rule.rule_type,
        "target_field": rule.target_field,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "alert_channels": rule.alert_channels,
        "severity": rule.severity,
        "status": rule.status,
        "description": rule.description,
        "version": rule.version,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


def _bump_patch_version(version: str) -> str:
    try:
        major, minor, patch = [int(item) for item in version.split(".")]
    except Exception:
        major, minor, patch = 1, 0, 0
    patch += 1
    return f"{major}.{minor}.{patch}"


def _build_event_diff(before: dict[str, Any], after_patch: dict[str, Any]) -> dict[str, Any]:
    changed: dict[str, Any] = {}
    for key, new_value in after_patch.items():
        old_value = before.get(key)
        if old_value != new_value:
            changed[key] = {"before": old_value, "after": new_value}
    return changed


class EventCreate(BaseModel):
    code: str = Field(..., min_length=3, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    description: str = Field(default="")
    properties: dict = Field(default_factory=dict)
    domain: str = Field(..., min_length=2, max_length=100)
    owner: str | None = None
    tags: list[str] = Field(default_factory=list)
    status: str = EventStatus.DRAFT.value


class EventUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    properties: dict | None = None
    domain: str | None = None
    owner: str | None = None
    tags: list[str] | None = None
    status: str | None = None


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_event(
    event_in: EventCreate,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = EventRepository(db)
    audit_repo = BaseRepository(AuditLog, db)
    existing = await repo.get_by_code(event_in.code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Event code already exists: {event_in.code}",
        )

    event_data = event_in.model_dump()
    event_data["project_id"] = context.project.id
    event_data["governance_status"] = EventGovernanceStatus.NOT_CHECKED.value
    event_data["status"] = (event_in.status or EventStatus.DRAFT.value).lower()

    event = await repo.create(event_data)
    await audit_repo.create(
        {
            "action": "EVENT_CREATE",
            "entity_type": "TRACKING_EVENT",
            "entity_id": event.code,
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "status": event.status,
                    "owner": event.owner,
                    "tags": event.tags,
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(_event_to_dict(event), message="Event created", code="EVENT_CREATED")


@router.get("/")
async def list_events(
    q: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    governance_status: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    repo = EventRepository(db)
    events = await repo.list_by_project_filtered(
        project_id=context.project.id,
        q=q,
        domain=domain,
        owner=owner,
        status=status_filter.lower() if status_filter else None,
        governance_status=governance_status,
        limit=limit,
    )
    return success_response([_event_to_dict(event) for event in events])


@router.get("/{event_id}/detail")
async def get_event_detail(
    event_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    event_repo = EventRepository(db)
    event = await event_repo.get(event_id)
    if not event or event.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    governance_result = await db.execute(
        select(GovernanceCheck)
        .where(
            GovernanceCheck.project_id == context.project.id,
            or_(
                GovernanceCheck.event_id == event.id,
                GovernanceCheck.event_name == event.name,
            ),
        )
        .order_by(GovernanceCheck.created_at.desc())
        .limit(50)
    )
    governance_rows = list(governance_result.scalars().all())

    pipeline_result = await db.execute(
        select(Pipeline)
        .where(
            Pipeline.project_id == context.project.id,
            Pipeline.event_code == event.code,
        )
        .order_by(Pipeline.updated_at.desc())
    )
    pipelines = list(pipeline_result.scalars().all())

    changes = await EventChangeLogRepository(db).get_by_event(event.id)
    dq_rules = await DataQualityRuleRepository(db).get_by_event(context.project.id, event.id)

    return success_response(
        {
            "event": _event_to_dict(event),
            "governance_records": [
                {
                    "id": row.id,
                    "verdict": row.verdict,
                    "score": row.score,
                    "reasoning": row.reasoning,
                    "recommended_code": row.recommended_code,
                    "model_name": row.model_name,
                    "risks": row.result_payload.get("risks", []) if isinstance(row.result_payload, dict) else [],
                    "suggestions": row.result_payload.get("suggestions", [])
                    if isinstance(row.result_payload, dict)
                    else [],
                    "actor_id": row.actor_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in governance_rows
            ],
            "related_pipelines": [
                {
                    "id": row.id,
                    "event_code": row.event_code,
                    "status": row.status,
                    "topic_name": row.topic_name,
                    "flink_job_name": row.flink_job_name,
                    "updated_at": row.updated_at.isoformat(),
                }
                for row in pipelines
            ],
            "data_quality_rules": [_dq_rule_to_dict(rule) for rule in dq_rules],
            "version_history": [
                {
                    "id": row.id,
                    "from_version": row.from_version,
                    "to_version": row.to_version,
                    "diff": row.diff,
                    "actor_id": row.actor_id,
                    "created_at": row.created_at.isoformat(),
                }
                for row in changes
            ],
        }
    )


@router.patch("/{event_id}")
async def update_event(
    event_id: int,
    event_in: EventUpdate,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    event_repo = EventRepository(db)
    audit_repo = BaseRepository(AuditLog, db)
    change_repo = EventChangeLogRepository(db)
    event = await event_repo.get(event_id)
    if not event or event.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    patch_data = {k: v for k, v in event_in.model_dump().items() if v is not None}
    if "status" in patch_data:
        patch_data["status"] = str(patch_data["status"]).lower()

    before = _event_to_dict(event)
    diff = _build_event_diff(before, patch_data)
    if not diff:
        return success_response(_event_to_dict(event), message="No changes detected", code="EVENT_NO_CHANGES")

    next_version = _bump_patch_version(event.version)
    patch_data["version"] = next_version
    updated = await event_repo.update(event, patch_data)

    await change_repo.create(
        {
            "event_id": updated.id,
            "project_id": updated.project_id,
            "from_version": before["version"],
            "to_version": next_version,
            "diff": diff,
            "actor_id": context.actor_id,
        }
    )
    await audit_repo.create(
        {
            "action": "EVENT_UPDATE",
            "entity_type": "TRACKING_EVENT",
            "entity_id": updated.code,
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
    return success_response(_event_to_dict(updated), message="Event updated", code="EVENT_UPDATED")


@router.post("/{event_id}/submit-governance")
async def submit_event_for_governance(
    event_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    event = await EventRepository(db).get(event_id)
    if not event or event.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    payload = {
        "event_id": event.id,
        "name": event.name,
        "description": event.description or "",
        "properties": event.properties,
    }
    return success_response(
        payload,
        message="Ready for governance check",
        code="EVENT_GOVERNANCE_READY",
    )
