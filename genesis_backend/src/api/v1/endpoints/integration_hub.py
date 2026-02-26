import json
import secrets
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.domain.settings import decrypt_mapping, encrypt_mapping
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.integration_invocation_log import IntegrationInvocationLog
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.project_integration_setting import ProjectIntegrationSetting
from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

PROJECT_INTEGRATION_MANAGE_ROLES = {"OWNER", "ADMIN", "EDITOR"}
INTEGRATION_TYPES = {
    "LLM",
    "KAFKA",
    "FLINK",
    "QDRANT",
    "JIRA",
    "SLACK",
    "PROMETHEUS",
    "KAFKA_EXTERNAL",
    "WEBHOOK",
    "BI",
}
INTEGRATION_CATEGORY_MAP = {
    "LLM": "LLM",
    "KAFKA": "MESSAGE",
    "KAFKA_EXTERNAL": "MESSAGE",
    "FLINK": "DATA_INFRA",
    "QDRANT": "SEARCH",
    "JIRA": "TICKETING",
    "SLACK": "NOTIFICATION",
    "WEBHOOK": "NOTIFICATION",
    "PROMETHEUS": "MONITORING",
    "BI": "ANALYTICS",
}
INTEGRATION_SECRET_FIELDS = {
    "LLM": {"api_key"},
    "KAFKA": {"sasl_password"},
    "KAFKA_EXTERNAL": {"sasl_password"},
    "FLINK": {"token"},
    "QDRANT": {"api_key"},
    "JIRA": {"api_token"},
    "SLACK": {"bot_token"},
    "WEBHOOK": {"secret"},
    "PROMETHEUS": {"token"},
    "BI": {"api_key"},
}
ALLOWED_CALLER_MODULES = {
    "GOVERNANCE",
    "ALERTS",
    "DQ",
    "SCHEDULER",
    "KNOWLEDGE",
    "PIPELINES",
    "MONITORING",
    "EXPLORE",
    "CATALOG",
    "INTEGRATION_HUB",
}


class IntegrationHubTestRequest(BaseModel):
    integration_type: str = Field(..., min_length=2, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


class IntegrationHubUpsertRequest(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class IntegrationHubInvokeRequest(BaseModel):
    caller_module: str = Field(..., min_length=2, max_length=64)
    action: str = Field(..., min_length=2, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    simulate_failure: bool = Field(default=False)
    error_code: str | None = Field(default=None, max_length=64)
    note: str | None = Field(default=None, max_length=1000)


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


def _mask_secret(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value)
    if len(raw) <= 4:
        return "*" * len(raw)
    return f"{raw[:2]}***{raw[-2:]}"


def _normalize_integration_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in INTEGRATION_TYPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported integration_type: {value}")
    return normalized


def _normalize_caller_module(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_CALLER_MODULES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported caller_module: {value}")
    return normalized


def _mask_config(integration_type: str, config: dict[str, Any]) -> dict[str, Any]:
    secret_fields = INTEGRATION_SECRET_FIELDS.get(integration_type, set())
    output: dict[str, Any] = {}
    for key, value in config.items():
        output[key] = _mask_secret(value) if key in secret_fields else value
    return output


def _merge_config(integration_type: str, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    secret_fields = INTEGRATION_SECRET_FIELDS.get(integration_type, set())
    for key, value in incoming.items():
        if key in secret_fields and isinstance(value, str):
            if not value.strip() or "***" in value:
                continue
        merged[key] = value
    return merged


def _validate_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")


def _validate_integration_config(integration_type: str, config: dict[str, Any]) -> tuple[str, str, str | None]:
    if integration_type == "LLM":
        api_key = str(config.get("api_key", "")).strip()
        if not api_key:
            return "FAILURE", "Missing api_key", "MISSING_API_KEY"
        if not api_key.startswith("sk-"):
            return "FAILURE", "api_key should start with sk-", "INVALID_API_KEY_FORMAT"
        base_url = str(config.get("base_url", "")).strip()
        if base_url and not _validate_url(base_url):
            return "FAILURE", "base_url must be http(s)", "INVALID_BASE_URL"
        return "SUCCESS", "LLM integration validated", None

    if integration_type in {"KAFKA", "KAFKA_EXTERNAL"}:
        bootstrap = str(config.get("bootstrap_servers", "")).strip()
        if not bootstrap:
            return "FAILURE", "Missing bootstrap_servers", "MISSING_BOOTSTRAP_SERVERS"
        nodes = [item.strip() for item in bootstrap.split(",") if item.strip()]
        if not nodes or any(":" not in node for node in nodes):
            return "FAILURE", "bootstrap_servers should be host:port list", "INVALID_BOOTSTRAP_SERVERS"
        return "SUCCESS", "Kafka integration validated", None

    if integration_type == "FLINK":
        rest_url = str(config.get("rest_url", "")).strip()
        if not rest_url or not _validate_url(rest_url):
            return "FAILURE", "Missing/invalid rest_url", "INVALID_REST_URL"
        return "SUCCESS", "Flink integration validated", None

    if integration_type == "QDRANT":
        host = str(config.get("host", "")).strip()
        if not host:
            return "FAILURE", "Missing host", "MISSING_HOST"
        try:
            port = int(config.get("port", 6333))
        except (TypeError, ValueError):
            return "FAILURE", "port must be integer", "INVALID_PORT"
        if port <= 0 or port > 65535:
            return "FAILURE", "port out of range", "INVALID_PORT_RANGE"
        return "SUCCESS", "Qdrant integration validated", None

    if integration_type == "JIRA":
        base_url = str(config.get("base_url", "")).strip()
        project_key = str(config.get("project_key", "")).strip()
        if not base_url or not _validate_url(base_url):
            return "FAILURE", "Missing/invalid base_url", "INVALID_BASE_URL"
        if not project_key:
            return "FAILURE", "Missing project_key", "MISSING_PROJECT_KEY"
        return "SUCCESS", "Jira integration validated", None

    if integration_type == "SLACK":
        bot_token = str(config.get("bot_token", "")).strip()
        channel = str(config.get("channel", "")).strip()
        if not bot_token:
            return "FAILURE", "Missing bot_token", "MISSING_BOT_TOKEN"
        if not channel:
            return "FAILURE", "Missing channel", "MISSING_CHANNEL"
        return "SUCCESS", "Slack integration validated", None

    if integration_type == "PROMETHEUS":
        endpoint = str(config.get("endpoint", "")).strip()
        if not endpoint or not _validate_url(endpoint):
            return "FAILURE", "Missing/invalid endpoint", "INVALID_ENDPOINT"
        return "SUCCESS", "Prometheus integration validated", None

    if integration_type == "WEBHOOK":
        endpoint = str(config.get("endpoint", "")).strip()
        if not endpoint or not _validate_url(endpoint):
            return "FAILURE", "Missing/invalid endpoint", "INVALID_ENDPOINT"
        return "SUCCESS", "Webhook integration validated", None

    if integration_type == "BI":
        endpoint = str(config.get("endpoint", "")).strip()
        workspace = str(config.get("workspace", "")).strip()
        if not endpoint or not _validate_url(endpoint):
            return "FAILURE", "Missing/invalid endpoint", "INVALID_ENDPOINT"
        if not workspace:
            return "FAILURE", "Missing workspace", "MISSING_WORKSPACE"
        return "SUCCESS", "BI integration validated", None

    return "FAILURE", "Unknown integration type", "UNKNOWN_INTEGRATION_TYPE"


def _integration_template(integration_type: str) -> dict[str, Any]:
    templates = {
        "LLM": {"api_key": "", "base_url": "https://api.openai.com", "model": "gpt-4o-mini"},
        "KAFKA": {"bootstrap_servers": "kafka-a:9092,kafka-b:9092", "security_protocol": "PLAINTEXT"},
        "KAFKA_EXTERNAL": {"bootstrap_servers": "ext-kafka:9092", "security_protocol": "SASL_SSL"},
        "FLINK": {"rest_url": "http://flink-jobmanager:8081", "cluster": "default"},
        "QDRANT": {"host": "qdrant.internal", "port": 6333, "collection": "events"},
        "JIRA": {"base_url": "https://your-company.atlassian.net", "project_key": "DATA", "issue_type": "Task"},
        "SLACK": {"channel": "#data-alerts", "bot_token": ""},
        "PROMETHEUS": {"endpoint": "http://prometheus:9090", "pushgateway": "http://pushgateway:9091"},
        "WEBHOOK": {"endpoint": "https://hooks.example.com/events", "secret": ""},
        "BI": {"endpoint": "https://bi.example.com/api", "workspace": "default"},
    }
    return templates.get(integration_type, {})


def _integration_category(integration_type: str) -> str:
    return INTEGRATION_CATEGORY_MAP.get(integration_type, "OTHER")


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Integration Hub requires bearer user context")


def _require_project_role(context: RequestContext, allowed_roles: set[str]) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in allowed_roles:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (allowed_roles & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for this integration operation")

async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    integration_type: str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "PROJECT_INTEGRATION",
            "entity_id": integration_type,
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


async def _write_invocation(
    db: AsyncSession,
    *,
    project_id: int,
    integration_type: str,
    caller_module: str,
    action: str,
    status_value: str,
    error_code: str | None,
    error_message: str | None,
    latency_ms: int,
    request_payload: dict[str, Any],
    response_payload: dict[str, Any],
    actor_id: str,
) -> IntegrationInvocationLog:
    return await BaseRepository(IntegrationInvocationLog, db).create(
        {
            "project_id": project_id,
            "integration_type": integration_type,
            "caller_module": caller_module,
            "action": action,
            "status": status_value,
            "error_code": error_code,
            "error_message": error_message,
            "latency_ms": latency_ms,
            "request_payload": request_payload,
            "response_payload": response_payload,
            "actor_id": actor_id,
        }
    )


async def _open_integration_alert(
    db: AsyncSession,
    *,
    project_id: int,
    integration_type: str,
    caller_module: str,
    title: str,
    description: str,
) -> Alert:
    source_id = f"{integration_type}:{caller_module}"
    existing_result = await db.execute(
        select(Alert).where(
            and_(
                Alert.project_id == project_id,
                Alert.source_type == "INTEGRATION",
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
            "source_type": "INTEGRATION",
            "source_id": source_id,
            "severity": "HIGH",
            "title": title[:255],
            "description": description[:1000],
            "status": "OPEN",
        }
    )


async def _build_static_usage(db: AsyncSession, *, project_id: int, integration_type: str) -> list[dict[str, Any]]:
    usage_rows: list[dict[str, Any]] = []
    if integration_type == "LLM":
        result = await db.execute(select(GovernanceCheck).where(GovernanceCheck.project_id == project_id))
        rows = list(result.scalars().all())
        if rows:
            latest = max((_as_utc(item.created_at) for item in rows), default=None)
            usage_rows.append(
                {
                    "module": "GOVERNANCE",
                    "calls": len(rows),
                    "success_calls": len([item for item in rows if item.verdict == "APPROVE"]),
                    "failure_calls": len([item for item in rows if item.verdict != "APPROVE"]),
                    "last_used_at": _to_iso(latest),
                }
            )
    elif integration_type in {"KAFKA", "KAFKA_EXTERNAL", "FLINK"}:
        result = await db.execute(select(Pipeline).where(Pipeline.project_id == project_id))
        rows = list(result.scalars().all())
        if rows:
            latest = max((_as_utc(item.updated_at) for item in rows), default=None)
            usage_rows.append(
                {
                    "module": "PIPELINES",
                    "calls": len(rows),
                    "success_calls": len([item for item in rows if item.status == "RUNNING"]),
                    "failure_calls": len([item for item in rows if item.status in {"FAILED", "ROLLING_BACK"}]),
                    "last_used_at": _to_iso(latest),
                }
            )
    elif integration_type == "QDRANT":
        result = await db.execute(select(TrackingEvent).where(TrackingEvent.project_id == project_id))
        rows = list(result.scalars().all())
        if rows:
            latest = max((_as_utc(item.updated_at) for item in rows), default=None)
            usage_rows.append(
                {
                    "module": "CATALOG",
                    "calls": len(rows),
                    "success_calls": len(rows),
                    "failure_calls": 0,
                    "last_used_at": _to_iso(latest),
                }
            )
    elif integration_type == "PROMETHEUS":
        result = await db.execute(select(Alert).where(Alert.project_id == project_id))
        rows = list(result.scalars().all())
        if rows:
            latest = max((_as_utc(item.created_at) for item in rows), default=None)
            usage_rows.append(
                {
                    "module": "MONITORING",
                    "calls": len(rows),
                    "success_calls": len([item for item in rows if item.status != "OPEN"]),
                    "failure_calls": len([item for item in rows if item.status == "OPEN"]),
                    "last_used_at": _to_iso(latest),
                }
            )
    elif integration_type in {"JIRA", "SLACK", "WEBHOOK", "BI"}:
        result = await db.execute(select(SchedulerDag).where(SchedulerDag.project_id == project_id))
        rows = list(result.scalars().all())
        if rows:
            latest = max((_as_utc(item.updated_at) for item in rows), default=None)
            usage_rows.append(
                {
                    "module": "SCHEDULER",
                    "calls": len(rows),
                    "success_calls": len(rows),
                    "failure_calls": 0,
                    "last_used_at": _to_iso(latest),
                }
            )
    return usage_rows


async def _build_integration_runtime(db: AsyncSession, *, project_id: int, integration_type: str) -> dict[str, Any]:
    invocation_result = await db.execute(
        select(IntegrationInvocationLog)
        .where(
            IntegrationInvocationLog.project_id == project_id,
            IntegrationInvocationLog.integration_type == integration_type,
        )
        .order_by(IntegrationInvocationLog.created_at.desc(), IntegrationInvocationLog.id.desc())
        .limit(400)
    )
    invocations = list(invocation_result.scalars().all())
    now = datetime.now(timezone.utc)
    threshold_7d = now - timedelta(days=7)
    calls_7d = [row for row in invocations if _as_utc(row.created_at) and _as_utc(row.created_at) >= threshold_7d]

    failure_7d = [row for row in calls_7d if row.status != "SUCCESS"]
    success_7d = [row for row in calls_7d if row.status == "SUCCESS"]
    success_rate_7d = round((len(success_7d) / len(calls_7d)) if calls_7d else 1.0, 6)
    error_distribution = Counter(row.error_code or "UNKNOWN" for row in failure_7d)
    last_heartbeat = _as_utc(invocations[0].created_at) if invocations else None

    usage_by_module: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "success_calls": 0, "failure_calls": 0, "last_used_at": None}
    )
    for row in invocations:
        module = row.caller_module
        target = usage_by_module[module]
        target["calls"] += 1
        if row.status == "SUCCESS":
            target["success_calls"] += 1
        else:
            target["failure_calls"] += 1
        row_time = _as_utc(row.created_at)
        if row_time and (target["last_used_at"] is None or row_time > target["last_used_at"]):
            target["last_used_at"] = row_time

    usage_rows = [
        {
            "module": module,
            "calls": value["calls"],
            "success_calls": value["success_calls"],
            "failure_calls": value["failure_calls"],
            "last_used_at": _to_iso(value["last_used_at"]),
        }
        for module, value in usage_by_module.items()
    ]

    static_usage_rows = await _build_static_usage(db, project_id=project_id, integration_type=integration_type)
    existing_modules = {item["module"] for item in usage_rows}
    for item in static_usage_rows:
        if item["module"] not in existing_modules:
            usage_rows.append(item)
    usage_rows.sort(key=lambda item: (item["calls"], item["module"]), reverse=True)

    health_status = "UNKNOWN"
    if calls_7d:
        if len(failure_7d) >= 5 and success_rate_7d < 0.75:
            health_status = "UNHEALTHY"
        elif len(failure_7d) >= 2 and success_rate_7d < 0.9:
            health_status = "WARNING"
        else:
            health_status = "HEALTHY"

    return {
        "usage_scenarios": usage_rows,
        "health": {
            "status": health_status,
            "last_heartbeat_at": _to_iso(last_heartbeat),
            "total_calls_7d": len(calls_7d),
            "success_calls_7d": len(success_7d),
            "failure_calls_7d": len(failure_7d),
            "success_rate_7d": success_rate_7d,
            "error_code_distribution": [{"error_code": code, "count": count} for code, count in error_distribution.most_common()],
        },
        "recent_calls": [
            {
                "id": row.id,
                "caller_module": row.caller_module,
                "action": row.action,
                "status": row.status,
                "error_code": row.error_code,
                "error_message": row.error_message,
                "latency_ms": row.latency_ms,
                "actor": parse_actor(row.actor_id),
                "created_at": _to_iso(row.created_at),
            }
            for row in invocations[:30]
        ],
    }


def _integration_to_row(integration_type: str, row: ProjectIntegrationSetting | None, runtime: dict[str, Any]) -> dict[str, Any]:
    if row is None:
        return {
            "integration_type": integration_type,
            "category": _integration_category(integration_type),
            "enabled": False,
            "config": _integration_template(integration_type),
            "has_stored_secret": False,
            "last_test": None,
            **runtime,
            "created_at": None,
            "updated_at": None,
        }

    decrypted = decrypt_mapping(row.encrypted_config)
    secret_fields = INTEGRATION_SECRET_FIELDS.get(integration_type, set())
    return {
        "integration_type": integration_type,
        "category": _integration_category(integration_type),
        "enabled": row.enabled,
        "config": _mask_config(integration_type, decrypted),
        "has_stored_secret": any(bool(str(decrypted.get(field, "")).strip()) for field in secret_fields),
        "last_test": {
            "status": row.last_test_status,
            "message": row.last_test_message,
            "tested_at": _to_iso(row.last_tested_at),
        }
        if row.last_test_status
        else None,
        **runtime,
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
    }


@router.get("/overview")
async def get_integration_hub_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(select(ProjectIntegrationSetting).where(ProjectIntegrationSetting.project_id == context.project.id))
    row_map = {item.integration_type: item for item in result.scalars().all()}

    items: list[dict[str, Any]] = []
    for integration_type in sorted(INTEGRATION_TYPES):
        runtime = await _build_integration_runtime(db, project_id=context.project.id, integration_type=integration_type)
        items.append(_integration_to_row(integration_type, row_map.get(integration_type), runtime))

    configured_count = len([item for item in items if item["created_at"] is not None])
    enabled_count = len([item for item in items if item["enabled"]])
    healthy_count = len([item for item in items if item["enabled"] and item["health"]["status"] in {"HEALTHY", "WARNING"}])
    unhealthy_count = len([item for item in items if item["enabled"] and item["health"]["status"] == "UNHEALTHY"])

    categories = Counter(item["category"] for item in items)
    all_failures = Counter()
    for item in items:
        for error_item in item["health"]["error_code_distribution"]:
            all_failures[error_item["error_code"]] += error_item["count"]

    audit_result = await db.execute(
        select(AuditLog)
        .where(and_(AuditLog.entity_type == "PROJECT_INTEGRATION", build_project_audit_filter(context.project.id)))
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
                "integration_type": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "configured_count": configured_count,
                "enabled_count": enabled_count,
                "healthy_count": healthy_count,
                "unhealthy_count": unhealthy_count,
                "coverage_ratio": round((enabled_count / len(INTEGRATION_TYPES)) if INTEGRATION_TYPES else 0.0, 6),
            },
            "category_breakdown": [{"category": key, "count": categories[key]} for key in sorted(categories.keys())],
            "top_failures": [{"error_code": key, "count": value} for key, value in all_failures.most_common(10)],
            "recent_activity": recent_activity,
            "items": items,
        }
    )

@router.get("/integrations")
async def list_integrations(
    q: str | None = Query(default=None),
    integration_type: str | None = Query(default=None),
    category: str | None = Query(default=None),
    enabled: bool | None = Query(default=None),
    health_status: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_type = _normalize_integration_type(integration_type) if integration_type else None
    normalized_category = category.strip().upper() if category else None
    normalized_health = health_status.strip().upper() if health_status else None

    result = await db.execute(select(ProjectIntegrationSetting).where(ProjectIntegrationSetting.project_id == context.project.id))
    row_map = {item.integration_type: item for item in result.scalars().all()}

    rows: list[dict[str, Any]] = []
    target_types = [normalized_type] if normalized_type else sorted(INTEGRATION_TYPES)
    for current_type in target_types:
        runtime = await _build_integration_runtime(db, project_id=context.project.id, integration_type=current_type)
        rows.append(_integration_to_row(current_type, row_map.get(current_type), runtime))

    filtered = []
    for row in rows:
        if normalized_category and row["category"] != normalized_category:
            continue
        if enabled is not None and bool(row["enabled"]) != enabled:
            continue
        if normalized_health and row["health"]["status"] != normalized_health:
            continue
        if q and q.strip():
            text = q.strip().lower()
            haystack = " ".join(
                [
                    row["integration_type"],
                    row["category"],
                    str(row["last_test"]["message"]) if row["last_test"] else "",
                    " ".join(item["module"] for item in row["usage_scenarios"]),
                ]
            ).lower()
            if text not in haystack:
                continue
        filtered.append(row)

    total = len(filtered)
    items = filtered[offset : offset + limit]
    return success_response(
        {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "types": sorted({item["integration_type"] for item in filtered}),
                "categories": sorted({item["category"] for item in filtered}),
                "health_statuses": sorted({item["health"]["status"] for item in filtered}),
            },
        }
    )


@router.get("/integrations/{integration_type}")
async def get_integration_detail(
    integration_type: str,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_type = _normalize_integration_type(integration_type)
    result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id,
            ProjectIntegrationSetting.integration_type == normalized_type,
        )
    )
    row = result.scalar_one_or_none()
    runtime = await _build_integration_runtime(db, project_id=context.project.id, integration_type=normalized_type)
    return success_response(
        {
            "integration": _integration_to_row(normalized_type, row, runtime),
            "template": _integration_template(normalized_type),
        }
    )


@router.post("/test")
async def test_integration(
    request: IntegrationHubTestRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_INTEGRATION_MANAGE_ROLES)
    normalized_type = _normalize_integration_type(request.integration_type)
    result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id,
            ProjectIntegrationSetting.integration_type == normalized_type,
        )
    )
    existing = result.scalar_one_or_none()
    existing_config = decrypt_mapping(existing.encrypted_config) if existing else {}
    merged_config = _merge_config(normalized_type, existing_config, request.config)

    test_status, test_message, error_code = _validate_integration_config(normalized_type, merged_config)
    latency_ms = int(40 + min(300, len(json.dumps(merged_config, ensure_ascii=True)) * 0.35))

    await _write_invocation(
        db,
        project_id=context.project.id,
        integration_type=normalized_type,
        caller_module="INTEGRATION_HUB",
        action="TEST_CONNECTION",
        status_value=test_status,
        error_code=error_code,
        error_message=None if test_status == "SUCCESS" else test_message,
        latency_ms=latency_ms,
        request_payload={"config_keys": sorted(merged_config.keys())},
        response_payload={"message": test_message},
        actor_id=context.actor_id,
    )

    await _write_audit(
        db,
        context,
        "INTEGRATION_HUB_TEST",
        normalized_type,
        {
            "summary": f"Integration test {test_status}",
            "message": test_message,
            "error_code": error_code,
        },
    )

    return success_response(
        {
            "integration_type": normalized_type,
            "status": test_status,
            "message": test_message,
            "error_code": error_code,
            "latency_ms": latency_ms,
        },
        message="Integration test executed",
        code="INTEGRATION_HUB_TESTED",
    )


@router.put("/integrations/{integration_type}")
async def upsert_integration(
    integration_type: str,
    request: IntegrationHubUpsertRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_INTEGRATION_MANAGE_ROLES)
    normalized_type = _normalize_integration_type(integration_type)

    result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id,
            ProjectIntegrationSetting.integration_type == normalized_type,
        )
    )
    existing = result.scalar_one_or_none()
    existing_config = decrypt_mapping(existing.encrypted_config) if existing else {}
    merged_config = _merge_config(normalized_type, existing_config, request.config)
    test_status, test_message, error_code = _validate_integration_config(normalized_type, merged_config)

    enabled_value = request.enabled if request.enabled is not None else (existing.enabled if existing else False)
    if enabled_value and test_status != "SUCCESS":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Integration test failed: {test_message}")

    patch_data = {
        "enabled": enabled_value,
        "encrypted_config": encrypt_mapping(merged_config),
        "last_test_status": test_status,
        "last_test_message": test_message,
        "last_tested_at": datetime.now(timezone.utc),
    }
    repo = BaseRepository(ProjectIntegrationSetting, db)
    if existing:
        row = await repo.update(existing, patch_data)
    else:
        row = await repo.create({"project_id": context.project.id, "integration_type": normalized_type, **patch_data})

    await _write_invocation(
        db,
        project_id=context.project.id,
        integration_type=normalized_type,
        caller_module="INTEGRATION_HUB",
        action="SAVE_CONFIGURATION",
        status_value="SUCCESS",
        error_code=None,
        error_message=None,
        latency_ms=35,
        request_payload={"enabled": enabled_value, "config_keys": sorted(merged_config.keys())},
        response_payload={"status": test_status, "message": test_message},
        actor_id=context.actor_id,
    )

    await _write_audit(
        db,
        context,
        "INTEGRATION_HUB_SAVE",
        normalized_type,
        {
            "summary": "Integration configuration saved",
            "enabled": enabled_value,
            "test_status": test_status,
            "test_message": test_message,
        },
    )

    runtime = await _build_integration_runtime(db, project_id=context.project.id, integration_type=normalized_type)
    return success_response(
        _integration_to_row(normalized_type, row, runtime),
        message="Integration saved",
        code="INTEGRATION_HUB_SAVED",
    )


@router.post("/integrations/{integration_type}/invoke")
async def invoke_integration(
    integration_type: str,
    request: IntegrationHubInvokeRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_type = _normalize_integration_type(integration_type)
    caller_module = _normalize_caller_module(request.caller_module)
    action_name = request.action.strip().upper()

    result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id,
            ProjectIntegrationSetting.integration_type == normalized_type,
        )
    )
    row = result.scalar_one_or_none()
    is_available = bool(row and row.enabled)

    if not is_available:
        failure_code = "INTEGRATION_DISABLED" if row else "INTEGRATION_NOT_CONFIGURED"
        failure_message = f"{normalized_type} is disabled" if row else f"{normalized_type} is not configured"
        invocation = await _write_invocation(
            db,
            project_id=context.project.id,
            integration_type=normalized_type,
            caller_module=caller_module,
            action=action_name,
            status_value="FAILURE",
            error_code=failure_code,
            error_message=failure_message,
            latency_ms=12,
            request_payload=request.payload,
            response_payload={"message": failure_message},
            actor_id=context.actor_id,
        )
        alert = await _open_integration_alert(
            db,
            project_id=context.project.id,
            integration_type=normalized_type,
            caller_module=caller_module,
            title=f"Integration call failed: {normalized_type}",
            description=failure_message,
        )
        await _write_audit(
            db,
            context,
            "INTEGRATION_HUB_INVOKE_FAILURE",
            normalized_type,
            {
                "summary": "Integration invoke failed",
                "caller_module": caller_module,
                "action": action_name,
                "error_code": failure_code,
                "message": failure_message,
                "alert_id": alert.id,
                "invocation_id": invocation.id,
            },
        )
        return success_response(
            {
                "status": "FAILURE",
                "integration_type": normalized_type,
                "caller_module": caller_module,
                "action": action_name,
                "error_code": failure_code,
                "message": failure_message,
                "alert_id": alert.id,
            },
            message="Integration invoke failed",
            code="INTEGRATION_HUB_INVOKE_FAILED",
        )

    simulated_failure = request.simulate_failure
    latency_ms = int(50 + min(600, len(json.dumps(request.payload, ensure_ascii=True)) * 0.2))

    if simulated_failure:
        failure_code = request.error_code.strip().upper() if request.error_code else "DOWNSTREAM_TIMEOUT"
        failure_message = request.note or "Simulated integration failure"
        invocation = await _write_invocation(
            db,
            project_id=context.project.id,
            integration_type=normalized_type,
            caller_module=caller_module,
            action=action_name,
            status_value="FAILURE",
            error_code=failure_code,
            error_message=failure_message,
            latency_ms=latency_ms,
            request_payload=request.payload,
            response_payload={"message": failure_message},
            actor_id=context.actor_id,
        )
        alert = await _open_integration_alert(
            db,
            project_id=context.project.id,
            integration_type=normalized_type,
            caller_module=caller_module,
            title=f"Integration call failed: {normalized_type}",
            description=failure_message,
        )
        await _write_audit(
            db,
            context,
            "INTEGRATION_HUB_INVOKE_FAILURE",
            normalized_type,
            {
                "summary": "Integration invoke failed",
                "caller_module": caller_module,
                "action": action_name,
                "error_code": failure_code,
                "message": failure_message,
                "alert_id": alert.id,
                "invocation_id": invocation.id,
            },
        )
        return success_response(
            {
                "status": "FAILURE",
                "integration_type": normalized_type,
                "caller_module": caller_module,
                "action": action_name,
                "error_code": failure_code,
                "message": failure_message,
                "alert_id": alert.id,
            },
            message="Integration invoke failed",
            code="INTEGRATION_HUB_INVOKE_FAILED",
        )

    external_request_id = f"ext_{normalized_type.lower()}_{secrets.token_hex(6)}"
    invocation = await _write_invocation(
        db,
        project_id=context.project.id,
        integration_type=normalized_type,
        caller_module=caller_module,
        action=action_name,
        status_value="SUCCESS",
        error_code=None,
        error_message=None,
        latency_ms=latency_ms,
        request_payload=request.payload,
        response_payload={"external_request_id": external_request_id},
        actor_id=context.actor_id,
    )
    await _write_audit(
        db,
        context,
        "INTEGRATION_HUB_INVOKE_SUCCESS",
        normalized_type,
        {
            "summary": "Integration invoke succeeded",
            "caller_module": caller_module,
            "action": action_name,
            "external_request_id": external_request_id,
            "invocation_id": invocation.id,
        },
    )
    return success_response(
        {
            "status": "SUCCESS",
            "integration_type": normalized_type,
            "caller_module": caller_module,
            "action": action_name,
            "external_request_id": external_request_id,
            "latency_ms": latency_ms,
        },
        message="Integration invoke succeeded",
        code="INTEGRATION_HUB_INVOKED",
    )
