import csv
import io
import json
import re
from datetime import date, datetime, time, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

FAILURE_ACTION_TOKENS = ("FAIL", "ERROR", "REJECT", "DENY")
DETAILS_MAX_LEN = 4000
MAX_SCAN_ROWS = 5000


class AuditLogExportRequest(BaseModel):
    format: str = Field(default="csv", min_length=3, max_length=8)
    q: str | None = None
    action: str | None = None
    entity_type: str | None = None
    trace_id: str | None = None
    user: str | None = None
    status: str | None = None
    date_from: str | None = None
    date_to: str | None = None


def _infer_status(action: str) -> str:
    upper_action = action.upper()
    if any(token in upper_action for token in FAILURE_ACTION_TOKENS):
        return "FAILURE"
    return "SUCCESS"


def _parse_datetime(value: str, *, end_of_day: bool) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("datetime value is empty")
    normalized = raw.replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(raw)
            parsed = datetime.combine(
                parsed_date,
                time.max if end_of_day else time.min,
            )
        except ValueError as exc:
            raise ValueError(f"Invalid datetime format: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _parse_details(raw_details: str | None) -> dict[str, Any]:
    if not raw_details:
        return {}
    try:
        parsed = json.loads(raw_details)
        if isinstance(parsed, dict):
            return parsed
        return {"value": parsed}
    except json.JSONDecodeError:
        return {"raw": raw_details}


def _extract_project_id(actor_id: str | None) -> int | None:
    if not actor_id:
        return None
    match = re.search(r"(?:project:|project_)(\d+)", actor_id)
    if not match:
        return None
    return int(match.group(1))


def _extract_context(log: AuditLog, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "tenant_id": details.get("tenant_id"),
        "project_id": details.get("project_id") or _extract_project_id(log.user_id),
        "ip_address": details.get("ip_address") or details.get("ip") or details.get("client_ip"),
        "actor_raw": log.user_id,
    }


def _extract_trace_id(details: dict[str, Any]) -> str | None:
    for key in ("trace_id", "traceId", "trace"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _extract_changed_fields(details: dict[str, Any]) -> list[str]:
    diff = details.get("diff")
    if not isinstance(diff, dict):
        return []
    return sorted(str(key) for key in diff.keys())


def _details_summary(details: dict[str, Any]) -> str:
    if not details:
        return "-"
    changed_fields = _extract_changed_fields(details)
    if changed_fields:
        return f"Changed fields: {', '.join(changed_fields[:6])}"
    for key in ("reason", "error_message", "message", "title", "name"):
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:200]
    keys = sorted(details.keys())
    return f"Details keys: {', '.join(keys[:6])}"


def _entity_link(entity_type: str, entity_id: str) -> dict[str, str | None]:
    route_map = {
        "TRACKING_EVENT": "/events",
        "EVENT": "/events",
        "DATA_ASSET": "/catalog",
        "DATA_QUALITY_RULE": "/data-quality",
        "PIPELINE": "/pipelines",
        "SCHEDULER_DAG": "/scheduler",
        "SCHEDULER_RUN": "/scheduler",
        "GOVERNANCE_CHECK": "/governance",
        "EXPLORE_QUERY": "/explore",
        "INFRASTRUCTURE": "/infrastructure",
    }
    module_route = route_map.get(entity_type)
    return {
        "module_route": module_route,
        "entity_type": entity_type,
        "entity_id": entity_id,
    }


def _to_list_item(log: AuditLog) -> dict[str, Any]:
    details = _parse_details(log.details)
    context = _extract_context(log, details)
    changed_fields = _extract_changed_fields(details)
    return {
        "id": log.id,
        "user": parse_actor(log.user_id),
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "target": f"{log.entity_type}:{log.entity_id}",
        "timestamp": log.timestamp.isoformat(),
        "status": _infer_status(log.action),
        "context": context,
        "trace_id": _extract_trace_id(details),
        "details_summary": _details_summary(details),
        "has_diff": bool(changed_fields),
        "changed_fields": changed_fields,
    }


def _to_detail_item(log: AuditLog) -> dict[str, Any]:
    details = _parse_details(log.details)
    context = _extract_context(log, details)
    diff = details.get("diff") if isinstance(details.get("diff"), dict) else {}

    key_fields: dict[str, Any] = {}
    for key, value in details.items():
        if key == "diff":
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            key_fields[key] = value

    return {
        "id": log.id,
        "user": parse_actor(log.user_id),
        "action": log.action,
        "entity_type": log.entity_type,
        "entity_id": log.entity_id,
        "target": f"{log.entity_type}:{log.entity_id}",
        "timestamp": log.timestamp.isoformat(),
        "status": _infer_status(log.action),
        "context": context,
        "trace_id": _extract_trace_id(details),
        "details_summary": _details_summary(details),
        "operation": {
            "key_fields": key_fields,
            "details": details,
        },
        "diff": diff,
        "navigation": _entity_link(log.entity_type, log.entity_id),
    }


async def _load_filtered_rows(
    *,
    context: RequestContext,
    db: AsyncSession,
    q: str | None,
    action: str | None,
    entity_type: str | None,
    trace_id: str | None,
    user: str | None,
    status_filter: str | None,
    date_from: str | None,
    date_to: str | None,
    max_scan: int,
) -> list[AuditLog]:
    query = (
        select(AuditLog)
        .where(build_project_audit_filter(context.project.id))
        .order_by(AuditLog.timestamp.desc())
    )
    if action:
        query = query.where(AuditLog.action == action.strip())
    if entity_type:
        query = query.where(AuditLog.entity_type == entity_type.strip())
    if trace_id:
        trace_like = f'%{trace_id.strip()}%'
        query = query.where(AuditLog.details.ilike(trace_like))
    if user:
        user_like = f"%{user.strip()}%"
        query = query.where(AuditLog.user_id.ilike(user_like))
    if q:
        q_like = f"%{q.strip()}%"
        query = query.where(
            or_(
                AuditLog.action.ilike(q_like),
                AuditLog.entity_type.ilike(q_like),
                AuditLog.entity_id.ilike(q_like),
                AuditLog.user_id.ilike(q_like),
                AuditLog.details.ilike(q_like),
            )
        )
    if date_from:
        parsed_from = _parse_datetime(date_from, end_of_day=False)
        query = query.where(AuditLog.timestamp >= parsed_from)
    if date_to:
        parsed_to = _parse_datetime(date_to, end_of_day=True)
        query = query.where(AuditLog.timestamp <= parsed_to)

    result = await db.execute(query.limit(max_scan))
    rows = list(result.scalars().all())

    if status_filter:
        normalized = status_filter.strip().upper()
        if normalized not in {"SUCCESS", "FAILURE"}:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="status must be SUCCESS or FAILURE")
        rows = [row for row in rows if _infer_status(row.action) == normalized]
    return rows


@router.get("/logs")
async def list_audit_logs(
    q: str | None = Query(default=None),
    action: str | None = Query(default=None),
    entity_type: str | None = Query(default=None),
    trace_id: str | None = Query(default=None),
    user: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0, le=5000),
    include_meta: bool = Query(default=False),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    rows = await _load_filtered_rows(
        context=context,
        db=db,
        q=q,
        action=action,
        entity_type=entity_type,
        trace_id=trace_id,
        user=user,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        max_scan=MAX_SCAN_ROWS,
    )
    total = len(rows)
    page_rows = rows[offset : offset + limit]
    items = [_to_list_item(row) for row in page_rows]

    if not include_meta:
        return success_response(items)

    facets = {
        "actions": sorted({row.action for row in rows}),
        "entity_types": sorted({row.entity_type for row in rows}),
        "users": sorted({parse_actor(row.user_id) for row in rows if row.user_id}),
        "trace_ids": sorted(
            {
                trace
                for row in rows
                for trace in [_extract_trace_id(_parse_details(row.details))]
                if trace
            }
        ),
    }
    return success_response(
        {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": facets,
        }
    )


@router.get("/logs/{log_id}")
async def get_audit_log_detail(
    log_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(AuditLog).where(
        AuditLog.id == log_id,
        build_project_audit_filter(context.project.id),
    )
    result = await db.execute(query)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit log not found")
    return success_response(_to_detail_item(row))


@router.post("/logs/export")
async def export_audit_logs(
    request: AuditLogExportRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    export_format = request.format.strip().lower()
    if export_format not in {"csv", "json"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be csv or json")

    rows = await _load_filtered_rows(
        context=context,
        db=db,
        q=request.q,
        action=request.action,
        entity_type=request.entity_type,
        trace_id=request.trace_id,
        user=request.user,
        status_filter=request.status,
        date_from=request.date_from,
        date_to=request.date_to,
        max_scan=MAX_SCAN_ROWS,
    )

    if export_format == "json":
        payload = [_to_detail_item(row) for row in rows]
        content = json.dumps(payload, ensure_ascii=False, indent=2)
        mime_type = "application/json"
        filename = f"audit_logs_project_{context.project.id}.json"
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            [
                "id",
                "timestamp",
                "user",
                "action",
                "entity_type",
                "entity_id",
                "trace_id",
                "status",
                "project_id",
                "tenant_id",
                "ip_address",
                "details_summary",
                "changed_fields",
                "details",
            ]
        )
        for row in rows:
            detail = _to_detail_item(row)
            context_data = detail["context"]
            details_json = json.dumps(detail["operation"]["details"], ensure_ascii=False)
            writer.writerow(
                [
                    detail["id"],
                    detail["timestamp"],
                    detail["user"],
                    detail["action"],
                    detail["entity_type"],
                    detail["entity_id"],
                    detail["trace_id"],
                    detail["status"],
                    context_data.get("project_id"),
                    context_data.get("tenant_id"),
                    context_data.get("ip_address"),
                    detail["details_summary"],
                    ",".join(detail["diff"].keys()),
                    details_json,
                ]
            )
        content = buffer.getvalue()
        mime_type = "text/csv"
        filename = f"audit_logs_project_{context.project.id}.csv"

    audit_details = json.dumps(
        {
            "format": export_format,
            "row_count": len(rows),
            "action_filter": request.action,
            "entity_type_filter": request.entity_type,
            "trace_id_filter": request.trace_id,
            "status_filter": request.status,
        },
        ensure_ascii=True,
    )[:DETAILS_MAX_LEN]
    await BaseRepository(AuditLog, db).create(
        {
            "action": "AUDIT_LOG_EXPORT",
            "entity_type": "AUDIT_LOG",
            "entity_id": str(context.project.id),
            "user_id": context.actor_id,
            "details": audit_details,
        }
    )

    return success_response(
        {
            "format": export_format,
            "filename": filename,
            "mime_type": mime_type,
            "row_count": len(rows),
            "content": content,
        }
    )
