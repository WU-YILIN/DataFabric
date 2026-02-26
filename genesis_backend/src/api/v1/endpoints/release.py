import json
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.release_change_action_history import ReleaseChangeActionHistory
from src.infrastructure.database.models.release_change_request import ReleaseChangeRequest
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

CHANGE_TYPES = {
    "EVENT_CHANGE",
    "DQ_RULE_CHANGE",
    "PIPELINE_CHANGE",
    "SCHEDULER_CHANGE",
    "POLICY_CHANGE",
    "INTEGRATION_CHANGE",
    "ACCESS_CHANGE",
    "OTHER",
}
PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
CHANGE_STATUSES = {
    "PENDING_APPROVAL",
    "REVISION_REQUIRED",
    "APPROVED",
    "SCHEDULED",
    "IN_PROGRESS",
    "COMPLETED",
    "FAILED",
    "ROLLED_BACK",
    "REJECTED",
    "CANCELLED",
}
WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR", "APPROVER"}
APPROVER_ROLES = {"OWNER", "ADMIN", "APPROVER"}
ACTION_TYPES = {
    "APPROVE",
    "REJECT",
    "REQUEST_REVISION",
    "SCHEDULE",
    "EXECUTE",
    "ROLLBACK",
    "CANCEL",
}

SOURCE_ROUTE_MAP = {
    "EVENT": "/events",
    "TRACKING_EVENT": "/events",
    "DQ_RULE": "/data-quality",
    "PIPELINE": "/pipelines",
    "SCHEDULER_DAG": "/scheduler",
    "POLICY_RULE": "/policy-center",
    "INTEGRATION": "/integration-hub",
    "ACCESS": "/access",
}


class ReleaseChangeCreateRequest(BaseModel):
    change_type: str = Field(..., min_length=2, max_length=64)
    source_type: str = Field(..., min_length=2, max_length=64)
    source_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    priority: str = Field(default="MEDIUM", max_length=32)

    impact_scope: dict[str, Any] = Field(default_factory=dict)
    diff_payload: dict[str, Any] | None = None
    before_payload: dict[str, Any] = Field(default_factory=dict)
    after_payload: dict[str, Any] = Field(default_factory=dict)

    release_plan_payload: dict[str, Any] = Field(default_factory=dict)
    rollback_plan_payload: dict[str, Any] = Field(default_factory=dict)
    current_approver_role: str | None = Field(default="APPROVER", max_length=64)
    manual_review_note: str | None = Field(default=None, max_length=1000)


class ReleaseChangeActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
    scheduled_at: str | None = Field(default=None)
    simulate_failure: bool = Field(default=False)
    failure_reason: str | None = Field(default=None, max_length=1000)
    trigger_rollback: bool = Field(default=True)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _normalize_enum(value: str, *, allowed: set[str], field_name: str) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported {field_name}: {value}")
    return normalized


def _parse_iso_datetime(value: str | None, *, field_name: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid {field_name}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Release center requires bearer user context")


def _require_write_role(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in WRITE_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (WRITE_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for release mutation")


def _require_approver_role(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in APPROVER_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (APPROVER_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")


def _tenant_id_from_context(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


def _actor(context: RequestContext) -> str:
    return context.user.email if context.user else parse_actor(context.actor_id)


def _compute_diff(before_payload: dict[str, Any], after_payload: dict[str, Any]) -> dict[str, Any]:
    before_keys = set(before_payload.keys())
    after_keys = set(after_payload.keys())
    added = sorted(list(after_keys - before_keys))
    removed = sorted(list(before_keys - after_keys))
    changed = []
    for key in sorted(before_keys & after_keys):
        before_value = before_payload.get(key)
        after_value = after_payload.get(key)
        if before_value != after_value:
            changed.append(
                {
                    "field": key,
                    "before": before_value,
                    "after": after_value,
                }
            )
    return {
        "added_fields": added,
        "removed_fields": removed,
        "changed_fields": changed,
        "change_count": len(added) + len(removed) + len(changed),
    }


def _evaluate_risk(
    *,
    change_type: str,
    priority: str,
    diff_payload: dict[str, Any],
    impact_scope: dict[str, Any],
    manual_review_note: str | None,
) -> dict[str, Any]:
    score = 0.15
    factors = []

    if priority == "HIGH":
        score += 0.2
        factors.append("high_priority")
    elif priority == "CRITICAL":
        score += 0.35
        factors.append("critical_priority")

    type_weights = {
        "PIPELINE_CHANGE": 0.2,
        "POLICY_CHANGE": 0.18,
        "ACCESS_CHANGE": 0.22,
        "INTEGRATION_CHANGE": 0.18,
        "DQ_RULE_CHANGE": 0.15,
        "EVENT_CHANGE": 0.1,
        "SCHEDULER_CHANGE": 0.12,
        "OTHER": 0.1,
    }
    score += type_weights.get(change_type, 0.1)

    diff_count = int(diff_payload.get("change_count") or 0)
    if diff_count >= 12:
        score += 0.18
        factors.append("large_diff")
    elif diff_count >= 5:
        score += 0.1
        factors.append("medium_diff")
    elif diff_count > 0:
        score += 0.04

    impact_project_count = len(impact_scope.get("project_ids", [])) if isinstance(impact_scope.get("project_ids"), list) else 0
    if impact_project_count >= 3:
        score += 0.18
        factors.append("multi_project_impact")
    elif impact_project_count >= 1:
        score += 0.06

    if impact_scope.get("tenant_wide"):
        score += 0.15
        factors.append("tenant_wide")

    if manual_review_note:
        factors.append("manual_review_provided")

    score = max(0.0, min(0.99, round(score, 4)))
    level = "LOW"
    if score >= 0.75:
        level = "HIGH"
    elif score >= 0.45:
        level = "MEDIUM"

    auto_result = {
        "risk_score": score,
        "risk_level": level,
        "factors": factors,
    }
    return {
        "auto": auto_result,
        "manual": {
            "review_note": manual_review_note,
            "reviewed": bool(manual_review_note),
        },
        "final": auto_result,
    }


def _change_to_row(change: ReleaseChangeRequest) -> dict[str, Any]:
    return {
        "id": change.id,
        "change_type": change.change_type,
        "source": {
            "source_type": change.source_type,
            "source_id": change.source_id,
            "route": SOURCE_ROUTE_MAP.get(change.source_type, ""),
        },
        "title": change.title,
        "description": change.description,
        "priority": change.priority,
        "status": change.status,
        "impact_scope": change.impact_scope or {},
        "diff_payload": change.diff_payload or {},
        "before_payload": change.before_payload or {},
        "after_payload": change.after_payload or {},
        "risk_assessment": change.risk_assessment_payload or {},
        "release_plan": change.release_plan_payload or {},
        "rollback_plan": change.rollback_plan_payload or {},
        "requested_by": change.requested_by,
        "current_approver_role": change.current_approver_role,
        "approved_by": change.approved_by,
        "rejected_by": change.rejected_by,
        "approved_at": _to_iso(change.approved_at),
        "rejected_at": _to_iso(change.rejected_at),
        "scheduled_at": _to_iso(change.scheduled_at),
        "executed_at": _to_iso(change.executed_at),
        "completed_at": _to_iso(change.completed_at),
        "rolled_back_at": _to_iso(change.rolled_back_at),
        "created_at": _to_iso(change.created_at),
        "updated_at": _to_iso(change.updated_at),
    }


def _history_to_row(item: ReleaseChangeActionHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "action": item.action,
        "actor": item.actor,
        "note": item.note,
        "payload": item.payload or {},
        "created_at": _to_iso(item.created_at),
    }


async def _write_history(
    db: AsyncSession,
    *,
    change_id: int,
    project_id: int,
    action: str,
    actor: str,
    note: str | None,
    payload: dict[str, Any],
) -> ReleaseChangeActionHistory:
    return await BaseRepository(ReleaseChangeActionHistory, db).create(
        {
            "change_request_id": change_id,
            "project_id": project_id,
            "action": action,
            "actor": actor,
            "note": note,
            "payload": payload,
        }
    )


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    change_id: int | str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "RELEASE_CHANGE",
            "entity_id": str(change_id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


async def _open_release_alert(
    db: AsyncSession,
    *,
    project_id: int,
    change_id: int,
    title: str,
    description: str,
) -> Alert:
    source_id = f"change:{change_id}"
    existing_result = await db.execute(
        select(Alert).where(
            and_(
                Alert.project_id == project_id,
                Alert.source_type == "RELEASE",
                Alert.source_id == source_id,
                Alert.status == "OPEN",
            )
        )
    )
    existing = existing_result.scalar_one_or_none()
    repo = BaseRepository(Alert, db)
    if existing:
        return await repo.update(existing, {"severity": "HIGH", "title": title[:255], "description": description[:1000]})
    return await repo.create(
        {
            "project_id": project_id,
            "source_type": "RELEASE",
            "source_id": source_id,
            "severity": "HIGH",
            "title": title[:255],
            "description": description[:1000],
            "status": "OPEN",
        }
    )


async def _resolve_release_alert(
    db: AsyncSession,
    *,
    project_id: int,
    change_id: int,
    note: str,
) -> Alert | None:
    source_id = f"change:{change_id}"
    result = await db.execute(
        select(Alert)
        .where(
            and_(
                Alert.project_id == project_id,
                Alert.source_type == "RELEASE",
                Alert.source_id == source_id,
                Alert.status.in_(["OPEN", "ACKNOWLEDGED"]),
            )
        )
        .order_by(Alert.id.desc())
    )
    alert = result.scalars().first()
    if alert is None:
        return None
    return await BaseRepository(Alert, db).update(
        alert,
        {
            "status": "RESOLVED",
            "resolved_at": datetime.now(timezone.utc),
            "last_note": note[:1000],
        },
    )


async def _validate_project_in_tenant(
    db: AsyncSession,
    *,
    project_id: int,
    tenant_id: int,
) -> Project:
    result = await db.execute(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    project = result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


@router.get("/overview")
async def get_release_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    result = await db.execute(
        select(ReleaseChangeRequest).where(ReleaseChangeRequest.project_id == context.project.id)
    )
    changes = list(result.scalars().all())

    status_counter = Counter(item.status for item in changes)
    type_counter = Counter(item.change_type for item in changes)
    priority_counter = Counter(item.priority for item in changes)

    in_progress_statuses = {"APPROVED", "SCHEDULED", "IN_PROGRESS"}
    open_statuses = {"PENDING_APPROVAL", "REVISION_REQUIRED", "APPROVED", "SCHEDULED", "IN_PROGRESS", "FAILED"}
    high_risk_open = 0
    for item in changes:
        risk_level = str(
            ((item.risk_assessment_payload or {}).get("final") or {}).get("risk_level") or "LOW"
        ).upper()
        if risk_level == "HIGH" and item.status in open_statuses:
            high_risk_open += 1

    audit_result = await db.execute(
        select(AuditLog)
        .where(and_(AuditLog.entity_type == "RELEASE_CHANGE", build_project_audit_filter(context.project.id)))
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(20)
    )
    recent_activity = []
    for row in audit_result.scalars().all():
        details = _safe_json_loads(row.details)
        recent_activity.append(
            {
                "id": row.id,
                "timestamp": _to_iso(row.timestamp),
                "actor": parse_actor(row.user_id),
                "action": row.action,
                "change_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_changes": len(changes),
                "pending_approval": status_counter.get("PENDING_APPROVAL", 0),
                "in_progress": sum(status_counter.get(status_name, 0) for status_name in in_progress_statuses),
                "completed": status_counter.get("COMPLETED", 0),
                "failed": status_counter.get("FAILED", 0),
                "rolled_back": status_counter.get("ROLLED_BACK", 0),
                "high_risk_open": high_risk_open,
            },
            "status_distribution": [
                {"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())
            ],
            "type_distribution": [
                {"change_type": key, "count": type_counter[key]} for key in sorted(type_counter.keys())
            ],
            "priority_distribution": [
                {"priority": key, "count": priority_counter[key]} for key in sorted(priority_counter.keys())
            ],
            "recent_activity": recent_activity,
        }
    )


@router.get("/changes")
async def list_release_changes(
    q: str | None = Query(default=None),
    change_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    priority: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    requested_by: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    normalized_change_type = (
        _normalize_enum(change_type, allowed=CHANGE_TYPES, field_name="change_type") if change_type else None
    )
    normalized_status = (
        _normalize_enum(status_filter, allowed=CHANGE_STATUSES, field_name="status") if status_filter else None
    )
    normalized_priority = (
        _normalize_enum(priority, allowed=PRIORITIES, field_name="priority") if priority else None
    )
    normalized_source_type = source_type.strip().upper() if source_type else None
    normalized_requested_by = requested_by.strip().lower() if requested_by else None
    parsed_from = _parse_iso_datetime(date_from, field_name="date_from") if date_from else None
    parsed_to = _parse_iso_datetime(date_to, field_name="date_to") if date_to else None

    result = await db.execute(
        select(ReleaseChangeRequest)
        .where(ReleaseChangeRequest.project_id == context.project.id)
        .order_by(ReleaseChangeRequest.updated_at.desc(), ReleaseChangeRequest.id.desc())
    )
    rows = list(result.scalars().all())

    if normalized_change_type:
        rows = [item for item in rows if item.change_type == normalized_change_type]
    if normalized_status:
        rows = [item for item in rows if item.status == normalized_status]
    if normalized_priority:
        rows = [item for item in rows if item.priority == normalized_priority]
    if normalized_source_type:
        rows = [item for item in rows if item.source_type == normalized_source_type]
    if normalized_requested_by:
        rows = [item for item in rows if normalized_requested_by in item.requested_by.lower()]
    if parsed_from:
        rows = [item for item in rows if _as_utc(item.created_at) and _as_utc(item.created_at) >= parsed_from]
    if parsed_to:
        rows = [item for item in rows if _as_utc(item.created_at) and _as_utc(item.created_at) <= parsed_to]
    if q and q.strip():
        keyword = q.strip().lower()
        filtered = []
        for item in rows:
            searchable = " ".join(
                [
                    item.title,
                    item.description or "",
                    item.change_type,
                    item.source_type,
                    item.source_id,
                    item.requested_by,
                ]
            ).lower()
            if keyword in searchable:
                filtered.append(item)
        rows = filtered

    total = len(rows)
    page_rows = rows[offset : offset + limit]

    status_counter = Counter(item.status for item in rows)
    type_counter = Counter(item.change_type for item in rows)
    priority_counter = Counter(item.priority for item in rows)
    requester_counter = Counter(item.requested_by for item in rows)

    return success_response(
        {
            "items": [_change_to_row(item) for item in page_rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
                "change_types": [
                    {"change_type": key, "count": type_counter[key]} for key in sorted(type_counter.keys())
                ],
                "priorities": [
                    {"priority": key, "count": priority_counter[key]} for key in sorted(priority_counter.keys())
                ],
                "requesters": [
                    {"requested_by": key, "count": requester_counter[key]}
                    for key in sorted(requester_counter.keys())
                ],
            },
        }
    )


@router.get("/changes/{change_id}")
async def get_release_change_detail(
    change_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    change_result = await db.execute(
        select(ReleaseChangeRequest).where(
            ReleaseChangeRequest.id == change_id,
            ReleaseChangeRequest.project_id == context.project.id,
        )
    )
    change = change_result.scalar_one_or_none()
    if change is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")

    history_result = await db.execute(
        select(ReleaseChangeActionHistory)
        .where(
            ReleaseChangeActionHistory.change_request_id == change.id,
            ReleaseChangeActionHistory.project_id == context.project.id,
        )
        .order_by(ReleaseChangeActionHistory.created_at.desc(), ReleaseChangeActionHistory.id.desc())
    )
    history = list(history_result.scalars().all())

    return success_response(
        {
            "change": _change_to_row(change),
            "history": [_history_to_row(item) for item in history],
        }
    )


@router.post("/changes")
async def create_release_change(
    request: ReleaseChangeCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write_role(context)

    tenant_id = _tenant_id_from_context(context)
    normalized_change_type = _normalize_enum(request.change_type, allowed=CHANGE_TYPES, field_name="change_type")
    normalized_priority = _normalize_enum(request.priority, allowed=PRIORITIES, field_name="priority")
    normalized_source_type = request.source_type.strip().upper()
    actor = _actor(context)

    approver_role = (request.current_approver_role or "APPROVER").strip().upper()
    if approver_role not in APPROVER_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported current_approver_role")

    impact_scope = dict(request.impact_scope or {})
    if impact_scope.get("tenant_id") and int(impact_scope["tenant_id"]) != tenant_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="impact_scope.tenant_id mismatch")

    project_ids_raw = impact_scope.get("project_ids")
    if isinstance(project_ids_raw, list):
        validated_ids: list[int] = []
        for item in project_ids_raw:
            project_id = int(item)
            await _validate_project_in_tenant(db, project_id=project_id, tenant_id=tenant_id)
            validated_ids.append(project_id)
        impact_scope["project_ids"] = sorted(list(set(validated_ids)))

    before_payload = dict(request.before_payload or {})
    after_payload = dict(request.after_payload or {})
    diff_payload = dict(request.diff_payload or {}) or _compute_diff(before_payload, after_payload)
    release_plan_payload = dict(request.release_plan_payload or {})
    rollback_plan_payload = dict(request.rollback_plan_payload or {})

    risk_assessment_payload = _evaluate_risk(
        change_type=normalized_change_type,
        priority=normalized_priority,
        diff_payload=diff_payload,
        impact_scope=impact_scope,
        manual_review_note=request.manual_review_note,
    )

    release_change = await BaseRepository(ReleaseChangeRequest, db).create(
        {
            "tenant_id": tenant_id,
            "project_id": context.project.id,
            "change_type": normalized_change_type,
            "source_type": normalized_source_type,
            "source_id": request.source_id.strip(),
            "title": request.title.strip(),
            "description": request.description.strip() if request.description else None,
            "priority": normalized_priority,
            "status": "PENDING_APPROVAL",
            "impact_scope": impact_scope,
            "diff_payload": diff_payload,
            "before_payload": before_payload,
            "after_payload": after_payload,
            "risk_assessment_payload": risk_assessment_payload,
            "release_plan_payload": release_plan_payload,
            "rollback_plan_payload": rollback_plan_payload,
            "requested_by": actor,
            "current_approver_role": approver_role,
        }
    )

    await _write_history(
        db,
        change_id=release_change.id,
        project_id=context.project.id,
        action="CREATE",
        actor=actor,
        note=request.description,
        payload={
            "status": "PENDING_APPROVAL",
            "summary": "Change request created and submitted for approval",
        },
    )
    await _write_audit(
        db,
        context,
        "RELEASE_CHANGE_CREATE",
        release_change.id,
        {
            "summary": "Release change created",
            "title": release_change.title,
            "change_type": release_change.change_type,
            "priority": release_change.priority,
            "status": release_change.status,
        },
    )

    return success_response(
        _change_to_row(release_change),
        message="Release change created",
        code="RELEASE_CHANGE_CREATED",
    )


@router.post("/changes/{change_id}/actions")
async def operate_release_change(
    change_id: int,
    request: ReleaseChangeActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    action = _normalize_enum(request.action, allowed=ACTION_TYPES, field_name="action")
    if action in {"APPROVE", "REJECT", "REQUEST_REVISION", "SCHEDULE", "ROLLBACK"}:
        _require_approver_role(context)
    else:
        _require_write_role(context)

    result = await db.execute(
        select(ReleaseChangeRequest).where(
            ReleaseChangeRequest.id == change_id,
            ReleaseChangeRequest.project_id == context.project.id,
        )
    )
    change = result.scalar_one_or_none()
    if change is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Change request not found")

    now = datetime.now(timezone.utc)
    actor = _actor(context)
    note = request.note.strip() if request.note else None
    from_status = change.status

    def _ensure_status(allowed: set[str]) -> None:
        if change.status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Action {action} not allowed from status {change.status}",
            )

    if action == "EXECUTE":
        _ensure_status({"APPROVED", "SCHEDULED"})
        if change.status == "SCHEDULED" and change.scheduled_at and now < _as_utc(change.scheduled_at):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot execute before scheduled_at")

        started = await BaseRepository(ReleaseChangeRequest, db).update(
            change,
            {
                "status": "IN_PROGRESS",
                "executed_at": now,
            },
        )
        await _write_history(
            db,
            change_id=started.id,
            project_id=started.project_id,
            action="EXECUTE",
            actor=actor,
            note=note,
            payload={"from_status": from_status, "to_status": "IN_PROGRESS"},
        )
        await _write_audit(
            db,
            context,
            "RELEASE_CHANGE_EXECUTE",
            started.id,
            {
                "summary": "Release execution started",
                "from_status": from_status,
                "to_status": "IN_PROGRESS",
            },
        )

        if request.simulate_failure:
            failed = await BaseRepository(ReleaseChangeRequest, db).update(
                started,
                {
                    "status": "FAILED",
                },
            )
            reason = request.failure_reason.strip() if request.failure_reason else "Simulated execution failure"
            alert = await _open_release_alert(
                db,
                project_id=failed.project_id,
                change_id=failed.id,
                title=f"Release change failed: {failed.title}",
                description=reason,
            )
            await _write_history(
                db,
                change_id=failed.id,
                project_id=failed.project_id,
                action="EXECUTE_FAILED",
                actor=actor,
                note=note,
                payload={"reason": reason, "alert_id": alert.id, "to_status": "FAILED"},
            )
            await _write_audit(
                db,
                context,
                "RELEASE_CHANGE_EXECUTE_FAILED",
                failed.id,
                {
                    "summary": "Release execution failed",
                    "reason": reason,
                    "alert_id": alert.id,
                },
            )

            final_change = failed
            if request.trigger_rollback:
                final_change = await BaseRepository(ReleaseChangeRequest, db).update(
                    failed,
                    {
                        "status": "ROLLED_BACK",
                        "rolled_back_at": now,
                    },
                )
                await _write_history(
                    db,
                    change_id=final_change.id,
                    project_id=final_change.project_id,
                    action="ROLLBACK",
                    actor=actor,
                    note=note,
                    payload={
                        "mode": "AUTO",
                        "reason": reason,
                        "from_status": "FAILED",
                        "to_status": "ROLLED_BACK",
                    },
                )
                await _write_audit(
                    db,
                    context,
                    "RELEASE_CHANGE_ROLLBACK",
                    final_change.id,
                    {
                        "summary": "Release rolled back automatically",
                        "reason": reason,
                    },
                )

            return success_response(
                {
                    "change": _change_to_row(final_change),
                    "execution": {
                        "result": "FAILED",
                        "reason": reason,
                        "auto_rollback": bool(request.trigger_rollback),
                    },
                },
                message="Release execution finished",
                code="RELEASE_CHANGE_EXECUTED",
            )

        completed = await BaseRepository(ReleaseChangeRequest, db).update(
            started,
            {
                "status": "COMPLETED",
                "completed_at": now,
            },
        )
        await _resolve_release_alert(
            db,
            project_id=completed.project_id,
            change_id=completed.id,
            note="Release execution completed successfully",
        )
        await _write_history(
            db,
            change_id=completed.id,
            project_id=completed.project_id,
            action="EXECUTE_SUCCESS",
            actor=actor,
            note=note,
            payload={
                "from_status": "IN_PROGRESS",
                "to_status": "COMPLETED",
                "final_snapshot": completed.after_payload or {},
            },
        )
        await _write_audit(
            db,
            context,
            "RELEASE_CHANGE_EXECUTE_SUCCESS",
            completed.id,
            {
                "summary": "Release execution completed",
                "from_status": from_status,
                "to_status": "COMPLETED",
            },
        )
        return success_response(
            {
                "change": _change_to_row(completed),
                "execution": {"result": "SUCCESS"},
            },
            message="Release execution finished",
            code="RELEASE_CHANGE_EXECUTED",
        )

    patch: dict[str, Any] = {}
    payload: dict[str, Any] = {"from_status": from_status}
    audit_action = "RELEASE_CHANGE_UPDATE"

    if action == "APPROVE":
        _ensure_status({"PENDING_APPROVAL", "REVISION_REQUIRED"})
        patch.update(
            {
                "status": "APPROVED",
                "approved_by": actor,
                "approved_at": now,
                "rejected_by": None,
                "rejected_at": None,
            }
        )
        payload["to_status"] = "APPROVED"
        audit_action = "RELEASE_CHANGE_APPROVE"
    elif action == "REJECT":
        _ensure_status({"PENDING_APPROVAL", "REVISION_REQUIRED", "APPROVED", "SCHEDULED"})
        patch.update(
            {
                "status": "REJECTED",
                "rejected_by": actor,
                "rejected_at": now,
            }
        )
        payload["to_status"] = "REJECTED"
        audit_action = "RELEASE_CHANGE_REJECT"
    elif action == "REQUEST_REVISION":
        _ensure_status({"PENDING_APPROVAL", "APPROVED", "SCHEDULED"})
        patch.update(
            {
                "status": "REVISION_REQUIRED",
                "scheduled_at": None,
            }
        )
        payload["to_status"] = "REVISION_REQUIRED"
        audit_action = "RELEASE_CHANGE_REQUEST_REVISION"
    elif action == "SCHEDULE":
        _ensure_status({"APPROVED", "PENDING_APPROVAL"})
        scheduled_at = _parse_iso_datetime(request.scheduled_at, field_name="scheduled_at")
        if scheduled_at is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="scheduled_at is required")
        patch.update(
            {
                "status": "SCHEDULED",
                "scheduled_at": scheduled_at,
                "approved_by": change.approved_by or actor,
                "approved_at": change.approved_at or now,
            }
        )
        payload["to_status"] = "SCHEDULED"
        payload["scheduled_at"] = _to_iso(scheduled_at)
        audit_action = "RELEASE_CHANGE_SCHEDULE"
    elif action == "ROLLBACK":
        _ensure_status({"FAILED", "COMPLETED", "IN_PROGRESS"})
        patch.update(
            {
                "status": "ROLLED_BACK",
                "rolled_back_at": now,
            }
        )
        payload["to_status"] = "ROLLED_BACK"
        await _resolve_release_alert(
            db,
            project_id=change.project_id,
            change_id=change.id,
            note=note or "Release change rolled back",
        )
        audit_action = "RELEASE_CHANGE_ROLLBACK"
    else:
        _ensure_status({"PENDING_APPROVAL", "REVISION_REQUIRED", "APPROVED", "SCHEDULED"})
        patch.update({"status": "CANCELLED", "scheduled_at": None})
        payload["to_status"] = "CANCELLED"
        audit_action = "RELEASE_CHANGE_CANCEL"

    updated = await BaseRepository(ReleaseChangeRequest, db).update(change, patch)
    await _write_history(
        db,
        change_id=updated.id,
        project_id=updated.project_id,
        action=action,
        actor=actor,
        note=note,
        payload=payload,
    )
    await _write_audit(
        db,
        context,
        audit_action,
        updated.id,
        {
            "summary": f"Release change {action.lower()}",
            "from_status": from_status,
            "to_status": updated.status,
            "note": note,
        },
    )

    return success_response(
        _change_to_row(updated),
        message="Release change updated",
        code="RELEASE_CHANGE_UPDATED",
    )
