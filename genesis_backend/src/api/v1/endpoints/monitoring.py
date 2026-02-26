from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import parse_actor
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.alert_action_history import AlertActionHistory
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_quality_execution_log import DataQualityExecutionLog
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.scheduler_run import SchedulerRun
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

SOURCE_MODULE_MAP = {
    "PIPELINE": "PIPELINES",
    "DATA_QUALITY_RULE": "DQ",
    "SCHEDULER_DAG": "SCHEDULER",
    "INFRASTRUCTURE": "INFRA",
    "LLM": "LLM",
    "GOVERNANCE": "LLM",
}
AVAILABLE_MODULES = ["PIPELINES", "DQ", "INFRA", "SCHEDULER", "LLM", "OTHER"]
SEVERITY_LEVEL = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


class AlertActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=32)
    note: str | None = Field(default=None, max_length=1000)
    assignee: str | None = Field(default=None, max_length=255)


def _module_from_source_type(source_type: str) -> str:
    return SOURCE_MODULE_MAP.get(source_type.upper(), "OTHER")


def _normalize_modules(raw: str | None) -> list[str]:
    if not raw:
        return []
    modules: list[str] = []
    for token in raw.split(","):
        value = token.strip().upper()
        if value in AVAILABLE_MODULES and value not in modules:
            modules.append(value)
    return modules


def _to_iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _alert_links(alert: Alert) -> dict[str, Any]:
    module = _module_from_source_type(alert.source_type)
    module_route_map = {
        "PIPELINES": "/pipelines",
        "DQ": "/data-quality",
        "SCHEDULER": "/scheduler",
        "INFRA": "/infrastructure",
        "LLM": "/governance",
        "OTHER": "/logs",
    }
    detail_route = module_route_map.get(module, "/logs")
    return {
        "module": module,
        "module_route": detail_route,
        "entity": {
            "source_type": alert.source_type,
            "source_id": alert.source_id,
        },
        "explore_prefill": (
            f"/explore?source_type={alert.source_type}&source_id={alert.source_id}"
            if alert.source_type in {"PIPELINE", "DATA_QUALITY_RULE", "SCHEDULER_DAG"}
            else None
        ),
    }


def _alert_to_row(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "source_type": alert.source_type,
        "source_id": alert.source_id,
        "source_module": _module_from_source_type(alert.source_type),
        "severity": alert.severity,
        "title": alert.title,
        "description": alert.description,
        "status": alert.status,
        "claimed_by": alert.claimed_by,
        "claimed_at": _to_iso(alert.claimed_at),
        "resolved_at": _to_iso(alert.resolved_at),
        "last_note": alert.last_note,
        "created_at": _to_iso(alert.created_at),
        "updated_at": _to_iso(alert.updated_at),
        "links": _alert_links(alert),
    }


def _history_to_row(item: AlertActionHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "action": item.action,
        "actor": parse_actor(item.actor_id),
        "actor_id": item.actor_id,
        "note": item.note,
        "payload": item.payload,
        "created_at": _to_iso(item.created_at),
    }


def _actor_email(context: RequestContext) -> str:
    if context.user:
        return context.user.email
    return parse_actor(context.actor_id)


def _check_write_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alert operation requires bearer user context",
        )


def _alert_status_rank(status: str) -> int:
    order = {"OPEN": 3, "ACKNOWLEDGED": 2, "RESOLVED": 1}
    return order.get(status.upper(), 0)


def _severity_rank(severity: str) -> int:
    return SEVERITY_LEVEL.get(severity.upper(), 0)


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    alert: Alert,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "ALERT",
            "entity_id": str(alert.id),
            "user_id": context.actor_id,
            "details": str(details),
        }
    )


@router.get("/overview")
async def get_monitoring_overview(
    modules: str | None = Query(default=None),
    window_minutes: int = Query(default=120, ge=30, le=1440),
    bucket_count: int = Query(default=12, ge=6, le=60),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    selected_modules = _normalize_modules(modules)
    now = datetime.now(timezone.utc)
    start_time = now - timedelta(minutes=window_minutes)
    bucket_seconds = max(60, int((window_minutes * 60) / bucket_count))

    alerts_result = await db.execute(
        select(Alert).where(
            Alert.project_id == context.project.id,
            Alert.created_at >= start_time,
        )
    )
    alerts = list(alerts_result.scalars().all())
    if selected_modules:
        alerts = [item for item in alerts if _module_from_source_type(item.source_type) in selected_modules]

    open_alerts = [item for item in alerts if item.status in {"OPEN", "ACKNOWLEDGED"}]
    critical_alerts = [item for item in open_alerts if item.severity.upper() == "CRITICAL"]
    acknowledged_alerts = [item for item in open_alerts if item.status == "ACKNOWLEDGED"]
    resolved_24h = [item for item in alerts if item.status == "RESOLVED"]

    audit_result = await db.execute(
        select(AuditLog).where(
            or_(
                AuditLog.user_id == f"project:{context.project.id}",
                AuditLog.user_id == f"project_{context.project.id}",
                AuditLog.user_id.like(f"%|project:{context.project.id}"),
            ),
            AuditLog.timestamp >= start_time,
        )
    )
    audit_rows = list(audit_result.scalars().all())
    audit_with_time = [(row, _as_utc(row.timestamp)) for row in audit_rows]
    alert_with_time = [(row, _as_utc(row.created_at)) for row in alerts]

    bucket_rows = []
    for index in range(bucket_count):
        bucket_start = start_time + timedelta(seconds=index * bucket_seconds)
        bucket_end = bucket_start + timedelta(seconds=bucket_seconds)
        bucket_audits = [
            row
            for row, ts in audit_with_time
            if ts and bucket_start <= ts < bucket_end
        ]
        bucket_alerts = [
            row
            for row, ts in alert_with_time
            if ts and bucket_start <= ts < bucket_end
        ]
        failure_actions = [
            row
            for row in bucket_audits
            if "FAIL" in row.action or "ERROR" in row.action or "REJECT" in row.action
        ]
        qps = round(len(bucket_audits) / bucket_seconds, 4)
        failure_rate = round((len(failure_actions) / len(bucket_audits)) if bucket_audits else 0.0, 4)
        # synthetic latency driven by error pressure + alert count for stable demo behavior
        latency_ms = round(80 + failure_rate * 450 + len(bucket_alerts) * 7, 2)
        bucket_rows.append(
            {
                "timestamp": bucket_end.isoformat(),
                "qps": qps,
                "latency_ms": latency_ms,
                "failure_rate": failure_rate,
                "alert_count": len(bucket_alerts),
            }
        )

    module_group: dict[str, list[Alert]] = {name: [] for name in AVAILABLE_MODULES}
    for alert in open_alerts:
        module_group[_module_from_source_type(alert.source_type)].append(alert)

    module_health = []
    for module in AVAILABLE_MODULES:
        if selected_modules and module not in selected_modules:
            continue
        rows = module_group[module]
        critical_count = len([row for row in rows if row.severity.upper() == "CRITICAL"])
        high_count = len([row for row in rows if row.severity.upper() == "HIGH"])
        score = max(0, 100 - critical_count * 30 - high_count * 12 - max(0, len(rows) - critical_count - high_count) * 4)
        if critical_count > 0:
            health_status = "RED"
        elif high_count > 0 or len(rows) > 3:
            health_status = "YELLOW"
        else:
            health_status = "GREEN"
        last_alert_at = max((_as_utc(row.created_at) for row in rows), default=None)
        module_health.append(
            {
                "module": module,
                "status": health_status,
                "score": score,
                "open_alerts": len(rows),
                "critical_alerts": critical_count,
                "last_alert_at": _to_iso(last_alert_at),
            }
        )

    pipeline_result = await db.execute(
        select(
            func.count(Pipeline.id),
            func.sum(case((Pipeline.status == "RUNNING", 1), else_=0)),
            func.sum(case((Pipeline.status.in_(["FAILED", "ROLLING_BACK"]), 1), else_=0)),
        ).where(Pipeline.project_id == context.project.id)
    )
    total_pipelines, running_pipelines, failed_pipelines = pipeline_result.one()

    dq_fail_result = await db.execute(
        select(func.count(DataQualityExecutionLog.id)).where(
            DataQualityExecutionLog.project_id == context.project.id,
            DataQualityExecutionLog.result == "FAIL",
            DataQualityExecutionLog.executed_at >= start_time,
        )
    )
    scheduler_fail_result = await db.execute(
        select(func.count(SchedulerRun.id)).where(
            SchedulerRun.project_id == context.project.id,
            SchedulerRun.status == "FAILED",
            SchedulerRun.started_at >= start_time,
        )
    )
    governance_result = await db.execute(
        select(func.count(GovernanceCheck.id)).where(
            GovernanceCheck.project_id == context.project.id,
            GovernanceCheck.created_at >= start_time,
        )
    )

    data = {
        "filters": {
            "selected_modules": selected_modules,
            "available_modules": AVAILABLE_MODULES,
            "window_minutes": window_minutes,
            "bucket_count": bucket_count,
            "bucket_seconds": bucket_seconds,
        },
        "summary": {
            "open_alerts": len(open_alerts),
            "critical_alerts": len(critical_alerts),
            "acknowledged_alerts": len(acknowledged_alerts),
            "resolved_alerts": len(resolved_24h),
            "total_alerts": len(alerts),
        },
        "trends": bucket_rows,
        "module_health": sorted(module_health, key=lambda item: item["module"]),
        "business_metrics": {
            "total_pipelines": int(total_pipelines or 0),
            "running_pipelines": int(running_pipelines or 0),
            "failed_pipelines": int(failed_pipelines or 0),
            "dq_rule_failures": int(dq_fail_result.scalar_one() or 0),
            "scheduler_failed_runs": int(scheduler_fail_result.scalar_one() or 0),
            "governance_checks": int(governance_result.scalar_one() or 0),
        },
        "collected_at": now.isoformat(),
    }
    return success_response(data)


@router.get("/alerts")
async def list_monitoring_alerts(
    q: str | None = Query(default=None),
    severity: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    source_module: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    query = select(Alert).where(Alert.project_id == context.project.id)
    filters = []
    if severity:
        filters.append(Alert.severity == severity.strip().upper())
    if status_filter:
        filters.append(Alert.status == status_filter.strip().upper())
    if q:
        keyword = f"%{q.strip()}%"
        filters.append(
            or_(
                Alert.title.ilike(keyword),
                Alert.description.ilike(keyword),
                Alert.source_id.ilike(keyword),
                Alert.source_type.ilike(keyword),
            )
        )
    if date_from:
        parsed_from = datetime.fromisoformat(date_from)
        filters.append(Alert.created_at >= parsed_from)
    if date_to:
        parsed_to = datetime.fromisoformat(date_to)
        filters.append(Alert.created_at <= parsed_to)
    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query.order_by(Alert.created_at.desc()))
    rows = list(result.scalars().all())

    if source_module:
        normalized_module = source_module.strip().upper()
        rows = [item for item in rows if _module_from_source_type(item.source_type) == normalized_module]

    total = len(rows)
    page_rows = rows[offset: offset + limit]

    module_counter = Counter(_module_from_source_type(item.source_type) for item in rows)
    severity_counter = Counter(item.severity for item in rows)
    status_counter = Counter(item.status for item in rows)

    data = {
        "items": [
            _alert_to_row(item)
            for item in sorted(
                page_rows,
                key=lambda item: (
                    -_alert_status_rank(item.status),
                    -_severity_rank(item.severity),
                    item.created_at,
                ),
                reverse=True,
            )
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": {
            "modules": [{"module": key, "count": count} for key, count in sorted(module_counter.items())],
            "severities": [{"severity": key, "count": count} for key, count in sorted(severity_counter.items())],
            "statuses": [{"status": key, "count": count} for key, count in sorted(status_counter.items())],
        },
    }
    return success_response(data)


@router.get("/alerts/{alert_id}")
async def get_monitoring_alert_detail(
    alert_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    alert_result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.project_id == context.project.id,
        )
    )
    alert = alert_result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    history_result = await db.execute(
        select(AlertActionHistory)
        .where(
            AlertActionHistory.alert_id == alert.id,
            AlertActionHistory.project_id == context.project.id,
        )
        .order_by(AlertActionHistory.created_at.desc())
    )
    history = list(history_result.scalars().all())

    around_minutes = 15
    bucket_minutes = 5
    alert_time = _as_utc(alert.created_at) or datetime.now(timezone.utc)
    begin_at = alert_time - timedelta(minutes=around_minutes)
    end_at = alert_time + timedelta(minutes=around_minutes)

    audit_result = await db.execute(
        select(AuditLog).where(
            or_(
                AuditLog.user_id == f"project:{context.project.id}",
                AuditLog.user_id == f"project_{context.project.id}",
                AuditLog.user_id.like(f"%|project:{context.project.id}"),
            ),
            AuditLog.timestamp >= begin_at,
            AuditLog.timestamp <= end_at,
        )
    )
    audit_rows = list(audit_result.scalars().all())
    audit_with_time = [(row, _as_utc(row.timestamp)) for row in audit_rows]

    timeline = []
    cursor = begin_at
    while cursor < end_at:
        next_cursor = cursor + timedelta(minutes=bucket_minutes)
        rows = [row for row, ts in audit_with_time if ts and cursor <= ts < next_cursor]
        failure_rows = [row for row in rows if "FAIL" in row.action or "ERROR" in row.action or "REJECT" in row.action]
        qps = round(len(rows) / (bucket_minutes * 60), 4)
        failure_rate = round((len(failure_rows) / len(rows)) if rows else 0.0, 4)
        latency_ms = round(90 + failure_rate * 400 + len(rows) * 0.35, 2)
        timeline.append(
            {
                "from": cursor.isoformat(),
                "to": next_cursor.isoformat(),
                "qps": qps,
                "failure_rate": failure_rate,
                "latency_ms": latency_ms,
            }
        )
        cursor = next_cursor

    data = {
        "alert": _alert_to_row(alert),
        "metadata": {
            "tenant_id": context.project.tenant_id,
            "project_id": context.project.id,
            "source_module": _module_from_source_type(alert.source_type),
            "source_type": alert.source_type,
            "source_id": alert.source_id,
        },
        "context_metrics": {
            "window_minutes": around_minutes,
            "bucket_minutes": bucket_minutes,
            "timeline": timeline,
        },
        "related_links": _alert_links(alert),
        "history": [_history_to_row(item) for item in history],
    }
    return success_response(data)


@router.post("/alerts/{alert_id}/actions")
async def operate_monitoring_alert(
    alert_id: int,
    request: AlertActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _check_write_context(context)
    action = request.action.strip().upper()
    if action not in {"CLAIM", "RESOLVE", "NOTE"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action: {request.action}")

    alert_result = await db.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.project_id == context.project.id,
        )
    )
    alert = alert_result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    now = datetime.now(timezone.utc)
    actor = _actor_email(context)
    patch: dict[str, Any] = {}
    note = request.note.strip() if request.note else None
    payload: dict[str, Any] = {}

    if action == "CLAIM":
        if alert.status == "RESOLVED":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resolved alert cannot be claimed")
        assignee = (request.assignee or actor).strip()
        patch.update({"status": "ACKNOWLEDGED", "claimed_by": assignee, "claimed_at": now})
        if note:
            patch["last_note"] = note
        payload = {"assignee": assignee}
        audit_action = "ALERT_CLAIM"
    elif action == "RESOLVE":
        patch.update({"status": "RESOLVED", "resolved_at": now})
        if not alert.claimed_by:
            patch["claimed_by"] = actor
            patch["claimed_at"] = now
        if note:
            patch["last_note"] = note
        payload = {"resolved_by": actor}
        audit_action = "ALERT_RESOLVE"
    else:
        if not note:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="note is required for NOTE action")
        patch.update({"last_note": note})
        payload = {"note_only": True}
        audit_action = "ALERT_NOTE"

    alert = await BaseRepository(Alert, db).update(alert, patch)
    history_repo = BaseRepository(AlertActionHistory, db)
    history = await history_repo.create(
        {
            "alert_id": alert.id,
            "project_id": alert.project_id,
            "action": action,
            "actor_id": context.actor_id,
            "note": note,
            "payload": payload,
        }
    )

    await _write_audit(
        db,
        context,
        action=audit_action,
        alert=alert,
        details={
            "operate_action": action,
            "patch": patch,
            "payload": payload,
        },
    )

    data = {
        "alert": _alert_to_row(alert),
        "latest_action": _history_to_row(history),
    }
    return success_response(data, message="Alert updated", code="MONITORING_ALERT_UPDATED")
