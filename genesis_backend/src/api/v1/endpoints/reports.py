import json
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
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
from src.infrastructure.database.models.custom_report_dashboard import CustomReportDashboard
from src.infrastructure.database.models.custom_report_dashboard_version import CustomReportDashboardVersion
from src.infrastructure.database.models.custom_report_saved_view import CustomReportSavedView
from src.infrastructure.database.models.data_quality_execution_log import DataQualityExecutionLog
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

KINDS = {"DASHBOARD", "REPORT"}
STATUSES = {"DRAFT", "PUBLISHED", "ARCHIVED"}
WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR"}
PUBLISH_ROLES = {"OWNER", "ADMIN", "APPROVER"}
ACTIONS = {"PUBLISH", "ARCHIVE", "UNARCHIVE", "CLONE", "SAVE_VIEW", "EXPORT", "REFRESH_CACHE", "SHARE"}
FORMATS = {"IMAGE", "PDF", "LINK"}
VISIBILITY = {"PROJECT", "ROLE_BASED", "PRIVATE", "LINK_ONLY"}
ROLE_SET = {"VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"}

DEFAULT_PERMISSION = {
    "visibility": "PROJECT",
    "viewer_roles": ["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"],
    "editor_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"],
    "clone_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"],
}

TEMPLATES: dict[str, dict[str, Any]] = {
    "OPS_MONITORING": {
        "key": "OPS_MONITORING",
        "kind": "DASHBOARD",
        "name": "Operations Monitoring Dashboard",
        "scenario": "OPERATIONS",
        "tags": ["ops", "monitoring"],
        "layout_payload": {
            "widgets": [
                {"id": "w1", "type": "KPI", "title": "Total Events", "dataset": "EVENT", "metric": "total"},
                {"id": "w2", "type": "BAR", "title": "Pipeline Status", "dataset": "PIPELINE", "metric": "status"},
                {"id": "w3", "type": "TABLE", "title": "Open Alerts", "dataset": "ALERT", "metric": "open"},
                {"id": "w4", "type": "LINE", "title": "Event Trend", "dataset": "EVENT", "metric": "trend"},
            ]
        },
    },
    "QUALITY_MONITORING": {
        "key": "QUALITY_MONITORING",
        "kind": "DASHBOARD",
        "name": "Data Quality Monitoring Dashboard",
        "scenario": "QUALITY",
        "tags": ["quality", "dq"],
        "layout_payload": {
            "widgets": [
                {"id": "w1", "type": "KPI", "title": "Active DQ Rules", "dataset": "DQ", "metric": "active_rules"},
                {"id": "w2", "type": "KPI", "title": "DQ Pass Rate", "dataset": "DQ", "metric": "pass_rate"},
                {"id": "w3", "type": "BAR", "title": "DQ Results", "dataset": "DQ", "metric": "result"},
                {
                    "id": "w4",
                    "type": "TABLE",
                    "title": "Governance Verdict",
                    "dataset": "GOVERNANCE",
                    "metric": "verdict",
                },
            ]
        },
    },
    "COST_ANALYSIS": {
        "key": "COST_ANALYSIS",
        "kind": "REPORT",
        "name": "Cost & Usage Analysis Report",
        "scenario": "COST",
        "tags": ["cost", "finance"],
        "layout_payload": {
            "widgets": [
                {"id": "w1", "type": "KPI", "title": "Estimated Cost", "dataset": "COST", "metric": "total"},
                {"id": "w2", "type": "PIE", "title": "Cost Breakdown", "dataset": "COST", "metric": "breakdown"},
                {"id": "w3", "type": "TABLE", "title": "Cost Drivers", "dataset": "COST", "metric": "drivers"},
            ]
        },
    },
}


class ReportCreateRequest(BaseModel):
    template_key: str | None = Field(default=None, max_length=128)
    kind: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    scenario: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)
    is_personal: bool = Field(default=False)
    layout_payload: dict[str, Any] = Field(default_factory=dict)
    query_payload: dict[str, Any] = Field(default_factory=dict)
    filter_payload: dict[str, Any] = Field(default_factory=dict)
    refresh_payload: dict[str, Any] = Field(default_factory=dict)
    permission_payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    change_note: str | None = Field(default=None, max_length=1000)


class ReportUpdateRequest(BaseModel):
    kind: str | None = Field(default=None, max_length=32)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    scenario: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)
    is_personal: bool | None = None
    layout_payload: dict[str, Any] | None = None
    query_payload: dict[str, Any] | None = None
    filter_payload: dict[str, Any] | None = None
    refresh_payload: dict[str, Any] | None = None
    permission_payload: dict[str, Any] | None = None
    tags: list[str] | None = None
    change_note: str | None = Field(default=None, max_length=1000)


class ReportActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
    clone_name: str | None = Field(default=None, max_length=255)
    view_name: str | None = Field(default=None, max_length=255)
    view_filter_payload: dict[str, Any] = Field(default_factory=dict)
    view_layout_override_payload: dict[str, Any] = Field(default_factory=dict)
    is_default_view: bool = Field(default=False)
    export_format: str | None = Field(default=None, max_length=32)
    link_expires_hours: int | None = Field(default=72, ge=1, le=720)
    time_window_days: int | None = Field(default=None, ge=1, le=180)
    share_payload: dict[str, Any] = Field(default_factory=dict)


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


def _normalize(value: str, *, allowed: set[str], field: str) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported {field}: {value}")
    return normalized


def _actor(context: RequestContext) -> str:
    return context.user.email if context.user else parse_actor(context.actor_id)


def _require_user(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reports API requires bearer user context")


def _require_write(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in WRITE_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (WRITE_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for reports mutation")


def _require_publish(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in PUBLISH_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (PUBLISH_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for publish/share action")


def _tenant_id(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


def _tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        item = tag.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item[:64])
    return out[:30]


def _permission(payload: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_PERMISSION)
    merged.update(payload or {})
    visibility = _normalize(str(merged.get("visibility") or "PROJECT"), allowed=VISIBILITY, field="visibility")
    normalize_roles = lambda values: sorted(
        list({_normalize(str(item), allowed=ROLE_SET, field="role") for item in values})
    )
    return {
        "visibility": visibility,
        "viewer_roles": normalize_roles(merged.get("viewer_roles") or DEFAULT_PERMISSION["viewer_roles"]),
        "editor_roles": normalize_roles(merged.get("editor_roles") or DEFAULT_PERMISSION["editor_roles"]),
        "clone_roles": normalize_roles(merged.get("clone_roles") or DEFAULT_PERMISSION["clone_roles"]),
    }


def _refresh(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    ttl = max(30, min(36000, int(raw.get("ttl_seconds", 300))))
    days = max(1, min(180, int(raw.get("time_window_days", 30))))
    return {"ttl_seconds": ttl, "time_window_days": days}


def _layout(payload: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(payload or {})
    widgets = raw.get("widgets") if isinstance(raw.get("widgets"), list) else []
    normalized_widgets = []
    for idx, widget in enumerate(widgets):
        if not isinstance(widget, dict):
            continue
        normalized_widgets.append(
            {
                "id": str(widget.get("id") or f"w_{idx + 1}")[:64],
                "type": str(widget.get("type") or "TABLE").upper(),
                "title": str(widget.get("title") or "Widget")[:255],
                "dataset": str(widget.get("dataset") or "EVENT").upper(),
                "metric": str(widget.get("metric") or "default").lower()[:64],
                "config": widget.get("config") if isinstance(widget.get("config"), dict) else {},
            }
        )
    return {"widgets": normalized_widgets, "grid": raw.get("grid") if isinstance(raw.get("grid"), dict) else {}}


def _role_set(context: RequestContext) -> set[str]:
    values: set[str] = set()
    if context.project_role:
        values.add(context.project_role.upper())
    if context.tenant_role:
        values.add(context.tenant_role.upper())
    return values


def _can_view(context: RequestContext, item: CustomReportDashboard) -> bool:
    actor = _actor(context)
    roles = _role_set(context)
    perm = _permission(item.permission_payload)
    if actor == item.created_by:
        return True
    if perm["visibility"] == "PROJECT":
        return True
    if perm["visibility"] == "PRIVATE":
        return bool(roles & {"OWNER", "ADMIN"})
    if perm["visibility"] == "ROLE_BASED":
        return bool(roles & set(perm["viewer_roles"]))
    if perm["visibility"] == "LINK_ONLY":
        return bool(roles & {"OWNER", "ADMIN"})
    return True


def _can_edit(context: RequestContext, item: CustomReportDashboard) -> bool:
    actor = _actor(context)
    if actor == item.created_by:
        return True
    return bool(_role_set(context) & set(_permission(item.permission_payload)["editor_roles"]))


def _can_clone(context: RequestContext, item: CustomReportDashboard) -> bool:
    actor = _actor(context)
    if actor == item.created_by:
        return True
    return bool(_role_set(context) & set(_permission(item.permission_payload)["clone_roles"]))


def _serialize(context: RequestContext, item: CustomReportDashboard) -> dict[str, Any]:
    layout_payload = item.layout_payload or {}
    widgets = layout_payload.get("widgets") if isinstance(layout_payload.get("widgets"), list) else []
    cached = item.cached_result_payload or {}
    return {
        "id": item.id,
        "tenant_id": item.tenant_id,
        "project_id": item.project_id,
        "kind": item.kind,
        "name": item.name,
        "description": item.description,
        "scenario": item.scenario,
        "status": item.status,
        "template_key": item.template_key,
        "is_personal": item.is_personal,
        "layout_payload": layout_payload,
        "query_payload": item.query_payload or {},
        "filter_payload": item.filter_payload or {},
        "refresh_payload": item.refresh_payload or {},
        "permission_payload": item.permission_payload or {},
        "tags": item.tags or [],
        "cached_summary": cached.get("summary") if isinstance(cached.get("summary"), dict) else {},
        "widget_count": len(widgets),
        "created_by": item.created_by,
        "updated_by": item.updated_by,
        "published_at": _to_iso(item.published_at),
        "last_data_refresh_at": _to_iso(item.last_data_refresh_at),
        "created_at": _to_iso(item.created_at),
        "updated_at": _to_iso(item.updated_at),
        "capabilities": {"can_view": _can_view(context, item), "can_edit": _can_edit(context, item), "can_clone": _can_clone(context, item)},
    }


def _snapshot(item: CustomReportDashboard) -> dict[str, Any]:
    return {
        "kind": item.kind,
        "name": item.name,
        "description": item.description,
        "scenario": item.scenario,
        "status": item.status,
        "template_key": item.template_key,
        "is_personal": item.is_personal,
        "layout_payload": item.layout_payload or {},
        "query_payload": item.query_payload or {},
        "filter_payload": item.filter_payload or {},
        "refresh_payload": item.refresh_payload or {},
        "permission_payload": item.permission_payload or {},
        "tags": item.tags or [],
    }


async def _create_version(db: AsyncSession, item: CustomReportDashboard, *, actor: str, note: str | None) -> None:
    result = await db.execute(
        select(CustomReportDashboardVersion)
        .where(CustomReportDashboardVersion.dashboard_id == item.id)
        .order_by(CustomReportDashboardVersion.version_no.desc())
        .limit(1)
    )
    latest = result.scalar_one_or_none()
    version_no = 1 if latest is None else int(latest.version_no) + 1
    await BaseRepository(CustomReportDashboardVersion, db).create(
        {
            "dashboard_id": item.id,
            "project_id": item.project_id,
            "version_no": version_no,
            "change_note": note,
            "snapshot_payload": _snapshot(item),
            "created_by": actor,
        }
    )


async def _audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    item_id: int | str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "CUSTOM_REPORT_DASHBOARD",
            "entity_id": str(item_id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


def _series(days: int, values: list[datetime]) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    counter: Counter[str] = Counter()
    for value in values:
        dt = _as_utc(value)
        if dt is None or dt < now - timedelta(days=days):
            continue
        counter[dt.date().isoformat()] += 1
    result = []
    for offset in range(days - 1, -1, -1):
        day = (now - timedelta(days=offset)).date().isoformat()
        result.append({"bucket": day, "value": counter.get(day, 0)})
    return result


def _cost(events: int, running_pipelines: int, dq_runs: int, open_alerts: int) -> dict[str, float]:
    ingest = round(events * 0.0012, 2)
    pipe = round(running_pipelines * 18.0, 2)
    dq = round(dq_runs * 0.25, 2)
    incident = round(open_alerts * 0.35, 2)
    return {"ingestion": ingest, "pipeline_compute": pipe, "dq_execution": dq, "incident_response": incident, "total": round(ingest + pipe + dq + incident, 2)}


async def _compute_data(db: AsyncSession, item: CustomReportDashboard, *, days: int, filters: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)

    events = list((await db.execute(select(TrackingEvent).where(TrackingEvent.project_id == item.project_id, TrackingEvent.created_at >= start))).scalars().all())
    pipelines = list((await db.execute(select(Pipeline).where(Pipeline.project_id == item.project_id))).scalars().all())
    dq_rules = list((await db.execute(select(DataQualityRule).where(DataQualityRule.project_id == item.project_id))).scalars().all())
    dq_exec = list((await db.execute(select(DataQualityExecutionLog).where(DataQualityExecutionLog.project_id == item.project_id, DataQualityExecutionLog.executed_at >= start))).scalars().all())
    alerts = list((await db.execute(select(Alert).where(Alert.project_id == item.project_id, Alert.created_at >= start))).scalars().all())
    audits = list((await db.execute(select(AuditLog).where(and_(AuditLog.timestamp >= start, build_project_audit_filter(item.project_id))))).scalars().all())
    gov_checks = list((await db.execute(select(GovernanceCheck).where(GovernanceCheck.project_id == item.project_id, GovernanceCheck.created_at >= start))).scalars().all())

    domain_filter = str(filters.get("domain") or "").strip().lower()
    filtered_events = [row for row in events if not domain_filter or (row.domain or "").lower() == domain_filter]
    running = len([row for row in pipelines if row.status in {"RUNNING", "PROVISIONING"}])
    open_alerts = [row for row in alerts if row.status in {"OPEN", "ACKNOWLEDGED"}]
    cost = _cost(len(filtered_events), running, len(dq_exec), len(open_alerts))

    widgets = []
    layout_payload = item.layout_payload or {}
    for widget in layout_payload.get("widgets", []):
        if not isinstance(widget, dict):
            continue
        dataset = str(widget.get("dataset") or "EVENT").upper()
        metric = str(widget.get("metric") or "default").lower()
        out: dict[str, Any] = {"widget_id": widget.get("id"), "type": widget.get("type"), "title": widget.get("title"), "dataset": dataset, "metric": metric}
        if dataset == "EVENT":
            if metric in {"total", "default"}:
                out["kpi"] = {"value": len(filtered_events), "unit": "events"}
            elif metric == "status":
                c = Counter(row.governance_status for row in filtered_events)
                out["series"] = [{"label": key, "value": c[key]} for key in sorted(c.keys())]
            else:
                out["series"] = _series(min(days, 30), [row.created_at for row in filtered_events])
        elif dataset == "PIPELINE":
            c = Counter(row.status for row in pipelines)
            out["series"] = [{"label": key, "value": c[key]} for key in sorted(c.keys())]
        elif dataset == "DQ":
            if metric in {"active_rules", "default"}:
                out["kpi"] = {"value": len([row for row in dq_rules if row.status == "ACTIVE"]), "unit": "rules"}
            elif metric == "pass_rate":
                rate = 1.0 if not dq_exec else sum(row.pass_rate for row in dq_exec) / len(dq_exec)
                out["kpi"] = {"value": round(rate, 4), "unit": "ratio"}
            else:
                c = Counter(row.result for row in dq_exec)
                out["series"] = [{"label": key, "value": c[key]} for key in sorted(c.keys())]
        elif dataset == "ALERT":
            c = Counter(row.severity for row in open_alerts)
            out["table"] = [{"severity": key, "count": c[key]} for key in sorted(c.keys())]
        elif dataset == "GOVERNANCE":
            c = Counter(row.verdict for row in gov_checks)
            out["table"] = [{"verdict": key, "count": c[key]} for key in sorted(c.keys())]
        elif dataset == "AUDIT":
            c = Counter(row.action for row in audits)
            out["series"] = [{"label": key, "value": c[key]} for key in sorted(c.keys())[:12]]
        else:
            if metric == "drivers":
                out["table"] = [{"driver": "event_count", "value": len(filtered_events)}, {"driver": "running_pipelines", "value": running}, {"driver": "dq_runs", "value": len(dq_exec)}, {"driver": "open_alerts", "value": len(open_alerts)}, {"driver": "estimated_total_usd", "value": cost["total"]}]
            elif metric == "breakdown":
                out["series"] = [{"label": key, "value": value} for key, value in cost.items() if key != "total"]
            else:
                out["kpi"] = {"value": cost["total"], "unit": "USD"}
        widgets.append(out)

    return {"computed_at": _to_iso(now), "time_window_days": days, "filters": filters, "widgets": widgets, "summary": {"event_count": len(filtered_events), "pipeline_count": len(pipelines), "running_pipeline_count": running, "dq_rule_count": len(dq_rules), "dq_execution_count": len(dq_exec), "alert_count": len(alerts), "audit_count": len(audits), "governance_check_count": len(gov_checks), "estimated_cost_total": cost["total"], "widget_count": len(widgets)}}


async def _cached_data(db: AsyncSession, item: CustomReportDashboard, *, days: int, filters: dict[str, Any], force: bool) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    refresh_payload = _refresh(item.refresh_payload or {})
    ttl = int(refresh_payload["ttl_seconds"])
    key = json.dumps({"id": item.id, "updated_at": _to_iso(_as_utc(item.updated_at)), "days": days, "filters": filters}, ensure_ascii=True, sort_keys=True, default=str)
    cached = item.cached_result_payload or {}
    last = _as_utc(item.last_data_refresh_at)
    if not force and cached.get("cache_key") == key and last and now <= last + timedelta(seconds=ttl):
        return cached

    payload = await _compute_data(db, item, days=days, filters=filters)
    payload["cache_key"] = key
    payload["cache_ttl_seconds"] = ttl
    await BaseRepository(CustomReportDashboard, db).update(item, {"cached_result_payload": payload, "last_data_refresh_at": now})
    return payload


@router.get("/overview")
async def get_reports_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    rows = list((await db.execute(select(CustomReportDashboard).where(CustomReportDashboard.project_id == context.project.id))).scalars().all())
    visible_rows = [row for row in rows if _can_view(context, row)]
    kind_counter = Counter(row.kind for row in visible_rows)
    status_counter = Counter(row.status for row in visible_rows)
    scenario_counter = Counter(row.scenario or "UNSET" for row in visible_rows)
    saved_view_count = len(
        (await db.execute(select(CustomReportSavedView).where(CustomReportSavedView.project_id == context.project.id, CustomReportSavedView.owner == _actor(context)))).scalars().all()
    )

    audits = list(
        (
            await db.execute(
                select(AuditLog)
                .where(and_(AuditLog.entity_type == "CUSTOM_REPORT_DASHBOARD", build_project_audit_filter(context.project.id)))
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(20)
            )
        ).scalars().all()
    )
    recent_activity = []
    for row in audits:
        details = _safe_json_loads(row.details)
        recent_activity.append(
            {
                "id": row.id,
                "timestamp": _to_iso(row.timestamp),
                "actor": parse_actor(row.user_id),
                "action": row.action,
                "dashboard_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_items": len(visible_rows),
                "dashboards": kind_counter.get("DASHBOARD", 0),
                "reports": kind_counter.get("REPORT", 0),
                "draft_items": status_counter.get("DRAFT", 0),
                "published_items": status_counter.get("PUBLISHED", 0),
                "archived_items": status_counter.get("ARCHIVED", 0),
                "saved_views": saved_view_count,
                "template_count": len(TEMPLATES),
            },
            "kind_distribution": [{"kind": key, "count": kind_counter[key]} for key in sorted(kind_counter.keys())],
            "status_distribution": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            "scenario_distribution": [{"scenario": key, "count": scenario_counter[key]} for key in sorted(scenario_counter.keys())],
            "recent_activity": recent_activity,
        }
    )


@router.get("/templates")
async def get_report_templates(
    context: RequestContext = Depends(get_request_context),
):
    _require_user(context)
    items = []
    for row in TEMPLATES.values():
        items.append(
            {
                "key": row["key"],
                "kind": row["kind"],
                "name": row["name"],
                "scenario": row.get("scenario"),
                "tags": row.get("tags", []),
                "layout_payload": row.get("layout_payload", {}),
            }
        )
    return success_response({"items": items, "total": len(items)})


@router.get("/items")
async def list_report_items(
    q: str | None = Query(default=None),
    kind: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    creator: str | None = Query(default=None),
    scenario: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    normalized_kind = _normalize(kind, allowed=KINDS, field="kind") if kind else None
    normalized_status = _normalize(status_filter, allowed=STATUSES, field="status") if status_filter else None
    creator_filter = creator.strip().lower() if creator else None
    scenario_filter = scenario.strip().lower() if scenario else None
    tag_filter = tag.strip().lower() if tag else None

    rows = list(
        (
            await db.execute(
                select(CustomReportDashboard)
                .where(CustomReportDashboard.project_id == context.project.id)
                .order_by(CustomReportDashboard.updated_at.desc(), CustomReportDashboard.id.desc())
            )
        ).scalars().all()
    )
    rows = [row for row in rows if _can_view(context, row)]
    if normalized_kind:
        rows = [row for row in rows if row.kind == normalized_kind]
    if normalized_status:
        rows = [row for row in rows if row.status == normalized_status]
    if creator_filter:
        rows = [row for row in rows if creator_filter in row.created_by.lower()]
    if scenario_filter:
        rows = [row for row in rows if scenario_filter in (row.scenario or "").lower()]
    if tag_filter:
        rows = [row for row in rows if tag_filter in (row.tags or [])]
    if q and q.strip():
        keyword = q.strip().lower()
        filtered = []
        for row in rows:
            text = " ".join([row.name, row.description or "", row.kind, row.scenario or "", row.created_by, " ".join(row.tags or [])]).lower()
            if keyword in text:
                filtered.append(row)
        rows = filtered

    total = len(rows)
    page_rows = rows[offset : offset + limit]
    status_counter = Counter(row.status for row in rows)
    kind_counter = Counter(row.kind for row in rows)
    creator_counter = Counter(row.created_by for row in rows)
    scenario_counter = Counter(row.scenario or "UNSET" for row in rows)
    tag_counter: Counter[str] = Counter()
    for row in rows:
        for row_tag in row.tags or []:
            tag_counter[row_tag] += 1

    return success_response(
        {
            "items": [_serialize(context, row) for row in page_rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
                "kinds": [{"kind": key, "count": kind_counter[key]} for key in sorted(kind_counter.keys())],
                "creators": [{"creator": key, "count": creator_counter[key]} for key in sorted(creator_counter.keys())],
                "scenarios": [{"scenario": key, "count": scenario_counter[key]} for key in sorted(scenario_counter.keys())],
                "tags": [{"tag": key, "count": tag_counter[key]} for key in sorted(tag_counter.keys())],
            },
        }
    )


@router.get("/items/{item_id}")
async def get_report_item_detail(
    item_id: int,
    include_data: bool = Query(default=True),
    time_window_days: int = Query(default=30, ge=1, le=180),
    runtime_filters: str | None = Query(default=None),
    saved_view_id: int | None = Query(default=None, ge=1),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    result = await db.execute(
        select(CustomReportDashboard).where(
            CustomReportDashboard.id == item_id,
            CustomReportDashboard.project_id == context.project.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report item not found")
    if not _can_view(context, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to view this item")

    actor = _actor(context)
    saved_views = list(
        (
            await db.execute(
                select(CustomReportSavedView)
                .where(
                    CustomReportSavedView.dashboard_id == item.id,
                    CustomReportSavedView.project_id == item.project_id,
                    CustomReportSavedView.owner == actor,
                )
                .order_by(CustomReportSavedView.updated_at.desc(), CustomReportSavedView.id.desc())
            )
        ).scalars().all()
    )
    filters = dict(item.filter_payload or {})
    if runtime_filters:
        try:
            parsed = json.loads(runtime_filters)
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid runtime_filters json") from exc
        if isinstance(parsed, dict):
            filters.update(parsed)
    if saved_view_id is not None:
        selected = next((row for row in saved_views if row.id == saved_view_id), None)
        if selected is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Saved view not found")
        filters.update(selected.filter_payload or {})

    data_payload = None
    if include_data:
        data_payload = await _cached_data(db, item, days=time_window_days, filters=filters, force=False)

    versions = list(
        (
            await db.execute(
                select(CustomReportDashboardVersion)
                .where(CustomReportDashboardVersion.dashboard_id == item.id)
                .order_by(CustomReportDashboardVersion.version_no.desc(), CustomReportDashboardVersion.id.desc())
                .limit(20)
            )
        ).scalars().all()
    )
    version_rows = [
        {
            "id": row.id,
            "dashboard_id": row.dashboard_id,
            "version_no": row.version_no,
            "change_note": row.change_note,
            "snapshot_payload": row.snapshot_payload or {},
            "created_by": row.created_by,
            "created_at": _to_iso(row.created_at),
        }
        for row in versions
    ]
    saved_view_rows = [
        {
            "id": row.id,
            "dashboard_id": row.dashboard_id,
            "owner": row.owner,
            "name": row.name,
            "filter_payload": row.filter_payload or {},
            "layout_override_payload": row.layout_override_payload or {},
            "is_default": row.is_default,
            "share_token": row.share_token,
            "expires_at": _to_iso(row.expires_at),
            "last_export_format": row.last_export_format,
            "last_export_at": _to_iso(row.last_export_at),
            "created_at": _to_iso(row.created_at),
            "updated_at": _to_iso(row.updated_at),
        }
        for row in saved_views
    ]
    return success_response(
        {
            "item": _serialize(context, item),
            "versions": version_rows,
            "saved_views": saved_view_rows,
            "applied_filters": filters,
            "data_payload": data_payload,
        }
    )


@router.post("/items")
async def create_report_item(
    request: ReportCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    _require_write(context)
    payload = request.model_dump()
    template_key = payload.get("template_key")
    if template_key:
        template = TEMPLATES.get(str(template_key).strip().upper())
        if template is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template not found: {template_key}")
        if not payload.get("kind"):
            payload["kind"] = template["kind"]
        if not payload.get("name"):
            payload["name"] = template["name"]
        if not payload.get("scenario"):
            payload["scenario"] = template.get("scenario")
        if not payload.get("tags"):
            payload["tags"] = list(template.get("tags", []))
        if not payload.get("layout_payload"):
            payload["layout_payload"] = dict(template.get("layout_payload", {}))
        payload["template_key"] = template["key"]

    kind_value = _normalize(str(payload.get("kind") or "DASHBOARD"), allowed=KINDS, field="kind")
    status_value = _normalize(str(payload.get("status") or "DRAFT"), allowed=STATUSES, field="status")
    if status_value == "PUBLISHED":
        _require_publish(context)
    name = str(payload.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name is required")

    actor = _actor(context)
    item = await BaseRepository(CustomReportDashboard, db).create(
        {
            "tenant_id": _tenant_id(context),
            "project_id": context.project.id,
            "kind": kind_value,
            "name": name[:255],
            "description": str(payload.get("description")).strip()[:1000] if payload.get("description") else None,
            "scenario": str(payload.get("scenario")).strip()[:128] if payload.get("scenario") else None,
            "status": status_value,
            "template_key": payload.get("template_key"),
            "is_personal": bool(payload.get("is_personal")),
            "layout_payload": _layout(payload.get("layout_payload")),
            "query_payload": dict(payload.get("query_payload") or {}),
            "filter_payload": dict(payload.get("filter_payload") or {}),
            "refresh_payload": _refresh(payload.get("refresh_payload")),
            "permission_payload": _permission(payload.get("permission_payload")),
            "tags": _tags(payload.get("tags") or []),
            "cached_result_payload": {},
            "published_at": datetime.now(timezone.utc) if status_value == "PUBLISHED" else None,
            "created_by": actor,
            "updated_by": actor,
        }
    )
    await _create_version(db, item, actor=actor, note=request.change_note or "Initial version")
    await _audit(
        db,
        context,
        "REPORT_DASHBOARD_CREATE",
        item.id,
        {"summary": "Report/dashboard created", "name": item.name, "kind": item.kind, "status": item.status},
    )
    return success_response(_serialize(context, item), message="Report/dashboard created", code="REPORT_DASHBOARD_CREATED")


@router.patch("/items/{item_id}")
async def update_report_item(
    item_id: int,
    request: ReportUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    _require_write(context)
    result = await db.execute(
        select(CustomReportDashboard).where(
            CustomReportDashboard.id == item_id,
            CustomReportDashboard.project_id == context.project.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report item not found")
    if not _can_edit(context, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to edit this item")

    patch = request.model_dump(exclude_none=True)
    if not patch:
        return success_response(_serialize(context, item), message="No changes", code="REPORT_NO_CHANGES")
    if "kind" in patch:
        patch["kind"] = _normalize(patch["kind"], allowed=KINDS, field="kind")
    if "status" in patch:
        patch["status"] = _normalize(patch["status"], allowed=STATUSES, field="status")
        if patch["status"] == "PUBLISHED":
            _require_publish(context)
            patch["published_at"] = datetime.now(timezone.utc)
    if "layout_payload" in patch:
        patch["layout_payload"] = _layout(patch["layout_payload"])
    if "refresh_payload" in patch:
        patch["refresh_payload"] = _refresh(patch["refresh_payload"])
    if "permission_payload" in patch:
        patch["permission_payload"] = _permission(patch["permission_payload"])
    if "tags" in patch:
        patch["tags"] = _tags(patch["tags"])
    if "name" in patch:
        patch["name"] = str(patch["name"]).strip()
        if len(patch["name"]) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name too short")
    if "description" in patch and patch["description"] is not None:
        patch["description"] = str(patch["description"]).strip()
    if "scenario" in patch:
        patch["scenario"] = str(patch["scenario"]).strip() or None

    actor = _actor(context)
    patch["updated_by"] = actor
    updated = await BaseRepository(CustomReportDashboard, db).update(item, patch)
    await _create_version(db, updated, actor=actor, note=request.change_note or "Report/dashboard updated")
    await _audit(
        db,
        context,
        "REPORT_DASHBOARD_UPDATE",
        updated.id,
        {"summary": "Report/dashboard updated", "patched_fields": sorted(list(patch.keys()))},
    )
    return success_response(_serialize(context, updated), message="Report/dashboard updated", code="REPORT_DASHBOARD_UPDATED")


@router.post("/items/{item_id}/actions")
async def operate_report_item(
    item_id: int,
    request: ReportActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    action = _normalize(request.action, allowed=ACTIONS, field="action")
    result = await db.execute(
        select(CustomReportDashboard).where(
            CustomReportDashboard.id == item_id,
            CustomReportDashboard.project_id == context.project.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report item not found")
    if not _can_view(context, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission for this item")

    actor = _actor(context)
    note = request.note.strip() if request.note else None
    now = datetime.now(timezone.utc)

    if action == "REFRESH_CACHE":
        if not _can_edit(context, item):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to refresh cache")
        days = int(request.time_window_days or _refresh(item.refresh_payload).get("time_window_days", 30))
        filters = dict(item.filter_payload or {})
        filters.update(request.view_filter_payload or {})
        payload = await _cached_data(db, item, days=days, filters=filters, force=True)
        await _audit(db, context, "REPORT_DASHBOARD_REFRESH_CACHE", item.id, {"summary": "Dashboard cache refreshed", "time_window_days": days})
        return success_response({"item": _serialize(context, item), "data_payload": payload}, message="Cache refreshed", code="REPORT_DASHBOARD_CACHE_REFRESHED")

    if action == "SAVE_VIEW":
        if request.is_default_view:
            rows = list((await db.execute(select(CustomReportSavedView).where(CustomReportSavedView.dashboard_id == item.id, CustomReportSavedView.owner == actor, CustomReportSavedView.is_default.is_(True)))).scalars().all())
            for row in rows:
                await BaseRepository(CustomReportSavedView, db).update(row, {"is_default": False})
        view = await BaseRepository(CustomReportSavedView, db).create(
            {
                "dashboard_id": item.id,
                "project_id": item.project_id,
                "owner": actor,
                "name": (request.view_name or f"{item.name} view").strip()[:255],
                "filter_payload": request.view_filter_payload or dict(item.filter_payload or {}),
                "layout_override_payload": request.view_layout_override_payload or {},
                "is_default": request.is_default_view,
            }
        )
        await _audit(db, context, "REPORT_DASHBOARD_SAVE_VIEW", item.id, {"summary": "Saved personalized view", "view_id": view.id})
        return success_response({"item": _serialize(context, item), "saved_view": {"id": view.id, "name": view.name, "is_default": view.is_default}}, message="Saved view created", code="REPORT_DASHBOARD_VIEW_SAVED")

    if action == "EXPORT":
        export_format = _normalize(request.export_format or "LINK", allowed=FORMATS, field="export_format")
        if export_format == "LINK":
            token = secrets.token_urlsafe(24)
            expires_at = now + timedelta(hours=int(request.link_expires_hours or 72))
            view = await BaseRepository(CustomReportSavedView, db).create(
                {
                    "dashboard_id": item.id,
                    "project_id": item.project_id,
                    "owner": actor,
                    "name": (request.view_name or f"{item.name} share").strip()[:255],
                    "filter_payload": request.view_filter_payload or dict(item.filter_payload or {}),
                    "layout_override_payload": request.view_layout_override_payload or {},
                    "is_default": False,
                    "share_token": token,
                    "expires_at": expires_at,
                    "last_export_format": "LINK",
                    "last_export_at": now,
                }
            )
            export_payload = {"format": "LINK", "url": f"/reports/shared/{token}", "expires_at": _to_iso(expires_at), "saved_view_id": view.id}
        else:
            filename = f"report_{item.id}_{int(now.timestamp())}.{export_format.lower()}"
            export_payload = {"format": export_format, "file_name": filename, "download_url": f"/exports/{filename}", "generated_at": _to_iso(now)}
        await _audit(db, context, "REPORT_DASHBOARD_EXPORT", item.id, {"summary": "Report/dashboard exported", "format": export_format})
        return success_response({"item": _serialize(context, item), "export": export_payload}, message="Export prepared", code="REPORT_DASHBOARD_EXPORTED")

    if action == "CLONE":
        if not _can_clone(context, item):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to clone")
        clone = await BaseRepository(CustomReportDashboard, db).create(
            {
                "tenant_id": item.tenant_id,
                "project_id": item.project_id,
                "kind": item.kind,
                "name": (request.clone_name or f"{item.name} (Clone)").strip()[:255],
                "description": item.description,
                "scenario": item.scenario,
                "status": "DRAFT",
                "template_key": item.template_key,
                "is_personal": item.is_personal,
                "layout_payload": item.layout_payload or {},
                "query_payload": item.query_payload or {},
                "filter_payload": item.filter_payload or {},
                "refresh_payload": item.refresh_payload or {},
                "permission_payload": item.permission_payload or {},
                "tags": list(item.tags or []),
                "cached_result_payload": {},
                "created_by": actor,
                "updated_by": actor,
            }
        )
        await _create_version(db, clone, actor=actor, note=note or "Clone created")
        await _audit(db, context, "REPORT_DASHBOARD_CLONE", item.id, {"summary": "Report/dashboard cloned", "source_id": item.id, "clone_id": clone.id})
        return success_response({"item": _serialize(context, item), "cloned_item": _serialize(context, clone)}, message="Clone created", code="REPORT_DASHBOARD_CLONED")

    if action == "SHARE":
        _require_publish(context)
        if not _can_edit(context, item):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to update share settings")
        merged = dict(item.permission_payload or {})
        merged.update(request.share_payload or {})
        updated = await BaseRepository(CustomReportDashboard, db).update(item, {"permission_payload": _permission(merged), "updated_by": actor})
        await _create_version(db, updated, actor=actor, note=note or "Share settings updated")
        await _audit(db, context, "REPORT_DASHBOARD_SHARE_UPDATE", item.id, {"summary": "Share settings updated", "visibility": updated.permission_payload.get("visibility")})
        return success_response({"item": _serialize(context, updated)}, message="Share settings updated", code="REPORT_DASHBOARD_SHARED")

    _require_publish(context)
    if not _can_edit(context, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to update status")

    if action == "PUBLISH":
        patch, audit_action = {"status": "PUBLISHED", "published_at": now, "updated_by": actor}, "REPORT_DASHBOARD_PUBLISH"
    elif action == "ARCHIVE":
        patch, audit_action = {"status": "ARCHIVED", "updated_by": actor}, "REPORT_DASHBOARD_ARCHIVE"
    else:
        patch, audit_action = {"status": "DRAFT", "updated_by": actor}, "REPORT_DASHBOARD_UNARCHIVE"
    updated = await BaseRepository(CustomReportDashboard, db).update(item, patch)
    await _create_version(db, updated, actor=actor, note=note or f"Action {action}")
    await _audit(db, context, audit_action, item.id, {"summary": f"Action {action}", "to_status": updated.status})
    return success_response({"item": _serialize(context, updated)}, message="Action applied", code="REPORT_DASHBOARD_ACTION_APPLIED")
