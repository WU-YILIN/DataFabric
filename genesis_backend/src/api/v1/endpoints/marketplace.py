import json
import re
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
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.models.data_product import DataProduct
from src.infrastructure.database.models.data_product_subscription import DataProductSubscription
from src.infrastructure.database.models.data_product_version import DataProductVersion
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

PRODUCT_STATUSES = {"DRAFT", "PUBLISHED", "ARCHIVED"}
PRODUCT_VISIBILITY = {"PROJECT", "PRIVATE", "ROLE_BASED"}
SUB_STATUSES = {"PENDING", "APPROVED", "REJECTED", "CANCELLED", "REVOKED"}
ROLE_SET = {"VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"}
WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR"}
APPROVER_ROLES = {"OWNER", "ADMIN", "APPROVER"}
ACTIONS = {
    "PUBLISH",
    "ARCHIVE",
    "UNARCHIVE",
    "REQUEST_SUBSCRIPTION",
    "APPROVE_SUBSCRIPTION",
    "REJECT_SUBSCRIPTION",
    "CANCEL_SUBSCRIPTION",
    "REVOKE_SUBSCRIPTION",
    "ROTATE_TOKEN",
}

DEFAULT_POLICY = {
    "visibility": "PROJECT",
    "viewer_roles": ["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"],
    "editor_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"],
}


class DataProductCreateRequest(BaseModel):
    product_key: str | None = Field(default=None, max_length=128)
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    domain: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=128)
    status: str = Field(default="DRAFT", max_length=32)
    visibility: str = Field(default="PROJECT", max_length=32)
    schema_payload: dict[str, Any] = Field(default_factory=dict)
    asset_ids: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    sla_payload: dict[str, Any] = Field(default_factory=dict)
    access_policy_payload: dict[str, Any] = Field(default_factory=dict)
    usage_payload: dict[str, Any] = Field(default_factory=dict)
    change_note: str | None = Field(default=None, max_length=1000)


class DataProductUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    domain: str | None = Field(default=None, max_length=128)
    category: str | None = Field(default=None, max_length=128)
    status: str | None = Field(default=None, max_length=32)
    visibility: str | None = Field(default=None, max_length=32)
    schema_payload: dict[str, Any] | None = None
    asset_ids: list[int] | None = None
    tags: list[str] | None = None
    sla_payload: dict[str, Any] | None = None
    access_policy_payload: dict[str, Any] | None = None
    usage_payload: dict[str, Any] | None = None
    change_note: str | None = Field(default=None, max_length=1000)


class DataProductActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=64)
    note: str | None = Field(default=None, max_length=1000)
    subscription_id: int | None = Field(default=None, ge=1)
    request_reason: str | None = Field(default=None, max_length=1000)
    expires_hours: int | None = Field(default=720, ge=1, le=24 * 365)
    usage_quota_payload: dict[str, Any] = Field(default_factory=dict)


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


def _actor(context: RequestContext) -> str:
    return context.user.email if context.user else parse_actor(context.actor_id)


def _require_user(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Marketplace API requires bearer user context")


def _require_write(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in WRITE_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (WRITE_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for marketplace mutation")


def _require_approver(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in APPROVER_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (APPROVER_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Approval permission required")


def _tenant_id(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


def _slugify(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return normalized[:96] if normalized else "product"


def _normalize_tags(tags: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tag in tags:
        item = tag.strip().lower()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item[:64])
    return out[:30]


def _normalize_access_policy(payload: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(DEFAULT_POLICY)
    base.update(payload or {})
    visibility = _normalize_enum(str(base.get("visibility") or "PROJECT"), allowed=PRODUCT_VISIBILITY, field_name="visibility")

    def _roles(value: Any) -> list[str]:
        values = value if isinstance(value, list) else []
        normalized = []
        for item in values:
            normalized.append(_normalize_enum(str(item), allowed=ROLE_SET, field_name="role"))
        return sorted(list(set(normalized)))

    return {
        "visibility": visibility,
        "viewer_roles": _roles(base.get("viewer_roles") or DEFAULT_POLICY["viewer_roles"]),
        "editor_roles": _roles(base.get("editor_roles") or DEFAULT_POLICY["editor_roles"]),
    }


def _role_set(context: RequestContext) -> set[str]:
    values: set[str] = set()
    if context.project_role:
        values.add(context.project_role.upper())
    if context.tenant_role:
        values.add(context.tenant_role.upper())
    return values


def _can_view(context: RequestContext, product: DataProduct) -> bool:
    actor = _actor(context)
    if actor == product.owner:
        return True
    policy = _normalize_access_policy(product.access_policy_payload or {})
    visibility = policy["visibility"]
    roles = _role_set(context)
    if visibility == "PROJECT":
        return True
    if visibility == "PRIVATE":
        return bool(roles & {"OWNER", "ADMIN"})
    return bool(roles & set(policy["viewer_roles"]))


def _can_edit(context: RequestContext, product: DataProduct) -> bool:
    actor = _actor(context)
    if actor == product.owner:
        return True
    policy = _normalize_access_policy(product.access_policy_payload or {})
    return bool(_role_set(context) & set(policy["editor_roles"]))


async def _validate_assets(db: AsyncSession, *, project_id: int, asset_ids: list[int]) -> list[int]:
    if not asset_ids:
        return []
    normalized = sorted(list(set(int(item) for item in asset_ids)))
    result = await db.execute(
        select(DataAsset.id).where(DataAsset.project_id == project_id, DataAsset.id.in_(normalized))
    )
    existing = {int(row[0]) for row in result.all()}
    missing = [item for item in normalized if item not in existing]
    if missing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown asset ids: {missing}")
    return normalized


def _serialize_product(context: RequestContext, product: DataProduct) -> dict[str, Any]:
    return {
        "id": product.id,
        "tenant_id": product.tenant_id,
        "project_id": product.project_id,
        "product_key": product.product_key,
        "name": product.name,
        "description": product.description,
        "domain": product.domain,
        "category": product.category,
        "owner": product.owner,
        "status": product.status,
        "visibility": product.visibility,
        "schema_payload": product.schema_payload or {},
        "asset_ids": product.asset_ids or [],
        "tags": product.tags or [],
        "sla_payload": product.sla_payload or {},
        "usage_payload": product.usage_payload or {},
        "access_policy_payload": product.access_policy_payload or {},
        "published_at": _to_iso(product.published_at),
        "created_by": product.created_by,
        "updated_by": product.updated_by,
        "created_at": _to_iso(product.created_at),
        "updated_at": _to_iso(product.updated_at),
        "capabilities": {
            "can_view": _can_view(context, product),
            "can_edit": _can_edit(context, product),
        },
    }


def _serialize_version(item: DataProductVersion) -> dict[str, Any]:
    return {
        "id": item.id,
        "product_id": item.product_id,
        "version_no": item.version_no,
        "change_note": item.change_note,
        "snapshot_payload": item.snapshot_payload or {},
        "created_by": item.created_by,
        "created_at": _to_iso(item.created_at),
    }


def _serialize_subscription(item: DataProductSubscription) -> dict[str, Any]:
    token = item.access_token
    masked = None
    if token:
        masked = token if len(token) <= 12 else f"{token[:8]}***{token[-4:]}"
    return {
        "id": item.id,
        "product_id": item.product_id,
        "subscriber": item.subscriber,
        "request_reason": item.request_reason,
        "status": item.status,
        "decision_note": item.decision_note,
        "approved_by": item.approved_by,
        "rejected_by": item.rejected_by,
        "access_token": masked,
        "expires_at": _to_iso(item.expires_at),
        "usage_quota_payload": item.usage_quota_payload or {},
        "last_used_at": _to_iso(item.last_used_at),
        "created_at": _to_iso(item.created_at),
        "updated_at": _to_iso(item.updated_at),
    }


def _snapshot(product: DataProduct) -> dict[str, Any]:
    return {
        "product_key": product.product_key,
        "name": product.name,
        "description": product.description,
        "domain": product.domain,
        "category": product.category,
        "owner": product.owner,
        "status": product.status,
        "visibility": product.visibility,
        "schema_payload": product.schema_payload or {},
        "asset_ids": product.asset_ids or [],
        "tags": product.tags or [],
        "sla_payload": product.sla_payload or {},
        "usage_payload": product.usage_payload or {},
        "access_policy_payload": product.access_policy_payload or {},
    }


async def _create_version(db: AsyncSession, product: DataProduct, *, actor: str, note: str | None) -> None:
    latest_result = await db.execute(
        select(DataProductVersion)
        .where(DataProductVersion.product_id == product.id)
        .order_by(DataProductVersion.version_no.desc())
        .limit(1)
    )
    latest = latest_result.scalar_one_or_none()
    version_no = 1 if latest is None else int(latest.version_no) + 1
    await BaseRepository(DataProductVersion, db).create(
        {
            "product_id": product.id,
            "project_id": product.project_id,
            "version_no": version_no,
            "change_note": note,
            "snapshot_payload": _snapshot(product),
            "created_by": actor,
        }
    )


async def _write_audit(db: AsyncSession, context: RequestContext, action: str, product_id: int | str, details: dict[str, Any]) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "DATA_PRODUCT",
            "entity_id": str(product_id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


@router.get("/overview")
async def get_marketplace_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    rows = list((await db.execute(select(DataProduct).where(DataProduct.project_id == context.project.id))).scalars().all())
    rows = [item for item in rows if _can_view(context, item)]
    status_counter = Counter(item.status for item in rows)
    domain_counter = Counter(item.domain or "UNSET" for item in rows)

    subs = list(
        (
            await db.execute(
                select(DataProductSubscription).where(DataProductSubscription.project_id == context.project.id)
            )
        ).scalars().all()
    )
    sub_counter = Counter(item.status for item in subs)

    recent = list(
        (
            await db.execute(
                select(AuditLog)
                .where(and_(AuditLog.entity_type == "DATA_PRODUCT", build_project_audit_filter(context.project.id)))
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
                "product_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_products": len(rows),
                "draft_products": status_counter.get("DRAFT", 0),
                "published_products": status_counter.get("PUBLISHED", 0),
                "archived_products": status_counter.get("ARCHIVED", 0),
                "pending_subscriptions": sub_counter.get("PENDING", 0),
                "approved_subscriptions": sub_counter.get("APPROVED", 0),
                "rejected_subscriptions": sub_counter.get("REJECTED", 0),
            },
            "status_distribution": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            "domain_distribution": [{"domain": key, "count": domain_counter[key]} for key in sorted(domain_counter.keys())],
            "subscription_distribution": [{"status": key, "count": sub_counter[key]} for key in sorted(sub_counter.keys())],
            "recent_activity": recent_activity,
        }
    )


@router.get("/products")
async def list_products(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    visibility: str | None = Query(default=None),
    owner: str | None = Query(default=None),
    domain: str | None = Query(default=None),
    tag: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    normalized_status = _normalize_enum(status_filter, allowed=PRODUCT_STATUSES, field_name="status") if status_filter else None
    normalized_visibility = _normalize_enum(visibility, allowed=PRODUCT_VISIBILITY, field_name="visibility") if visibility else None
    owner_filter = owner.strip().lower() if owner else None
    domain_filter = domain.strip().lower() if domain else None
    tag_filter = tag.strip().lower() if tag else None

    rows = list(
        (
            await db.execute(
                select(DataProduct)
                .where(DataProduct.project_id == context.project.id)
                .order_by(DataProduct.updated_at.desc(), DataProduct.id.desc())
            )
        ).scalars().all()
    )
    rows = [item for item in rows if _can_view(context, item)]
    if normalized_status:
        rows = [item for item in rows if item.status == normalized_status]
    if normalized_visibility:
        rows = [item for item in rows if item.visibility == normalized_visibility]
    if owner_filter:
        rows = [item for item in rows if owner_filter in item.owner.lower()]
    if domain_filter:
        rows = [item for item in rows if domain_filter in (item.domain or "").lower()]
    if tag_filter:
        rows = [item for item in rows if tag_filter in (item.tags or [])]
    if q and q.strip():
        keyword = q.strip().lower()
        filtered = []
        for item in rows:
            text = " ".join(
                [
                    item.product_key,
                    item.name,
                    item.description or "",
                    item.owner,
                    item.domain or "",
                    item.category or "",
                    " ".join(item.tags or []),
                ]
            ).lower()
            if keyword in text:
                filtered.append(item)
        rows = filtered

    total = len(rows)
    page_rows = rows[offset : offset + limit]
    status_counter = Counter(item.status for item in rows)
    owner_counter = Counter(item.owner for item in rows)
    domain_counter = Counter(item.domain or "UNSET" for item in rows)
    tag_counter: Counter[str] = Counter()
    for item in rows:
        for row_tag in item.tags or []:
            tag_counter[row_tag] += 1

    return success_response(
        {
            "items": [_serialize_product(context, item) for item in page_rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
                "owners": [{"owner": key, "count": owner_counter[key]} for key in sorted(owner_counter.keys())],
                "domains": [{"domain": key, "count": domain_counter[key]} for key in sorted(domain_counter.keys())],
                "tags": [{"tag": key, "count": tag_counter[key]} for key in sorted(tag_counter.keys())],
            },
        }
    )


@router.get("/products/{product_id}")
async def get_product_detail(
    product_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    result = await db.execute(
        select(DataProduct).where(DataProduct.id == product_id, DataProduct.project_id == context.project.id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if not _can_view(context, product):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to view this product")

    versions = list(
        (
            await db.execute(
                select(DataProductVersion)
                .where(DataProductVersion.product_id == product.id)
                .order_by(DataProductVersion.version_no.desc(), DataProductVersion.id.desc())
                .limit(20)
            )
        ).scalars().all()
    )
    all_subs = list(
        (
            await db.execute(
                select(DataProductSubscription)
                .where(DataProductSubscription.product_id == product.id)
                .order_by(DataProductSubscription.created_at.desc(), DataProductSubscription.id.desc())
            )
        ).scalars().all()
    )
    actor = _actor(context)
    roles = _role_set(context)
    if actor != product.owner and not (roles & {"OWNER", "ADMIN", "APPROVER"}):
        all_subs = [item for item in all_subs if item.subscriber == actor]
    sub_counter = Counter(item.status for item in all_subs)

    return success_response(
        {
            "product": _serialize_product(context, product),
            "versions": [_serialize_version(item) for item in versions],
            "subscriptions": [_serialize_subscription(item) for item in all_subs],
            "usage_summary": {
                "subscription_total": len(all_subs),
                "pending": sub_counter.get("PENDING", 0),
                "approved": sub_counter.get("APPROVED", 0),
                "rejected": sub_counter.get("REJECTED", 0),
                "active_tokens": len([item for item in all_subs if item.status == "APPROVED" and item.access_token]),
            },
        }
    )


@router.post("/products")
async def create_product(
    request: DataProductCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    _require_write(context)
    status_value = _normalize_enum(request.status, allowed=PRODUCT_STATUSES, field_name="status")
    visibility = _normalize_enum(request.visibility, allowed=PRODUCT_VISIBILITY, field_name="visibility")
    if status_value == "PUBLISHED":
        _require_approver(context)

    key = request.product_key.strip().lower() if request.product_key else f"{_slugify(request.name)}_{secrets.token_hex(3)}"
    exists = await db.execute(select(DataProduct).where(DataProduct.product_key == key))
    if exists.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="product_key already exists")

    actor = _actor(context)
    assets = await _validate_assets(db, project_id=context.project.id, asset_ids=request.asset_ids)
    access_policy = _normalize_access_policy(
        {
            **(request.access_policy_payload or {}),
            "visibility": visibility,
        }
    )
    item = await BaseRepository(DataProduct, db).create(
        {
            "tenant_id": _tenant_id(context),
            "project_id": context.project.id,
            "product_key": key,
            "name": request.name.strip(),
            "description": request.description.strip() if request.description else None,
            "domain": request.domain.strip().lower() if request.domain else None,
            "category": request.category.strip().lower() if request.category else None,
            "owner": actor,
            "status": status_value,
            "visibility": visibility,
            "schema_payload": request.schema_payload or {},
            "asset_ids": assets,
            "tags": _normalize_tags(request.tags or []),
            "sla_payload": request.sla_payload or {},
            "usage_payload": request.usage_payload or {},
            "access_policy_payload": access_policy,
            "published_at": datetime.now(timezone.utc) if status_value == "PUBLISHED" else None,
            "created_by": actor,
            "updated_by": actor,
        }
    )
    await _create_version(db, item, actor=actor, note=request.change_note or "Initial version")
    await _write_audit(
        db,
        context,
        "DATA_PRODUCT_CREATE",
        item.id,
        {"summary": "Data product created", "product_key": item.product_key, "status": item.status},
    )
    return success_response(_serialize_product(context, item), message="Data product created", code="DATA_PRODUCT_CREATED")


@router.patch("/products/{product_id}")
async def update_product(
    product_id: int,
    request: DataProductUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    _require_write(context)
    result = await db.execute(
        select(DataProduct).where(DataProduct.id == product_id, DataProduct.project_id == context.project.id)
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if not _can_edit(context, item):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to edit product")

    patch = request.model_dump(exclude_none=True)
    if not patch:
        return success_response(_serialize_product(context, item), message="No changes", code="DATA_PRODUCT_NO_CHANGES")

    if "status" in patch:
        patch["status"] = _normalize_enum(patch["status"], allowed=PRODUCT_STATUSES, field_name="status")
        if patch["status"] == "PUBLISHED":
            _require_approver(context)
            patch["published_at"] = datetime.now(timezone.utc)
    if "visibility" in patch:
        patch["visibility"] = _normalize_enum(patch["visibility"], allowed=PRODUCT_VISIBILITY, field_name="visibility")
    if "asset_ids" in patch:
        patch["asset_ids"] = await _validate_assets(db, project_id=context.project.id, asset_ids=patch["asset_ids"])
    if "tags" in patch:
        patch["tags"] = _normalize_tags(patch["tags"])
    if "domain" in patch and patch["domain"] is not None:
        patch["domain"] = str(patch["domain"]).strip().lower() or None
    if "category" in patch and patch["category"] is not None:
        patch["category"] = str(patch["category"]).strip().lower() or None
    if "name" in patch:
        patch["name"] = str(patch["name"]).strip()
        if len(patch["name"]) < 2:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name too short")
    if "description" in patch and patch["description"] is not None:
        patch["description"] = str(patch["description"]).strip()
    if "access_policy_payload" in patch:
        merged = dict(item.access_policy_payload or {})
        merged.update(patch["access_policy_payload"] or {})
        if "visibility" in patch:
            merged["visibility"] = patch["visibility"]
        patch["access_policy_payload"] = _normalize_access_policy(merged)

    patch["updated_by"] = _actor(context)
    updated = await BaseRepository(DataProduct, db).update(item, patch)
    await _create_version(db, updated, actor=patch["updated_by"], note=request.change_note or "Product updated")
    await _write_audit(
        db,
        context,
        "DATA_PRODUCT_UPDATE",
        updated.id,
        {"summary": "Data product updated", "patched_fields": sorted(list(patch.keys()))},
    )
    return success_response(_serialize_product(context, updated), message="Data product updated", code="DATA_PRODUCT_UPDATED")


@router.post("/products/{product_id}/actions")
async def operate_product(
    product_id: int,
    request: DataProductActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user(context)
    action = _normalize_enum(request.action, allowed=ACTIONS, field_name="action")
    result = await db.execute(
        select(DataProduct).where(DataProduct.id == product_id, DataProduct.project_id == context.project.id)
    )
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if not _can_view(context, product):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission for product")

    actor = _actor(context)
    note = request.note.strip() if request.note else None

    if action in {"PUBLISH", "ARCHIVE", "UNARCHIVE"}:
        _require_approver(context)
        if not _can_edit(context, product):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to change product status")
        if action == "PUBLISH":
            patch, audit_action = {"status": "PUBLISHED", "published_at": datetime.now(timezone.utc), "updated_by": actor}, "DATA_PRODUCT_PUBLISH"
        elif action == "ARCHIVE":
            patch, audit_action = {"status": "ARCHIVED", "updated_by": actor}, "DATA_PRODUCT_ARCHIVE"
        else:
            patch, audit_action = {"status": "DRAFT", "updated_by": actor}, "DATA_PRODUCT_UNARCHIVE"
        updated = await BaseRepository(DataProduct, db).update(product, patch)
        await _create_version(db, updated, actor=actor, note=note or f"Action {action}")
        await _write_audit(db, context, audit_action, updated.id, {"summary": f"Product {action.lower()}", "status": updated.status})
        return success_response({"product": _serialize_product(context, updated)}, message="Action applied", code="DATA_PRODUCT_ACTION_APPLIED")

    sub_query = select(DataProductSubscription).where(DataProductSubscription.product_id == product.id)
    if request.subscription_id is not None:
        sub_query = sub_query.where(DataProductSubscription.id == request.subscription_id)
    sub_query = sub_query.order_by(DataProductSubscription.created_at.desc(), DataProductSubscription.id.desc())
    sub_item = (await db.execute(sub_query)).scalars().first()

    if action == "REQUEST_SUBSCRIPTION":
        if product.status != "PUBLISHED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only published product can be subscribed")
        existing_pending = await db.execute(
            select(DataProductSubscription).where(
                DataProductSubscription.product_id == product.id,
                DataProductSubscription.subscriber == actor,
                DataProductSubscription.status.in_(["PENDING", "APPROVED"]),
            )
        )
        existing = existing_pending.scalars().first()
        if existing and existing.status == "PENDING":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Subscription request already pending")
        if existing and existing.status == "APPROVED":
            return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(existing)}, message="Already subscribed", code="DATA_PRODUCT_ALREADY_SUBSCRIBED")
        created = await BaseRepository(DataProductSubscription, db).create(
            {
                "product_id": product.id,
                "project_id": product.project_id,
                "subscriber": actor,
                "request_reason": request.request_reason,
                "status": "PENDING",
                "decision_note": note,
                "usage_quota_payload": request.usage_quota_payload or {},
            }
        )
        await _write_audit(db, context, "DATA_PRODUCT_SUB_REQUEST", product.id, {"summary": "Subscription requested", "subscription_id": created.id, "subscriber": actor})
        return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(created)}, message="Subscription requested", code="DATA_PRODUCT_SUB_REQUESTED")

    if action in {"APPROVE_SUBSCRIPTION", "REJECT_SUBSCRIPTION", "REVOKE_SUBSCRIPTION", "ROTATE_TOKEN"}:
        _require_approver(context)
        if sub_item is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")

        if action == "APPROVE_SUBSCRIPTION":
            if sub_item.status != "PENDING":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending subscription can be approved")
            token = f"dpsub_{secrets.token_urlsafe(20)}"
            expires_at = datetime.now(timezone.utc) + timedelta(hours=int(request.expires_hours or 720))
            updated_sub = await BaseRepository(DataProductSubscription, db).update(
                sub_item,
                {
                    "status": "APPROVED",
                    "approved_by": actor,
                    "rejected_by": None,
                    "decision_note": note,
                    "access_token": token,
                    "expires_at": expires_at,
                    "usage_quota_payload": request.usage_quota_payload or sub_item.usage_quota_payload or {},
                },
            )
            await _write_audit(db, context, "DATA_PRODUCT_SUB_APPROVE", product.id, {"summary": "Subscription approved", "subscription_id": updated_sub.id, "subscriber": updated_sub.subscriber})
            return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(updated_sub)}, message="Subscription approved", code="DATA_PRODUCT_SUB_APPROVED")

        if action == "REJECT_SUBSCRIPTION":
            if sub_item.status != "PENDING":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending subscription can be rejected")
            updated_sub = await BaseRepository(DataProductSubscription, db).update(
                sub_item,
                {
                    "status": "REJECTED",
                    "rejected_by": actor,
                    "decision_note": note,
                },
            )
            await _write_audit(db, context, "DATA_PRODUCT_SUB_REJECT", product.id, {"summary": "Subscription rejected", "subscription_id": updated_sub.id})
            return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(updated_sub)}, message="Subscription rejected", code="DATA_PRODUCT_SUB_REJECTED")

        if action == "REVOKE_SUBSCRIPTION":
            if sub_item.status != "APPROVED":
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved subscription can be revoked")
            updated_sub = await BaseRepository(DataProductSubscription, db).update(
                sub_item,
                {
                    "status": "REVOKED",
                    "decision_note": note,
                    "access_token": None,
                },
            )
            await _write_audit(db, context, "DATA_PRODUCT_SUB_REVOKE", product.id, {"summary": "Subscription revoked", "subscription_id": updated_sub.id})
            return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(updated_sub)}, message="Subscription revoked", code="DATA_PRODUCT_SUB_REVOKED")

        if sub_item.status != "APPROVED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only approved subscription token can be rotated")
        token = f"dpsub_{secrets.token_urlsafe(20)}"
        updated_sub = await BaseRepository(DataProductSubscription, db).update(
            sub_item,
            {
                "access_token": token,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=int(request.expires_hours or 720)),
                "decision_note": note,
            },
        )
        await _write_audit(db, context, "DATA_PRODUCT_SUB_ROTATE_TOKEN", product.id, {"summary": "Subscription token rotated", "subscription_id": updated_sub.id})
        return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(updated_sub)}, message="Subscription token rotated", code="DATA_PRODUCT_SUB_TOKEN_ROTATED")

    # CANCEL_SUBSCRIPTION
    if sub_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscription not found")
    if sub_item.status != "PENDING":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only pending subscription can be cancelled")
    can_cancel = sub_item.subscriber == actor or actor == product.owner or bool(_role_set(context) & {"OWNER", "ADMIN"})
    if not can_cancel:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No permission to cancel subscription")
    updated_sub = await BaseRepository(DataProductSubscription, db).update(
        sub_item,
        {
            "status": "CANCELLED",
            "decision_note": note,
        },
    )
    await _write_audit(db, context, "DATA_PRODUCT_SUB_CANCEL", product.id, {"summary": "Subscription cancelled", "subscription_id": updated_sub.id})
    return success_response({"product": _serialize_product(context, product), "subscription": _serialize_subscription(updated_sub)}, message="Subscription cancelled", code="DATA_PRODUCT_SUB_CANCELLED")
