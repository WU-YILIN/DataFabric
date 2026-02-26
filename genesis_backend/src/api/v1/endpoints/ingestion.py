import hashlib
import json
import re
import secrets
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.ingestion_channel_config import IngestionChannelConfig
from src.infrastructure.database.models.ingestion_event_log import IngestionEventLog
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

PLATFORMS = {"WEB", "IOS", "ANDROID", "SERVER"}
ENVIRONMENTS = {"PROD", "STAGING", "DEV", "TEST"}
CHANNEL_STATUSES = {"ACTIVE", "INACTIVE"}
SAMPLING_MODES = {"ALL", "RATE", "NONE"}
WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR"}
DEFAULT_ENDPOINT_PATH = "/api/v1/ingestion/gateway/events"

DEFAULT_SWITCHES = {
    "enable_schema_check": True,
    "enable_realtime_governance": True,
    "enable_dq_hook": False,
    "enable_pii_masking": False,
}

SDK_DOWNLOAD_LINKS = {
    "WEB": {
        "npm": "https://npmjs.com/package/@genesis/ingestion-sdk-web",
        "cdn": "https://cdn.genesis.local/sdk/web/latest/genesis-sdk.min.js",
    },
    "IOS": {
        "cocoapods": "https://cocoapods.org/pods/GenesisIngestionSDK",
        "spm": "https://github.com/genesis-labs/ios-ingestion-sdk",
    },
    "ANDROID": {
        "maven": "https://repo.maven.apache.org/maven2/io/genesis/ingestion-sdk-android",
        "github": "https://github.com/genesis-labs/android-ingestion-sdk",
    },
    "SERVER": {
        "pypi": "https://pypi.org/project/genesis-ingestion-sdk",
        "npm": "https://npmjs.com/package/@genesis/ingestion-sdk-node",
    },
}


class IngestionChannelCreateRequest(BaseModel):
    platform: str = Field(..., min_length=2, max_length=32)
    app_name: str = Field(..., min_length=2, max_length=255)
    environment: str = Field(default="PROD", min_length=2, max_length=32)
    status: str = Field(default="ACTIVE", min_length=2, max_length=32)

    app_id: str | None = Field(default=None, max_length=128)
    endpoint_domain: str | None = Field(default=None, max_length=255)
    endpoint_path: str = Field(default=DEFAULT_ENDPOINT_PATH, max_length=255)
    auth_mode: str = Field(default="HEADER_KEY", max_length=32)

    sampling_mode: str = Field(default="ALL", max_length=32)
    sampling_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    switches_payload: dict[str, Any] = Field(default_factory=dict)
    blocked_events: list[str] = Field(default_factory=list)

    sdk_version: str = Field(default="1.0.0", max_length=64)
    sdk_config_payload: dict[str, Any] = Field(default_factory=dict)
    quickstart_payload: dict[str, Any] = Field(default_factory=dict)


class IngestionChannelUpdateRequest(BaseModel):
    app_name: str | None = Field(default=None, min_length=2, max_length=255)
    environment: str | None = Field(default=None, min_length=2, max_length=32)
    status: str | None = Field(default=None, min_length=2, max_length=32)

    endpoint_domain: str | None = Field(default=None, max_length=255)
    endpoint_path: str | None = Field(default=None, max_length=255)
    auth_mode: str | None = Field(default=None, max_length=32)

    sampling_mode: str | None = Field(default=None, max_length=32)
    sampling_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    switches_payload: dict[str, Any] | None = None
    blocked_events: list[str] | None = None

    sdk_version: str | None = Field(default=None, max_length=64)
    sdk_config_payload: dict[str, Any] | None = None
    quickstart_payload: dict[str, Any] | None = None


class IngestionRotateKeyRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=1000)


class IngestionGatewayEventRequest(BaseModel):
    app_id: str = Field(..., min_length=2, max_length=128)
    event_name: str = Field(..., min_length=2, max_length=255)
    event_ts: str | None = None
    sdk_version: str | None = Field(default=None, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


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


def _normalize_app_name(value: str) -> str:
    normalized = value.strip()
    if len(normalized) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="app_name too short")
    return normalized


def _sanitize_identifier(value: str) -> str:
    sanitized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return sanitized[:48] if sanitized else "app"


def _mask_ingest_key(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:6]}***{value[-4:]}"


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ingestion center requires bearer user context")


def _require_write_role(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in WRITE_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (WRITE_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for ingestion mutation")


def _tenant_id_from_context(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


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


def _generate_app_id(platform: str, environment: str, app_name: str) -> str:
    return f"{platform.lower()}_{environment.lower()}_{_sanitize_identifier(app_name)}_{secrets.token_hex(3)}"


def _generate_ingest_key() -> str:
    return f"ing_{secrets.token_urlsafe(24)}"


def _build_quickstart(channel: IngestionChannelConfig) -> dict[str, Any]:
    endpoint = f"https://{channel.endpoint_domain}{channel.endpoint_path}"
    platform = channel.platform.upper()

    snippets = {
        "WEB": (
            "import { GenesisIngestion } from '@genesis/ingestion-sdk-web'\n"
            "const sdk = new GenesisIngestion({ appId: '%s', ingestKey: '%s', endpoint: '%s' })\n"
            "sdk.track('commerce.order_created', { order_id: 'o_1001' })"
            % (channel.app_id, channel.ingest_key, endpoint)
        ),
        "IOS": (
            "let sdk = GenesisIngestion(appId: \"%s\", ingestKey: \"%s\", endpoint: \"%s\")\n"
            "sdk.track(eventName: \"commerce.order_created\", payload: [\"order_id\": \"o_1001\"])"
            % (channel.app_id, channel.ingest_key, endpoint)
        ),
        "ANDROID": (
            "val sdk = GenesisIngestion(appId = \"%s\", ingestKey = \"%s\", endpoint = \"%s\")\n"
            "sdk.track(\"commerce.order_created\", mapOf(\"order_id\" to \"o_1001\"))"
            % (channel.app_id, channel.ingest_key, endpoint)
        ),
        "SERVER": (
            "from genesis_ingestion import GenesisIngestion\n"
            "sdk = GenesisIngestion(app_id='%s', ingest_key='%s', endpoint='%s')\n"
            "sdk.track('commerce.order_created', {'order_id': 'o_1001'})"
            % (channel.app_id, channel.ingest_key, endpoint)
        ),
    }

    return {
        "endpoint": endpoint,
        "headers": {"X-INGEST-KEY": channel.ingest_key},
        "sample_payload": {
            "app_id": channel.app_id,
            "event_name": "commerce.order_created",
            "event_ts": datetime.now(timezone.utc).isoformat(),
            "sdk_version": channel.sdk_version,
            "payload": {"order_id": "o_1001", "user_id": "u_1001"},
        },
        "snippet": snippets.get(platform, snippets["SERVER"]),
        "downloads": SDK_DOWNLOAD_LINKS.get(platform, {}),
    }


def _channel_to_row(channel: IngestionChannelConfig, *, include_secret: bool = False) -> dict[str, Any]:
    endpoint = f"https://{channel.endpoint_domain}{channel.endpoint_path}"
    return {
        "id": channel.id,
        "tenant_id": channel.tenant_id,
        "project_id": channel.project_id,
        "platform": channel.platform,
        "app_name": channel.app_name,
        "environment": channel.environment,
        "status": channel.status,
        "app_id": channel.app_id,
        "ingest_key": channel.ingest_key if include_secret else _mask_ingest_key(channel.ingest_key),
        "has_ingest_key": bool(channel.ingest_key),
        "endpoint_domain": channel.endpoint_domain,
        "endpoint_path": channel.endpoint_path,
        "endpoint": endpoint,
        "auth_mode": channel.auth_mode,
        "sampling_mode": channel.sampling_mode,
        "sampling_rate": channel.sampling_rate,
        "switches_payload": channel.switches_payload or {},
        "blocked_events": channel.blocked_events or [],
        "sdk_version": channel.sdk_version,
        "sdk_config_payload": channel.sdk_config_payload or {},
        "quickstart_payload": channel.quickstart_payload or {},
        "accepted_events_count": channel.accepted_events_count,
        "rejected_events_count": channel.rejected_events_count,
        "last_seen_at": _to_iso(channel.last_seen_at),
        "last_event_at": _to_iso(channel.last_event_at),
        "created_by": channel.created_by,
        "updated_by": channel.updated_by,
        "created_at": _to_iso(channel.created_at),
        "updated_at": _to_iso(channel.updated_at),
    }


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    channel_id: int | str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "INGESTION_CHANNEL",
            "entity_id": str(channel_id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


async def _open_ingestion_alert(
    db: AsyncSession,
    *,
    project_id: int,
    channel_id: int,
    title: str,
    description: str,
) -> Alert:
    source_id = f"channel:{channel_id}"
    existing_result = await db.execute(
        select(Alert).where(
            and_(
                Alert.project_id == project_id,
                Alert.source_type == "INGESTION",
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
            "source_type": "INGESTION",
            "source_id": source_id,
            "severity": "HIGH",
            "title": title[:255],
            "description": description[:1000],
            "status": "OPEN",
        }
    )

async def _within_rate_limit(
    db: AsyncSession,
    *,
    channel_id: int,
    now: datetime,
    max_per_minute: int = 1000,
) -> bool:
    result = await db.execute(
        select(IngestionEventLog)
        .where(
            IngestionEventLog.channel_id == channel_id,
            IngestionEventLog.created_at >= now - timedelta(minutes=1),
        )
        .limit(max_per_minute + 1)
    )
    rows = list(result.scalars().all())
    return len(rows) <= max_per_minute


def _should_sample(
    *,
    channel: IngestionChannelConfig,
    app_id: str,
    event_name: str,
) -> bool:
    if channel.sampling_mode == "NONE":
        return False
    if channel.sampling_mode == "ALL":
        return True
    seed = f"{channel.id}:{app_id}:{event_name}"
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    value = int(digest[:8], 16) / 0xFFFFFFFF
    return value <= float(channel.sampling_rate)


def _parse_event_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@router.get("/overview")
async def get_ingestion_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(IngestionChannelConfig).where(IngestionChannelConfig.project_id == context.project.id)
    )
    channels = list(result.scalars().all())

    now = datetime.now(timezone.utc)
    logs_result = await db.execute(
        select(IngestionEventLog).where(
            IngestionEventLog.project_id == context.project.id,
            IngestionEventLog.created_at >= now - timedelta(days=7),
        )
    )
    logs = list(logs_result.scalars().all())
    accepted_7d = len([item for item in logs if item.status == "ACCEPTED"])
    rejected_7d = len([item for item in logs if item.status == "REJECTED"])

    platform_counter = Counter(item.platform for item in channels)
    env_counter = Counter(item.environment for item in channels)

    audit_result = await db.execute(
        select(AuditLog)
        .where(and_(AuditLog.entity_type == "INGESTION_CHANNEL", build_project_audit_filter(context.project.id)))
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
                "channel_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_channels": len(channels),
                "active_channels": len([item for item in channels if item.status == "ACTIVE"]),
                "inactive_channels": len([item for item in channels if item.status == "INACTIVE"]),
                "events_7d": len(logs),
                "accepted_7d": accepted_7d,
                "rejected_7d": rejected_7d,
            },
            "platform_breakdown": [{"platform": key, "count": platform_counter[key]} for key in sorted(platform_counter.keys())],
            "environment_breakdown": [{"environment": key, "count": env_counter[key]} for key in sorted(env_counter.keys())],
            "recent_activity": recent_activity,
        }
    )


@router.get("/options")
async def get_ingestion_options(
    context: RequestContext = Depends(get_request_context),
):
    _require_user_context(context)
    return success_response(
        {
            "platforms": sorted(PLATFORMS),
            "environments": sorted(ENVIRONMENTS),
            "statuses": sorted(CHANNEL_STATUSES),
            "sampling_modes": sorted(SAMPLING_MODES),
            "default_switches": dict(DEFAULT_SWITCHES),
            "sdk_download_links": SDK_DOWNLOAD_LINKS,
        }
    )


@router.get("/channels")
async def list_ingestion_channels(
    q: str | None = Query(default=None),
    platform: str | None = Query(default=None),
    environment: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    normalized_platform = _normalize_enum(platform, allowed=PLATFORMS, field_name="platform") if platform else None
    normalized_environment = _normalize_enum(environment, allowed=ENVIRONMENTS, field_name="environment") if environment else None
    normalized_status = _normalize_enum(status_filter, allowed=CHANNEL_STATUSES, field_name="status") if status_filter else None

    query = select(IngestionChannelConfig).where(IngestionChannelConfig.project_id == context.project.id)
    if normalized_platform:
        query = query.where(IngestionChannelConfig.platform == normalized_platform)
    if normalized_environment:
        query = query.where(IngestionChannelConfig.environment == normalized_environment)
    if normalized_status:
        query = query.where(IngestionChannelConfig.status == normalized_status)

    result = await db.execute(query.order_by(IngestionChannelConfig.updated_at.desc(), IngestionChannelConfig.id.desc()))
    rows = list(result.scalars().all())

    if q and q.strip():
        keyword = q.strip().lower()
        filtered = []
        for row in rows:
            text = " ".join([row.app_name, row.app_id, row.platform, row.environment]).lower()
            if keyword in text:
                filtered.append(row)
        rows = filtered

    total = len(rows)
    page_rows = rows[offset : offset + limit]

    platform_counter = Counter(item.platform for item in rows)
    env_counter = Counter(item.environment for item in rows)
    status_counter = Counter(item.status for item in rows)

    return success_response(
        {
            "items": [_channel_to_row(item) for item in page_rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "platforms": [{"platform": key, "count": platform_counter[key]} for key in sorted(platform_counter.keys())],
                "environments": [{"environment": key, "count": env_counter[key]} for key in sorted(env_counter.keys())],
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            },
        }
    )


@router.get("/channels/{channel_id}")
async def get_ingestion_channel_detail(
    channel_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(IngestionChannelConfig).where(
            IngestionChannelConfig.id == channel_id,
            IngestionChannelConfig.project_id == context.project.id,
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    logs_result = await db.execute(
        select(IngestionEventLog)
        .where(IngestionEventLog.channel_id == channel.id)
        .order_by(IngestionEventLog.created_at.desc(), IngestionEventLog.id.desc())
        .limit(30)
    )
    logs = list(logs_result.scalars().all())

    return success_response(
        {
            "channel": _channel_to_row(channel),
            "quickstart": _build_quickstart(channel),
            "recent_events": [
                {
                    "id": item.id,
                    "request_id": item.request_id,
                    "event_name": item.event_name,
                    "status": item.status,
                    "reason_code": item.reason_code,
                    "reason_message": item.reason_message,
                    "event_ts": _to_iso(item.event_ts),
                    "source_ip": item.source_ip,
                    "sdk_version": item.sdk_version,
                    "created_at": _to_iso(item.created_at),
                }
                for item in logs
            ],
            "sdk_download_links": SDK_DOWNLOAD_LINKS.get(channel.platform, {}),
        }
    )

@router.post("/channels")
async def create_ingestion_channel(
    request: IngestionChannelCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write_role(context)

    tenant_id = _tenant_id_from_context(context)
    platform = _normalize_enum(request.platform, allowed=PLATFORMS, field_name="platform")
    environment = _normalize_enum(request.environment, allowed=ENVIRONMENTS, field_name="environment")
    status_value = _normalize_enum(request.status, allowed=CHANNEL_STATUSES, field_name="status")
    sampling_mode = _normalize_enum(request.sampling_mode, allowed=SAMPLING_MODES, field_name="sampling_mode")

    app_name = _normalize_app_name(request.app_name)
    app_id = request.app_id.strip() if request.app_id else _generate_app_id(platform, environment, app_name)

    existing_result = await db.execute(select(IngestionChannelConfig).where(IngestionChannelConfig.app_id == app_id))
    if existing_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="app_id already exists")

    endpoint_domain = request.endpoint_domain.strip() if request.endpoint_domain else "ingest.genesis.local"
    endpoint_path = request.endpoint_path.strip() if request.endpoint_path else DEFAULT_ENDPOINT_PATH
    if not endpoint_path.startswith("/"):
        endpoint_path = f"/{endpoint_path}"

    switches_payload = dict(DEFAULT_SWITCHES)
    switches_payload.update(request.switches_payload or {})
    blocked_events = [item.strip() for item in (request.blocked_events or []) if item and item.strip()]

    actor = context.user.email if context.user else parse_actor(context.actor_id)
    ingest_key = _generate_ingest_key()
    channel = await BaseRepository(IngestionChannelConfig, db).create(
        {
            "tenant_id": tenant_id,
            "project_id": context.project.id,
            "platform": platform,
            "app_name": app_name,
            "environment": environment,
            "status": status_value,
            "app_id": app_id,
            "ingest_key": ingest_key,
            "endpoint_domain": endpoint_domain,
            "endpoint_path": endpoint_path,
            "auth_mode": request.auth_mode.strip().upper(),
            "sampling_mode": sampling_mode,
            "sampling_rate": float(request.sampling_rate),
            "switches_payload": switches_payload,
            "blocked_events": blocked_events,
            "sdk_version": request.sdk_version.strip(),
            "sdk_config_payload": request.sdk_config_payload or {},
            "quickstart_payload": request.quickstart_payload or {},
            "created_by": actor,
            "updated_by": actor,
        }
    )

    await _write_audit(
        db,
        context,
        "INGESTION_CHANNEL_CREATE",
        channel.id,
        {
            "summary": "Ingestion channel created",
            "app_id": channel.app_id,
            "platform": channel.platform,
            "environment": channel.environment,
            "status": channel.status,
        },
    )

    return success_response(
        {
            "channel": _channel_to_row(channel, include_secret=True),
            "quickstart": _build_quickstart(channel),
            "generated_ingest_key": ingest_key,
        },
        message="Ingestion channel created",
        code="INGESTION_CHANNEL_CREATED",
    )


@router.patch("/channels/{channel_id}")
async def update_ingestion_channel(
    channel_id: int,
    request: IngestionChannelUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write_role(context)

    result = await db.execute(
        select(IngestionChannelConfig).where(
            IngestionChannelConfig.id == channel_id,
            IngestionChannelConfig.project_id == context.project.id,
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    patch = request.model_dump(exclude_none=True)
    if "environment" in patch:
        patch["environment"] = _normalize_enum(patch["environment"], allowed=ENVIRONMENTS, field_name="environment")
    if "status" in patch:
        patch["status"] = _normalize_enum(patch["status"], allowed=CHANNEL_STATUSES, field_name="status")
    if "sampling_mode" in patch:
        patch["sampling_mode"] = _normalize_enum(patch["sampling_mode"], allowed=SAMPLING_MODES, field_name="sampling_mode")

    if "app_name" in patch:
        patch["app_name"] = _normalize_app_name(patch["app_name"])
    if "endpoint_domain" in patch and patch["endpoint_domain"] is not None:
        patch["endpoint_domain"] = str(patch["endpoint_domain"]).strip()
    if "endpoint_path" in patch and patch["endpoint_path"] is not None:
        value = str(patch["endpoint_path"]).strip()
        patch["endpoint_path"] = value if value.startswith("/") else f"/{value}"
    if "auth_mode" in patch and patch["auth_mode"] is not None:
        patch["auth_mode"] = str(patch["auth_mode"]).strip().upper()

    if "switches_payload" in patch and patch["switches_payload"] is not None:
        switches = dict(DEFAULT_SWITCHES)
        switches.update(patch["switches_payload"])
        patch["switches_payload"] = switches
    if "blocked_events" in patch and patch["blocked_events"] is not None:
        patch["blocked_events"] = [item.strip() for item in patch["blocked_events"] if item and item.strip()]
    if "sdk_version" in patch and patch["sdk_version"] is not None:
        patch["sdk_version"] = str(patch["sdk_version"]).strip()

    actor = context.user.email if context.user else parse_actor(context.actor_id)
    patch["updated_by"] = actor
    updated = await BaseRepository(IngestionChannelConfig, db).update(channel, patch)

    await _write_audit(
        db,
        context,
        "INGESTION_CHANNEL_UPDATE",
        updated.id,
        {
            "summary": "Ingestion channel updated",
            "patched_fields": sorted(patch.keys()),
        },
    )

    return success_response(
        {
            "channel": _channel_to_row(updated),
            "quickstart": _build_quickstart(updated),
        },
        message="Ingestion channel updated",
        code="INGESTION_CHANNEL_UPDATED",
    )


@router.post("/channels/{channel_id}/rotate-key")
async def rotate_ingestion_key(
    channel_id: int,
    request: IngestionRotateKeyRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_write_role(context)

    result = await db.execute(
        select(IngestionChannelConfig).where(
            IngestionChannelConfig.id == channel_id,
            IngestionChannelConfig.project_id == context.project.id,
        )
    )
    channel = result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")

    new_key = _generate_ingest_key()
    actor = context.user.email if context.user else parse_actor(context.actor_id)
    updated = await BaseRepository(IngestionChannelConfig, db).update(
        channel,
        {
            "ingest_key": new_key,
            "updated_by": actor,
        },
    )

    await _write_audit(
        db,
        context,
        "INGESTION_CHANNEL_ROTATE_KEY",
        updated.id,
        {
            "summary": "Ingestion key rotated",
            "reason": request.reason,
        },
    )

    return success_response(
        {
            "channel": _channel_to_row(updated, include_secret=True),
            "quickstart": _build_quickstart(updated),
            "generated_ingest_key": new_key,
        },
        message="Ingestion key rotated",
        code="INGESTION_CHANNEL_KEY_ROTATED",
    )


@router.post("/gateway/events")
async def ingest_gateway_event(
    request: IngestionGatewayEventRequest,
    raw_request: Request,
    x_ingest_key: str | None = Header(default=None, alias="X-INGEST-KEY"),
    db: AsyncSession = Depends(get_async_session),
):
    if not x_ingest_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing X-INGEST-KEY")

    channel_result = await db.execute(
        select(IngestionChannelConfig).where(IngestionChannelConfig.ingest_key == x_ingest_key)
    )
    channel = channel_result.scalar_one_or_none()
    if channel is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ingest key")

    if channel.status != "ACTIVE":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Channel is inactive")

    now = datetime.now(timezone.utc)
    source_ip = raw_request.client.host if raw_request.client else None
    request_id = f"ing_{secrets.token_hex(8)}"
    event_name = request.event_name.strip()

    status_value = "ACCEPTED"
    reason_code = None
    reason_message = None

    if request.app_id.strip() != channel.app_id:
        status_value = "REJECTED"
        reason_code = "APP_ID_MISMATCH"
        reason_message = "app_id does not match ingest key"

    if status_value == "ACCEPTED" and not await _within_rate_limit(db, channel_id=channel.id, now=now):
        status_value = "REJECTED"
        reason_code = "RATE_LIMITED"
        reason_message = "request rate exceeded"

    if status_value == "ACCEPTED":
        if not re.match(r"^[a-z]+(\.[a-z0-9_]+)+$", event_name):
            status_value = "REJECTED"
            reason_code = "INVALID_EVENT_NAME"
            reason_message = "event_name must follow namespace.action format"

    blocked = {item.lower() for item in (channel.blocked_events or [])}
    if status_value == "ACCEPTED" and event_name.lower() in blocked:
        status_value = "REJECTED"
        reason_code = "BLOCKED_EVENT"
        reason_message = "event blocked by channel config"

    if status_value == "ACCEPTED" and not _should_sample(channel=channel, app_id=request.app_id.strip(), event_name=event_name):
        status_value = "SAMPLED_OUT"
        reason_code = "SAMPLED_OUT"
        reason_message = "event skipped by sampling"

    try:
        parsed_event_ts = _parse_event_ts(request.event_ts)
    except Exception:
        parsed_event_ts = None

    log_row = await BaseRepository(IngestionEventLog, db).create(
        {
            "tenant_id": channel.tenant_id,
            "project_id": channel.project_id,
            "channel_id": channel.id,
            "request_id": request_id,
            "event_name": event_name,
            "event_ts": parsed_event_ts,
            "status": status_value,
            "reason_code": reason_code,
            "reason_message": reason_message,
            "payload": request.payload or {},
            "source_ip": source_ip,
            "sdk_version": request.sdk_version,
        }
    )

    patch = {
        "last_seen_at": now,
        "last_event_at": now,
    }
    if status_value == "ACCEPTED":
        patch["accepted_events_count"] = int(channel.accepted_events_count or 0) + 1
    elif status_value == "REJECTED":
        patch["rejected_events_count"] = int(channel.rejected_events_count or 0) + 1
    updated_channel = await BaseRepository(IngestionChannelConfig, db).update(channel, patch)

    alert_id = None
    if status_value == "REJECTED":
        alert = await _open_ingestion_alert(
            db,
            project_id=channel.project_id,
            channel_id=channel.id,
            title=f"Ingestion rejected: {channel.app_id}",
            description=reason_message or "Unknown rejection",
        )
        alert_id = alert.id

    return success_response(
        {
            "request_id": request_id,
            "status": status_value,
            "reason_code": reason_code,
            "reason_message": reason_message,
            "channel": {
                "id": updated_channel.id,
                "app_id": updated_channel.app_id,
                "platform": updated_channel.platform,
                "environment": updated_channel.environment,
            },
            "event_log": {
                "id": log_row.id,
                "event_name": log_row.event_name,
                "created_at": _to_iso(log_row.created_at),
            },
            "alert_id": alert_id,
            "next_modules": ["EVENT_CATALOG", "GOVERNANCE", "DATA_QUALITY"] if status_value == "ACCEPTED" else [],
        },
        message="Ingestion gateway processed",
        code="INGESTION_GATEWAY_RESULT",
    )
