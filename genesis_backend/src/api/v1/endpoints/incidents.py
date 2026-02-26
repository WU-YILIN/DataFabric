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
from src.infrastructure.database.models.incident_case import IncidentCase
from src.infrastructure.database.models.incident_timeline_entry import IncidentTimelineEntry
from src.infrastructure.database.models.knowledge_document import KnowledgeDocument
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

SEVERITY_SET = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
STATUS_SET = {"OPEN", "TRIAGED", "INVESTIGATING", "MITIGATED", "RESOLVED", "CLOSED"}
SOURCE_TYPES = {"ALERT", "PIPELINE", "DQ_RULE", "EVENT", "RELEASE_CHANGE", "REPORT", "OTHER"}
ACTIONS = {
    "TRIAGE",
    "ASSIGN",
    "START_INVESTIGATION",
    "ADD_NOTE",
    "MITIGATE",
    "RESOLVE",
    "CLOSE",
    "REOPEN",
    "LINK_RUNBOOK",
}
WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR", "APPROVER"}


class IncidentCreateRequest(BaseModel):
    source_type: str = Field(..., min_length=2, max_length=64)
    source_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=2, max_length=255)
    summary: str | None = Field(default=None, max_length=1000)
    severity: str = Field(default="MEDIUM", max_length=32)
    assignee: str | None = Field(default=None, max_length=255)
    runbook_doc_id: int | None = Field(default=None, ge=1)
    context_payload: dict[str, Any] = Field(default_factory=dict)
    impact_payload: dict[str, Any] = Field(default_factory=dict)
    resolution_payload: dict[str, Any] = Field(default_factory=dict)
    note: str | None = Field(default=None, max_length=1000)


class IncidentUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=255)
    summary: str | None = Field(default=None, max_length=1000)
    severity: str | None = Field(default=None, max_length=32)
    assignee: str | None = Field(default=None, max_length=255)
    runbook_doc_id: int | None = Field(default=None, ge=1)
    context_payload: dict[str, Any] | None = None
    impact_payload: dict[str, Any] | None = None
    resolution_payload: dict[str, Any] | None = None
    note: str | None = Field(default=None, max_length=1000)


class IncidentActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
    assignee: str | None = Field(default=None, max_length=255)
    runbook_doc_id: int | None = Field(default=None, ge=1)
    resolution_payload: dict[str, Any] = Field(default_factory=dict)
    impact_payload: dict[str, Any] = Field(default_factory=dict)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _normalize_enum(value: str, *, allowed: set[str], field_name: str) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported {field_name}: {value}")
    return normalized


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Incidents API requires bearer user context")


def _require_write(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in WRITE_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (WRITE_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for incident mutation")


def _tenant_id(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


def _actor(context: RequestContext) -> str:
    return context.user.email if context.user else parse_actor(context.actor_id)


async def _validate_runbook(db: AsyncSession, *, project_id: int, runbook_doc_id: int | None) -> KnowledgeDocument | None:
    if runbook_doc_id is None:
        return None
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == runbook_doc_id,
            KnowledgeDocument.project_id == project_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Runbook document not found")
    return row


async def _resolve_source_context(
    db: AsyncSession,
    *,
    project_id: int,
    source_type: str,
    source_id: str,
) -> dict[str, Any]:
    context_payload: dict[str, Any] = {}
    if source_type == "ALERT":
        try:
            alert_id = int(source_id)
        except Exception:
            return {"source_type": source_type, "source_id": source_id}
        result = await db.execute(
            select(Alert).where(
                Alert.id == alert_id,
                Alert.project_id == project_id,
            )
        )
        alert = result.scalar_one_or_none()
        if alert:
            context_payload = {
                "alert": {
                    "id": alert.id,
                    "severity": alert.severity,
                    "status": alert.status,
                    "title": alert.title,
                    "description": alert.description,
                    "source_type": alert.source_type,
                    "source_id": alert.source_id,
                }
            }
    return {"source_type": source_type, "source_id": source_id, **context_payload}


def _incident_to_row(context: RequestContext, row: IncidentCase) -> dict[str, Any]:
    roles = set()
    if context.project_role:
        roles.add(context.project_role.upper())
    if context.tenant_role:
        roles.add(context.tenant_role.upper())
    actor = _actor(context)
    can_edit = actor == row.owner or bool(roles & {"OWNER", "ADMIN", "APPROVER", "EDITOR"})
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "project_id": row.project_id,
        "runbook_doc_id": row.runbook_doc_id,
        "source_type": row.source_type,
        "source_id": row.source_id,
        "title": row.title,
        "summary": row.summary,
        "severity": row.severity,
        "status": row.status,
        "owner": row.owner,
        "assignee": row.assignee,
        "context_payload": row.context_payload or {},
        "impact_payload": row.impact_payload or {},
        "resolution_payload": row.resolution_payload or {},
        "started_at": _to_iso(row.started_at),
        "mitigated_at": _to_iso(row.mitigated_at),
        "resolved_at": _to_iso(row.resolved_at),
        "closed_at": _to_iso(row.closed_at),
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "capabilities": {"can_edit": can_edit},
    }


def _timeline_to_row(row: IncidentTimelineEntry) -> dict[str, Any]:
    return {
        "id": row.id,
        "incident_id": row.incident_id,
        "action": row.action,
        "actor": row.actor,
        "note": row.note,
        "payload": row.payload or {},
        "created_at": _to_iso(row.created_at),
    }


async def _write_timeline(
    db: AsyncSession,
    *,
    incident_id: int,
    project_id: int,
    action: str,
    actor: str,
    note: str | None,
    payload: dict[str, Any],
) -> None:
    await BaseRepository(IncidentTimelineEntry, db).create(
        {
            "incident_id": incident_id,
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
    incident_id: int | str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "INCIDENT_CASE",
            "entity_id": str(incident_id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


@router.get("/overview")
async def get_incident_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    rows = list((await db.execute(select(IncidentCase).where(IncidentCase.project_id == context.project.id))).scalars().all())
    status_counter = Counter(item.status for item in rows)
    severity_counter = Counter(item.severity for item in rows)

    mttr_minutes = 0.0
    resolved_rows = [item for item in rows if item.started_at and item.resolved_at]
    if resolved_rows:
        total_seconds = 0.0
        for item in resolved_rows:
            start = item.started_at.astimezone(timezone.utc) if item.started_at.tzinfo else item.started_at.replace(tzinfo=timezone.utc)
            end = item.resolved_at.astimezone(timezone.utc) if item.resolved_at.tzinfo else item.resolved_at.replace(tzinfo=timezone.utc)
            total_seconds += max(0.0, (end - start).total_seconds())
        mttr_minutes = round(total_seconds / len(resolved_rows) / 60.0, 2)

    recent = list(
        (
            await db.execute(
                select(AuditLog)
                .where(and_(AuditLog.entity_type == "INCIDENT_CASE", build_project_audit_filter(context.project.id)))
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(20)
            )
        ).scalars().all()
    )
    recent_activity = []
    for row in recent:
        details = _safe_json_loads(row.details)
        recent_activity.append(
            {
                "id": row.id,
                "timestamp": _to_iso(row.timestamp),
                "actor": parse_actor(row.user_id),
                "action": row.action,
                "incident_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_incidents": len(rows),
                "open_incidents": status_counter.get("OPEN", 0),
                "investigating_incidents": status_counter.get("INVESTIGATING", 0),
                "mitigated_incidents": status_counter.get("MITIGATED", 0),
                "resolved_incidents": status_counter.get("RESOLVED", 0),
                "closed_incidents": status_counter.get("CLOSED", 0),
                "mttr_minutes": mttr_minutes,
            },
            "status_distribution": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            "severity_distribution": [{"severity": key, "count": severity_counter[key]} for key in sorted(severity_counter.keys())],
            "recent_activity": recent_activity,
        }
    )


@router.get("/cases")
async def list_incident_cases(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    assignee: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_status = _normalize_enum(status_filter, allowed=STATUS_SET, field_name="status") if status_filter else None
    normalized_severity = _normalize_enum(severity, allowed=SEVERITY_SET, field_name="severity") if severity else None
    normalized_source = _normalize_enum(source_type, allowed=SOURCE_TYPES, field_name="source_type") if source_type else None
    owner_filter = owner.strip().lower() if owner else None
    assignee_filter = assignee.strip().lower() if assignee else None

    rows = list(
        (
            await db.execute(
                select(IncidentCase)
                .where(IncidentCase.project_id == context.project.id)
                .order_by(IncidentCase.updated_at.desc(), IncidentCase.id.desc())
            )
        ).scalars().all()
    )
    if normalized_status:
        rows = [item for item in rows if item.status == normalized_status]
    if normalized_severity:
        rows = [item for item in rows if item.severity == normalized_severity]
    if normalized_source:
        rows = [item for item in rows if item.source_type == normalized_source]
    if owner_filter:
        rows = [item for item in rows if owner_filter in item.owner.lower()]
    if assignee_filter:
        rows = [item for item in rows if item.assignee and assignee_filter in item.assignee.lower()]
    if q and q.strip():
        keyword = q.strip().lower()
        filtered = []
        for item in rows:
            text = " ".join(
                [
                    item.title,
                    item.summary or "",
                    item.source_type,
                    item.source_id,
                    item.owner,
                    item.assignee or "",
                ]
            ).lower()
            if keyword in text:
                filtered.append(item)
        rows = filtered

    total = len(rows)
    page_rows = rows[offset : offset + limit]
    status_counter = Counter(item.status for item in rows)
    severity_counter = Counter(item.severity for item in rows)
    owner_counter = Counter(item.owner for item in rows)
    source_counter = Counter(item.source_type for item in rows)

    return success_response(
        {
            "items": [_incident_to_row(context, item) for item in page_rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
                "severities": [{"severity": key, "count": severity_counter[key]} for key in sorted(severity_counter.keys())],
                "owners": [{"owner": key, "count": owner_counter[key]} for key in sorted(owner_counter.keys())],
                "source_types": [{"source_type": key, "count": source_counter[key]} for key in sorted(source_counter.keys())],
            },
        }
    )


@router.get("/cases/{case_id}")
async def get_incident_case_detail(
    case_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(IncidentCase).where(IncidentCase.id == case_id, IncidentCase.project_id == context.project.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident case not found")

    timeline = list(
        (
            await db.execute(
                select(IncidentTimelineEntry)
                .where(IncidentTimelineEntry.incident_id == item.id, IncidentTimelineEntry.project_id == item.project_id)
                .order_by(IncidentTimelineEntry.created_at.desc(), IncidentTimelineEntry.id.desc())
            )
        ).scalars().all()
    )
    return success_response({"case": _incident_to_row(context, item), "timeline": [_timeline_to_row(row) for row in timeline]})


@router.post("/cases")
async def create_incident_case(
    request: IncidentCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write(context)
    source_type = _normalize_enum(request.source_type, allowed=SOURCE_TYPES, field_name="source_type")
    severity = _normalize_enum(request.severity, allowed=SEVERITY_SET, field_name="severity")
    await _validate_runbook(db, project_id=context.project.id, runbook_doc_id=request.runbook_doc_id)
    actor = _actor(context)

    source_context = await _resolve_source_context(
        db,
        project_id=context.project.id,
        source_type=source_type,
        source_id=request.source_id.strip(),
    )
    merged_context = dict(source_context)
    merged_context.update(request.context_payload or {})

    item = await BaseRepository(IncidentCase, db).create(
        {
            "tenant_id": _tenant_id(context),
            "project_id": context.project.id,
            "runbook_doc_id": request.runbook_doc_id,
            "source_type": source_type,
            "source_id": request.source_id.strip(),
            "title": request.title.strip(),
            "summary": request.summary.strip() if request.summary else None,
            "severity": severity,
            "status": "OPEN",
            "owner": actor,
            "assignee": request.assignee.strip() if request.assignee else None,
            "context_payload": merged_context,
            "impact_payload": request.impact_payload or {},
            "resolution_payload": request.resolution_payload or {},
            "created_by": actor,
            "updated_by": actor,
        }
    )
    await _write_timeline(
        db,
        incident_id=item.id,
        project_id=item.project_id,
        action="CREATE",
        actor=actor,
        note=request.note,
        payload={"status": "OPEN"},
    )
    await _write_audit(
        db,
        context,
        "INCIDENT_CREATE",
        item.id,
        {"summary": "Incident case created", "title": item.title, "severity": item.severity, "status": item.status},
    )
    return success_response(_incident_to_row(context, item), message="Incident case created", code="INCIDENT_CREATED")


@router.patch("/cases/{case_id}")
async def update_incident_case(
    case_id: int,
    request: IncidentUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write(context)
    result = await db.execute(
        select(IncidentCase).where(IncidentCase.id == case_id, IncidentCase.project_id == context.project.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident case not found")
    if not _incident_to_row(context, item)["capabilities"]["can_edit"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to edit incident")

    patch = request.model_dump(exclude_none=True)
    if not patch:
        return success_response(_incident_to_row(context, item), message="No changes", code="INCIDENT_NO_CHANGES")

    if "severity" in patch:
        patch["severity"] = _normalize_enum(patch["severity"], allowed=SEVERITY_SET, field_name="severity")
    if "runbook_doc_id" in patch:
        await _validate_runbook(db, project_id=context.project.id, runbook_doc_id=patch["runbook_doc_id"])
    if "title" in patch:
        patch["title"] = str(patch["title"]).strip()
    if "summary" in patch and patch["summary"] is not None:
        patch["summary"] = str(patch["summary"]).strip()
    if "assignee" in patch and patch["assignee"] is not None:
        patch["assignee"] = str(patch["assignee"]).strip()

    actor = _actor(context)
    patch["updated_by"] = actor
    updated = await BaseRepository(IncidentCase, db).update(item, patch)
    await _write_timeline(
        db,
        incident_id=updated.id,
        project_id=updated.project_id,
        action="UPDATE",
        actor=actor,
        note=request.note,
        payload={"patched_fields": sorted(list(patch.keys()))},
    )
    await _write_audit(
        db,
        context,
        "INCIDENT_UPDATE",
        updated.id,
        {"summary": "Incident case updated", "patched_fields": sorted(list(patch.keys()))},
    )
    return success_response(_incident_to_row(context, updated), message="Incident case updated", code="INCIDENT_UPDATED")


@router.post("/cases/{case_id}/actions")
async def operate_incident_case(
    case_id: int,
    request: IncidentActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write(context)
    action = _normalize_enum(request.action, allowed=ACTIONS, field_name="action")

    result = await db.execute(
        select(IncidentCase).where(IncidentCase.id == case_id, IncidentCase.project_id == context.project.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident case not found")
    if not _incident_to_row(context, item)["capabilities"]["can_edit"]:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to operate incident")

    actor = _actor(context)
    note = request.note.strip() if request.note else None
    now = datetime.now(timezone.utc)
    from_status = item.status
    patch: dict[str, Any] = {"updated_by": actor}
    timeline_payload: dict[str, Any] = {"from_status": from_status}
    audit_action = "INCIDENT_ACTION"

    def _ensure_allowed(allowed: set[str]) -> None:
        if item.status not in allowed:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Action {action} not allowed from status {item.status}")

    if action == "TRIAGE":
        _ensure_allowed({"OPEN"})
        patch["status"] = "TRIAGED"
        patch["started_at"] = item.started_at or now
        audit_action = "INCIDENT_TRIAGE"
    elif action == "ASSIGN":
        assignee = request.assignee.strip() if request.assignee else None
        if not assignee:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignee is required")
        patch["assignee"] = assignee
        audit_action = "INCIDENT_ASSIGN"
    elif action == "START_INVESTIGATION":
        _ensure_allowed({"OPEN", "TRIAGED"})
        patch["status"] = "INVESTIGATING"
        patch["started_at"] = item.started_at or now
        audit_action = "INCIDENT_START_INVESTIGATION"
    elif action == "ADD_NOTE":
        audit_action = "INCIDENT_ADD_NOTE"
    elif action == "MITIGATE":
        _ensure_allowed({"OPEN", "TRIAGED", "INVESTIGATING"})
        patch["status"] = "MITIGATED"
        patch["mitigated_at"] = now
        if request.impact_payload:
            patch["impact_payload"] = request.impact_payload
        audit_action = "INCIDENT_MITIGATE"
    elif action == "RESOLVE":
        _ensure_allowed({"OPEN", "TRIAGED", "INVESTIGATING", "MITIGATED"})
        patch["status"] = "RESOLVED"
        patch["resolved_at"] = now
        if request.resolution_payload:
            patch["resolution_payload"] = request.resolution_payload
        audit_action = "INCIDENT_RESOLVE"
    elif action == "CLOSE":
        _ensure_allowed({"RESOLVED", "MITIGATED"})
        patch["status"] = "CLOSED"
        patch["closed_at"] = now
        audit_action = "INCIDENT_CLOSE"
    elif action == "REOPEN":
        _ensure_allowed({"MITIGATED", "RESOLVED", "CLOSED"})
        patch["status"] = "OPEN"
        patch["closed_at"] = None
        audit_action = "INCIDENT_REOPEN"
    else:
        await _validate_runbook(db, project_id=context.project.id, runbook_doc_id=request.runbook_doc_id)
        if request.runbook_doc_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="runbook_doc_id is required")
        patch["runbook_doc_id"] = request.runbook_doc_id
        audit_action = "INCIDENT_LINK_RUNBOOK"

    if "status" in patch:
        timeline_payload["to_status"] = patch["status"]
    if "assignee" in patch:
        timeline_payload["assignee"] = patch["assignee"]
    if "runbook_doc_id" in patch:
        timeline_payload["runbook_doc_id"] = patch["runbook_doc_id"]
    if request.impact_payload:
        timeline_payload["impact_payload"] = request.impact_payload
    if request.resolution_payload:
        timeline_payload["resolution_payload"] = request.resolution_payload

    updated = await BaseRepository(IncidentCase, db).update(item, patch)
    await _write_timeline(
        db,
        incident_id=updated.id,
        project_id=updated.project_id,
        action=action,
        actor=actor,
        note=note,
        payload=timeline_payload,
    )
    await _write_audit(
        db,
        context,
        audit_action,
        updated.id,
        {"summary": f"Incident action {action}", "from_status": from_status, "to_status": updated.status, "note": note},
    )
    return success_response(_incident_to_row(context, updated), message="Incident action applied", code="INCIDENT_ACTION_APPLIED")

