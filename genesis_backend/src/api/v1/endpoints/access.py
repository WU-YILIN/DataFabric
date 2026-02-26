import json
import secrets
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.project_member_invitation import ProjectMemberInvitation
from src.infrastructure.database.models.role_template_policy import RoleTemplatePolicy
from src.infrastructure.database.models.user import User, UserProjectRole, UserTenantRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ACCESS_ADMIN_ROLES = {"OWNER", "ADMIN"}
TENANT_ROLE_VALUES = {"OWNER", "ADMIN", "MEMBER"}
PROJECT_ROLE_VALUES = {"OWNER", "ADMIN", "APPROVER", "EDITOR", "VIEWER"}
INVITABLE_PROJECT_ROLES = {"ADMIN", "APPROVER", "EDITOR", "VIEWER"}
PROJECT_ROLE_MANAGE_ACTIONS = {"UPSERT", "REMOVE"}
TENANT_ROLE_MANAGE_ACTIONS = {"UPSERT", "REMOVE"}

SECURITY_AUDIT_ACTIONS = {
    "ACCESS_USER_INVITE",
    "ACCESS_USER_ROLE_UPDATE",
    "ACCESS_USER_STATUS_UPDATE",
    "ACCESS_ROLE_TEMPLATE_SAVE",
    "ACCESS_ROLE_TEMPLATE_DELETE",
}

SYSTEM_ROLE_TEMPLATES: dict[str, dict[str, Any]] = {
    "VIEWER": {
        "name": "只读",
        "description": "可查看各模块信息，不允许变更和执行高风险动作。",
        "permission_matrix": {
            "modules": {
                "OVERVIEW": ["VIEW"],
                "GOVERNANCE": ["VIEW"],
                "EVENTS": ["VIEW"],
                "DATA_CATALOG": ["VIEW"],
                "DATA_QUALITY": ["VIEW"],
                "EXPLORE": ["VIEW"],
                "INFRASTRUCTURE": ["VIEW"],
                "MONITORING": ["VIEW"],
                "COLLABORATION": ["VIEW"],
                "KNOWLEDGE": ["VIEW"],
                "COST": ["VIEW"],
                "SANDBOX": ["VIEW"],
                "SCHEDULER": ["VIEW"],
                "PIPELINES": ["VIEW"],
                "AUDIT_LOGS": ["VIEW"],
                "INTEGRATION_HUB": ["VIEW"],
            }
        },
    },
    "EDITOR": {
        "name": "数据工程师",
        "description": "可维护数据对象与流程，但不负责最终审批。",
        "permission_matrix": {
            "modules": {
                "OVERVIEW": ["VIEW"],
                "EVENTS": ["VIEW", "CREATE", "UPDATE"],
                "DATA_CATALOG": ["VIEW", "CREATE", "UPDATE"],
                "DATA_QUALITY": ["VIEW", "CREATE", "UPDATE", "OPERATE"],
                "EXPLORE": ["VIEW", "OPERATE"],
                "INFRASTRUCTURE": ["VIEW"],
                "SCHEDULER": ["VIEW", "CREATE", "UPDATE", "OPERATE"],
                "PIPELINES": ["VIEW", "CREATE", "UPDATE", "OPERATE"],
                "KNOWLEDGE": ["VIEW", "CREATE", "UPDATE"],
                "COLLABORATION": ["VIEW", "CREATE", "UPDATE"],
                "INTEGRATION_HUB": ["VIEW", "INVOKE"],
            }
        },
    },
    "APPROVER": {
        "name": "治理专员",
        "description": "具备审批类操作能力，聚焦治理、告警和协作流程。",
        "permission_matrix": {
            "modules": {
                "OVERVIEW": ["VIEW"],
                "GOVERNANCE": ["VIEW", "APPROVE"],
                "MONITORING": ["VIEW", "OPERATE"],
                "COLLABORATION": ["VIEW", "APPROVE", "REJECT", "REQUEST_REVISION"],
                "KNOWLEDGE": ["VIEW", "UPDATE", "PUBLISH"],
                "AUDIT_LOGS": ["VIEW"],
                "SETTINGS": ["VIEW"],
                "INTEGRATION_HUB": ["VIEW"],
            }
        },
    },
    "ADMIN": {
        "name": "平台管理员",
        "description": "可管理项目成员、配置、集成与大部分模块动作。",
        "permission_matrix": {
            "modules": {
                "OVERVIEW": ["*"],
                "GOVERNANCE": ["*"],
                "EVENTS": ["*"],
                "DATA_CATALOG": ["*"],
                "DATA_QUALITY": ["*"],
                "EXPLORE": ["*"],
                "INFRASTRUCTURE": ["*"],
                "MONITORING": ["*"],
                "COLLABORATION": ["*"],
                "KNOWLEDGE": ["*"],
                "COST": ["*"],
                "SANDBOX": ["*"],
                "SCHEDULER": ["*"],
                "PIPELINES": ["*"],
                "AUDIT_LOGS": ["VIEW", "EXPORT"],
                "SETTINGS": ["*"],
                "INTEGRATION_HUB": ["*"],
                "ACCESS_MANAGEMENT": ["*"],
            }
        },
    },
    "OWNER": {
        "name": "租户所有者",
        "description": "最高权限角色，拥有跨模块和安全策略最终控制权。",
        "permission_matrix": {
            "modules": {
                "*": ["*"],
            }
        },
    },
}


class AccessInviteRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    tenant_id: int | None = Field(default=None, ge=1)
    project_id: int | None = Field(default=None, ge=1)
    tenant_role: str = Field(default="MEMBER", min_length=3, max_length=64)
    project_role: str = Field(default="VIEWER", min_length=3, max_length=64)
    expires_in_hours: int = Field(default=168, ge=1, le=24 * 30)


class AccessProjectRolePatch(BaseModel):
    project_id: int = Field(..., ge=1)
    action: str = Field(default="UPSERT", min_length=3, max_length=16)
    role: str | None = Field(default=None, min_length=3, max_length=64)


class AccessRolesUpdateRequest(BaseModel):
    tenant_role_action: str = Field(default="UPSERT", min_length=3, max_length=16)
    tenant_role: str | None = Field(default=None, min_length=3, max_length=64)
    project_roles: list[AccessProjectRolePatch] = Field(default_factory=list)


class AccessStatusUpdateRequest(BaseModel):
    is_active: bool


class AccessRoleTemplateUpsertRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    permission_matrix: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class AccessEvaluateRequest(BaseModel):
    user_id: int = Field(..., ge=1)
    module: str = Field(..., min_length=2, max_length=128)
    action: str = Field(..., min_length=2, max_length=64)
    project_id: int | None = Field(default=None, ge=1)


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
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _role_rank(role: str | None) -> int:
    order = {
        "OWNER": 6,
        "ADMIN": 5,
        "APPROVER": 4,
        "EDITOR": 3,
        "VIEWER": 2,
        "MEMBER": 1,
    }
    return order.get((role or "").upper(), 0)


def _highest_role(roles: list[str]) -> str | None:
    if not roles:
        return None
    return sorted(roles, key=lambda item: _role_rank(item), reverse=True)[0]


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
    return normalized


def _normalize_tenant_role(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in TENANT_ROLE_VALUES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported tenant role: {value}")
    return normalized


def _normalize_project_role(value: str, *, allow_owner: bool) -> str:
    normalized = value.strip().upper()
    allowed_values = PROJECT_ROLE_VALUES if allow_owner else INVITABLE_PROJECT_ROLES
    if normalized not in allowed_values:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported project role: {value}")
    return normalized


def _normalize_manage_action(value: str, allowed: set[str], *, field_name: str) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported {field_name}: {value}")
    return normalized


def _normalize_permission_matrix(raw: dict[str, Any]) -> dict[str, Any]:
    modules_raw = raw.get("modules")
    if not isinstance(modules_raw, dict) or not modules_raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="permission_matrix.modules must be non-empty object")
    normalized_modules: dict[str, list[str]] = {}
    for module, actions in modules_raw.items():
        module_key = str(module).strip().upper()
        if not module_key:
            continue
        if not isinstance(actions, list):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"module {module_key} actions must be list")
        normalized_actions: list[str] = []
        for action in actions:
            action_key = str(action).strip().upper()
            if not action_key:
                continue
            if action_key not in normalized_actions:
                normalized_actions.append(action_key)
        if not normalized_actions:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"module {module_key} requires at least one action")
        normalized_modules[module_key] = normalized_actions
    if not normalized_modules:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="permission_matrix.modules must not be empty")
    return {"modules": normalized_modules}


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access API requires bearer user context")


def _require_access_admin(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in ACCESS_ADMIN_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for access management")


def _tenant_id_from_context(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


async def _resolve_target_project(
    db: AsyncSession,
    *,
    context_tenant_id: int,
    requested_tenant_id: int | None,
    requested_project_id: int | None,
    default_project_id: int,
) -> tuple[int, Project]:
    tenant_id = requested_tenant_id or context_tenant_id
    if tenant_id != context_tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cross-tenant access is not allowed")
    project_id = requested_project_id or default_project_id
    project_result = await db.execute(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    project = project_result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return tenant_id, project


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    entity_type: str,
    entity_id: str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


async def _load_tenant_user_maps(
    db: AsyncSession,
    tenant_id: int,
) -> tuple[
    dict[int, User],
    dict[int, list[dict[str, Any]]],
    dict[int, list[dict[str, Any]]],
]:
    users: dict[int, User] = {}
    tenant_roles: dict[int, list[dict[str, Any]]] = defaultdict(list)
    project_roles: dict[int, list[dict[str, Any]]] = defaultdict(list)

    tenant_role_result = await db.execute(
        select(User, UserTenantRole)
        .join(UserTenantRole, UserTenantRole.user_id == User.id)
        .where(UserTenantRole.tenant_id == tenant_id)
    )
    for user, role in tenant_role_result.all():
        users[user.id] = user
        tenant_roles[user.id].append(
            {
                "id": role.id,
                "tenant_id": role.tenant_id,
                "role": role.role,
                "updated_at": _to_iso(role.updated_at),
            }
        )

    project_role_result = await db.execute(
        select(User, UserProjectRole, Project)
        .join(UserProjectRole, UserProjectRole.user_id == User.id)
        .join(Project, Project.id == UserProjectRole.project_id)
        .where(Project.tenant_id == tenant_id)
    )
    for user, role, project in project_role_result.all():
        users[user.id] = user
        project_roles[user.id].append(
            {
                "id": role.id,
                "project_id": role.project_id,
                "project_name": project.name,
                "role": role.role,
                "updated_at": _to_iso(role.updated_at),
            }
        )

    for items in project_roles.values():
        items.sort(key=lambda item: (-_role_rank(item["role"]), item["project_name"]))
    for items in tenant_roles.values():
        items.sort(key=lambda item: (-_role_rank(item["role"]), item["tenant_id"]))
    return users, tenant_roles, project_roles


def _serialize_user_item(
    user: User,
    *,
    tenant_roles: list[dict[str, Any]],
    project_roles: list[dict[str, Any]],
) -> dict[str, Any]:
    role_candidates = [item["role"] for item in tenant_roles] + [item["role"] for item in project_roles]
    highest = _highest_role(role_candidates)
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "status": "ACTIVE" if user.is_active else "INACTIVE",
        "organization": "default",
        "last_login_at": None,
        "highest_role": highest,
        "tenant_roles": tenant_roles,
        "project_roles": project_roles,
        "auth_provider": user.auth_provider,
        "created_at": _to_iso(user.created_at),
        "updated_at": _to_iso(user.updated_at),
    }

async def _load_effective_role_templates(
    db: AsyncSession,
    tenant_id: int,
) -> dict[str, dict[str, Any]]:
    templates = deepcopy(SYSTEM_ROLE_TEMPLATES)
    result = await db.execute(
        select(RoleTemplatePolicy)
        .where(RoleTemplatePolicy.tenant_id == tenant_id)
        .order_by(RoleTemplatePolicy.template_key.asc())
    )
    for row in result.scalars().all():
        templates[row.template_key] = {
            "name": row.name,
            "description": row.description,
            "permission_matrix": row.permission_matrix,
            "is_active": row.is_active,
            "is_system": row.is_system,
            "template_id": row.id,
            "updated_at": _to_iso(row.updated_at),
            "source": "TENANT_OVERRIDE" if row.template_key in SYSTEM_ROLE_TEMPLATES else "TENANT_CUSTOM",
        }

    for key, value in templates.items():
        value.setdefault("is_active", True)
        value.setdefault("is_system", key in SYSTEM_ROLE_TEMPLATES)
        value.setdefault("template_id", None)
        value.setdefault("updated_at", None)
        value.setdefault("source", "SYSTEM")
    return templates


def _matrix_match(template: dict[str, Any], module: str, action: str) -> bool:
    matrix = template.get("permission_matrix") or {}
    modules = matrix.get("modules") if isinstance(matrix, dict) else None
    if not isinstance(modules, dict):
        return False
    module_actions = modules.get(module, [])
    wildcard_module_actions = modules.get("*", [])
    if "*" in module_actions or action in module_actions:
        return True
    if "*" in wildcard_module_actions or action in wildcard_module_actions:
        return True
    return False


def _match_effective_role_for_scope(
    *,
    tenant_roles: list[dict[str, Any]],
    project_roles: list[dict[str, Any]],
    project_id: int | None,
) -> str | None:
    if project_id is not None:
        target_project_role = next((item["role"] for item in project_roles if item["project_id"] == project_id), None)
        if target_project_role:
            return target_project_role.upper()
    role_candidates = [item["role"] for item in project_roles] + [item["role"] for item in tenant_roles]
    role = _highest_role(role_candidates)
    return role.upper() if role else None


@router.get("/overview")
async def get_access_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)

    users, tenant_roles_map, project_roles_map = await _load_tenant_user_maps(db, tenant_id)
    serialized_users = [
        _serialize_user_item(
            user,
            tenant_roles=tenant_roles_map.get(user_id, []),
            project_roles=project_roles_map.get(user_id, []),
        )
        for user_id, user in users.items()
    ]

    role_counter = Counter(item["highest_role"] or "UNASSIGNED" for item in serialized_users)
    status_counter = Counter(item["status"] for item in serialized_users)

    now = datetime.now(timezone.utc)
    expired_cleanup = await db.execute(
        delete(ProjectMemberInvitation).where(
            ProjectMemberInvitation.tenant_id == tenant_id,
            ProjectMemberInvitation.status == "PENDING",
            ProjectMemberInvitation.expires_at < now,
        )
    )
    if expired_cleanup.rowcount:
        await db.flush()

    invitation_result = await db.execute(
        select(ProjectMemberInvitation).where(
            ProjectMemberInvitation.tenant_id == tenant_id,
            ProjectMemberInvitation.status == "PENDING",
        )
    )
    pending_invitations = list(invitation_result.scalars().all())

    templates = await _load_effective_role_templates(db, tenant_id)
    audit_result = await db.execute(
        select(AuditLog)
        .where(and_(build_project_audit_filter(context.project.id), AuditLog.action.in_(SECURITY_AUDIT_ACTIONS)))
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(20)
    )
    recent_security_activity = []
    for row in audit_result.scalars().all():
        details = _safe_json_loads(row.details)
        recent_security_activity.append(
            {
                "id": row.id,
                "timestamp": _to_iso(row.timestamp),
                "actor": parse_actor(row.user_id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_users": len(serialized_users),
                "active_users": status_counter.get("ACTIVE", 0),
                "inactive_users": status_counter.get("INACTIVE", 0),
                "pending_invitations": len(pending_invitations),
                "admin_users": role_counter.get("ADMIN", 0) + role_counter.get("OWNER", 0),
                "role_templates": len(templates),
            },
            "role_distribution": [{"role": key, "count": role_counter[key]} for key in sorted(role_counter.keys())],
            "status_distribution": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            "recent_security_activity": recent_security_activity,
        }
    )


@router.get("/users")
async def list_access_users(
    q: str | None = Query(default=None),
    role: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    project_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)

    normalized_role = role.strip().upper() if role else None
    normalized_status = status_filter.strip().upper() if status_filter else None
    if normalized_status and normalized_status not in {"ACTIVE", "INACTIVE"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported status: {status_filter}")

    if project_id is not None:
        project_result = await db.execute(
            select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
        )
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    users, tenant_roles_map, project_roles_map = await _load_tenant_user_maps(db, tenant_id)
    all_rows: list[dict[str, Any]] = []
    for user_id, user in users.items():
        row = _serialize_user_item(
            user,
            tenant_roles=tenant_roles_map.get(user_id, []),
            project_roles=project_roles_map.get(user_id, []),
        )

        if normalized_status and row["status"] != normalized_status:
            continue
        if normalized_role:
            role_values = [item["role"] for item in row["tenant_roles"]] + [item["role"] for item in row["project_roles"]]
            if normalized_role not in {item.upper() for item in role_values}:
                continue
        if project_id is not None and not any(item["project_id"] == project_id for item in row["project_roles"]):
            continue
        if q:
            keyword = q.strip().lower()
            if keyword:
                role_text = " ".join(item["role"] for item in row["tenant_roles"] + row["project_roles"]).lower()
                if keyword not in row["email"].lower() and keyword not in row["name"].lower() and keyword not in role_text:
                    continue
        all_rows.append(row)

    all_rows.sort(key=lambda item: (-_role_rank(item["highest_role"]), item["email"]))
    total = len(all_rows)
    paged = all_rows[offset : offset + limit]

    role_counter = Counter(item["highest_role"] or "UNASSIGNED" for item in all_rows)
    status_counter = Counter(item["status"] for item in all_rows)
    return success_response(
        {
            "items": paged,
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "roles": [{"role": key, "count": role_counter[key]} for key in sorted(role_counter.keys())],
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            },
        }
    )


@router.get("/users/{user_id}")
async def get_access_user_detail(
    user_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)

    users, tenant_roles_map, project_roles_map = await _load_tenant_user_maps(db, tenant_id)
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    tenant_roles = tenant_roles_map.get(user_id, [])
    project_roles = project_roles_map.get(user_id, [])
    item = _serialize_user_item(user, tenant_roles=tenant_roles, project_roles=project_roles)

    audit_result = await db.execute(
        select(AuditLog)
        .where(AuditLog.user_id.like(f"user:{user.email}|%"))
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(50)
    )
    audit_rows = list(audit_result.scalars().all())
    recent_actions = []
    action_counter = Counter()
    for row in audit_rows:
        details = _safe_json_loads(row.details)
        action_counter[row.action] += 1
        recent_actions.append(
            {
                "id": row.id,
                "timestamp": _to_iso(row.timestamp),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    templates = await _load_effective_role_templates(db, tenant_id)
    effective_permission_profiles = []
    role_values = sorted({item["role"] for item in tenant_roles + project_roles})
    for role_name in role_values:
        role_key = role_name.upper()
        template = templates.get(role_key)
        effective_permission_profiles.append(
            {
                "role": role_name,
                "template_key": role_key,
                "template_name": template["name"] if template else None,
                "module_count": len((template or {}).get("permission_matrix", {}).get("modules", {})),
                "is_active": (template or {}).get("is_active", False),
            }
        )

    return success_response(
        {
            "user": item,
            "audit_summary": {
                "recent_actions": recent_actions[:20],
                "top_actions": [{"action": key, "count": value} for key, value in action_counter.most_common(10)],
            },
            "effective_permission_profiles": effective_permission_profiles,
        }
    )

@router.post("/users/invite")
async def invite_access_user(
    request: AccessInviteRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    context_tenant_id = _tenant_id_from_context(context)

    normalized_email = _normalize_email(request.email)
    tenant_role = _normalize_tenant_role(request.tenant_role)
    project_role = _normalize_project_role(request.project_role, allow_owner=False)
    tenant_id, project = await _resolve_target_project(
        db,
        context_tenant_id=context_tenant_id,
        requested_tenant_id=request.tenant_id,
        requested_project_id=request.project_id,
        default_project_id=context.project.id,
    )

    user_result = await db.execute(select(User).where(User.email == normalized_email))
    existing_user = user_result.scalar_one_or_none()

    mode: str
    member_data: dict[str, Any] | None = None
    invitation_data: dict[str, Any] | None = None

    if existing_user:
        tenant_role_result = await db.execute(
            select(UserTenantRole).where(
                UserTenantRole.user_id == existing_user.id,
                UserTenantRole.tenant_id == tenant_id,
            )
        )
        existing_tenant_role = tenant_role_result.scalar_one_or_none()
        if existing_tenant_role:
            if existing_tenant_role.role != "OWNER":
                await BaseRepository(UserTenantRole, db).update(existing_tenant_role, {"role": tenant_role})
        else:
            await BaseRepository(UserTenantRole, db).create(
                {
                    "user_id": existing_user.id,
                    "tenant_id": tenant_id,
                    "role": tenant_role,
                }
            )

        project_role_result = await db.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == existing_user.id,
                UserProjectRole.project_id == project.id,
            )
        )
        existing_project_role = project_role_result.scalar_one_or_none()
        if existing_project_role:
            await BaseRepository(UserProjectRole, db).update(existing_project_role, {"role": project_role})
        else:
            await BaseRepository(UserProjectRole, db).create(
                {
                    "user_id": existing_user.id,
                    "project_id": project.id,
                    "role": project_role,
                }
            )

        refreshed_users, refreshed_tenant_roles, refreshed_project_roles = await _load_tenant_user_maps(db, tenant_id)
        refreshed_user = refreshed_users.get(existing_user.id)
        mode = "member_updated"
        member_data = (
            _serialize_user_item(
                refreshed_user,
                tenant_roles=refreshed_tenant_roles.get(existing_user.id, []),
                project_roles=refreshed_project_roles.get(existing_user.id, []),
            )
            if refreshed_user
            else None
        )
    else:
        invite_token = secrets.token_urlsafe(24)
        invitation = await BaseRepository(ProjectMemberInvitation, db).create(
            {
                "tenant_id": tenant_id,
                "project_id": project.id,
                "email": normalized_email,
                "role": project_role,
                "status": "PENDING",
                "invite_token": invite_token,
                "invited_by_user_id": context.user.id if context.user else None,
                "expires_at": datetime.now(timezone.utc) + timedelta(hours=request.expires_in_hours),
            }
        )
        mode = "invitation_sent"
        invitation_data = {
            "id": invitation.id,
            "email": invitation.email,
            "tenant_id": invitation.tenant_id,
            "project_id": invitation.project_id,
            "project_role": invitation.role,
            "tenant_role": tenant_role,
            "status": invitation.status,
            "expires_at": _to_iso(invitation.expires_at),
            "created_at": _to_iso(invitation.created_at),
        }

    await _write_audit(
        db,
        context,
        "ACCESS_USER_INVITE",
        "USER_ACCESS",
        normalized_email,
        {
            "summary": "User invitation/assignment processed",
            "mode": mode,
            "tenant_id": tenant_id,
            "project_id": project.id,
            "tenant_role": tenant_role,
            "project_role": project_role,
            "email": normalized_email,
        },
    )

    return success_response(
        {
            "mode": mode,
            "member": member_data,
            "pending_invitation": invitation_data,
            "delivery": {
                "channel": "EMAIL",
                "status": "QUEUED_SIMULATED",
            },
        },
        message="Access invitation processed",
        code="ACCESS_USER_INVITED",
    )


@router.patch("/users/{user_id}/roles")
async def update_access_user_roles(
    user_id: int,
    request: AccessRolesUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)

    users, _, _ = await _load_tenant_user_maps(db, tenant_id)
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    tenant_role_action = _normalize_manage_action(
        request.tenant_role_action,
        TENANT_ROLE_MANAGE_ACTIONS,
        field_name="tenant_role_action",
    )
    tenant_role_value = _normalize_tenant_role(request.tenant_role) if request.tenant_role else None
    if tenant_role_action == "UPSERT" and tenant_role_value is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="tenant_role is required for UPSERT")

    tenant_role_result = await db.execute(
        select(UserTenantRole).where(
            UserTenantRole.user_id == user_id,
            UserTenantRole.tenant_id == tenant_id,
        )
    )
    existing_tenant_role = tenant_role_result.scalar_one_or_none()
    if tenant_role_action == "UPSERT":
        if existing_tenant_role:
            if existing_tenant_role.role != "OWNER":
                await BaseRepository(UserTenantRole, db).update(existing_tenant_role, {"role": tenant_role_value})
        else:
            await BaseRepository(UserTenantRole, db).create(
                {
                    "user_id": user_id,
                    "tenant_id": tenant_id,
                    "role": tenant_role_value,
                }
            )
    else:
        if existing_tenant_role and existing_tenant_role.role != "OWNER":
            await db.delete(existing_tenant_role)

    for item in request.project_roles:
        action = _normalize_manage_action(item.action, PROJECT_ROLE_MANAGE_ACTIONS, field_name="project role action")
        role_value = None
        if action == "UPSERT":
            if item.role is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="project role is required for UPSERT")
            allow_owner = (context.project_role or "").upper() == "OWNER" or (context.tenant_role or "").upper() == "OWNER"
            role_value = _normalize_project_role(item.role, allow_owner=allow_owner)

        project_result = await db.execute(
            select(Project).where(Project.id == item.project_id, Project.tenant_id == tenant_id)
        )
        project = project_result.scalar_one_or_none()
        if project is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Project {item.project_id} not found")

        row_result = await db.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == user_id,
                UserProjectRole.project_id == item.project_id,
            )
        )
        existing_row = row_result.scalar_one_or_none()
        if action == "UPSERT":
            if existing_row:
                await BaseRepository(UserProjectRole, db).update(existing_row, {"role": role_value})
            else:
                await BaseRepository(UserProjectRole, db).create(
                    {
                        "user_id": user_id,
                        "project_id": item.project_id,
                        "role": role_value,
                    }
                )
        elif existing_row:
            await db.delete(existing_row)

    refreshed_users, refreshed_tenant_roles, refreshed_project_roles = await _load_tenant_user_maps(db, tenant_id)
    refreshed_user = refreshed_users.get(user_id)
    if refreshed_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found after update")
    payload = _serialize_user_item(
        refreshed_user,
        tenant_roles=refreshed_tenant_roles.get(user_id, []),
        project_roles=refreshed_project_roles.get(user_id, []),
    )

    await _write_audit(
        db,
        context,
        "ACCESS_USER_ROLE_UPDATE",
        "USER_ACCESS",
        str(user_id),
        {
            "summary": "User roles updated",
            "tenant_role_action": tenant_role_action,
            "tenant_role": tenant_role_value,
            "project_role_updates": [item.model_dump() for item in request.project_roles],
        },
    )
    return success_response(payload, message="User roles updated", code="ACCESS_USER_ROLES_UPDATED")


@router.patch("/users/{user_id}/status")
async def update_access_user_status(
    user_id: int,
    request: AccessStatusUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)

    users, _, _ = await _load_tenant_user_maps(db, tenant_id)
    user = users.get(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    updated_user = await BaseRepository(User, db).update(user, {"is_active": request.is_active})
    await _write_audit(
        db,
        context,
        "ACCESS_USER_STATUS_UPDATE",
        "USER_ACCESS",
        str(user_id),
        {
            "summary": "User status updated",
            "is_active": request.is_active,
            "email": updated_user.email,
        },
    )
    return success_response(
        {
            "user_id": updated_user.id,
            "email": updated_user.email,
            "is_active": updated_user.is_active,
            "updated_at": _to_iso(updated_user.updated_at),
        },
        message="User status updated",
        code="ACCESS_USER_STATUS_UPDATED",
    )


@router.get("/role-templates")
async def list_access_role_templates(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)
    templates = await _load_effective_role_templates(db, tenant_id)

    items = []
    for template_key in sorted(templates.keys(), key=lambda item: (-_role_rank(item), item)):
        template = templates[template_key]
        items.append(
            {
                "template_key": template_key,
                "name": template["name"],
                "description": template.get("description"),
                "permission_matrix": template["permission_matrix"],
                "is_active": template.get("is_active", True),
                "is_system": template.get("is_system", False),
                "source": template.get("source", "SYSTEM"),
                "template_id": template.get("template_id"),
                "updated_at": template.get("updated_at"),
            }
        )
    return success_response({"items": items, "total": len(items)})


@router.put("/role-templates/{template_key}")
async def upsert_access_role_template(
    template_key: str,
    request: AccessRoleTemplateUpsertRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)
    normalized_key = template_key.strip().upper()
    if len(normalized_key) < 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid template_key")

    matrix = _normalize_permission_matrix(request.permission_matrix)
    row_result = await db.execute(
        select(RoleTemplatePolicy).where(
            RoleTemplatePolicy.tenant_id == tenant_id,
            RoleTemplatePolicy.template_key == normalized_key,
        )
    )
    existing = row_result.scalar_one_or_none()
    payload = {
        "name": request.name.strip(),
        "description": request.description.strip() if request.description else None,
        "permission_matrix": matrix,
        "is_active": request.is_active,
        "is_system": normalized_key in SYSTEM_ROLE_TEMPLATES,
    }
    repo = BaseRepository(RoleTemplatePolicy, db)
    if existing:
        row = await repo.update(existing, payload)
    else:
        row = await repo.create(
            {
                "tenant_id": tenant_id,
                "template_key": normalized_key,
                **payload,
            }
        )

    await _write_audit(
        db,
        context,
        "ACCESS_ROLE_TEMPLATE_SAVE",
        "ROLE_TEMPLATE",
        normalized_key,
        {
            "summary": "Role template saved",
            "is_active": row.is_active,
            "is_system": row.is_system,
        },
    )

    templates = await _load_effective_role_templates(db, tenant_id)
    current = templates[normalized_key]
    return success_response(
        {
            "template_key": normalized_key,
            "name": current["name"],
            "description": current.get("description"),
            "permission_matrix": current["permission_matrix"],
            "is_active": current.get("is_active", True),
            "is_system": current.get("is_system", False),
            "source": current.get("source", "SYSTEM"),
            "template_id": current.get("template_id"),
            "updated_at": current.get("updated_at"),
        },
        message="Role template saved",
        code="ACCESS_ROLE_TEMPLATE_SAVED",
    )


@router.delete("/role-templates/{template_key}")
async def delete_access_role_template(
    template_key: str,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)
    normalized_key = template_key.strip().upper()

    row_result = await db.execute(
        select(RoleTemplatePolicy).where(
            RoleTemplatePolicy.tenant_id == tenant_id,
            RoleTemplatePolicy.template_key == normalized_key,
        )
    )
    row = row_result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role template override not found")

    await db.delete(row)
    await _write_audit(
        db,
        context,
        "ACCESS_ROLE_TEMPLATE_DELETE",
        "ROLE_TEMPLATE",
        normalized_key,
        {"summary": "Role template override deleted"},
    )
    return success_response(
        {"template_key": normalized_key, "deleted": True},
        message="Role template deleted",
        code="ACCESS_ROLE_TEMPLATE_DELETED",
    )


@router.post("/evaluate")
async def evaluate_access_decision(
    request: AccessEvaluateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_access_admin(context)
    tenant_id = _tenant_id_from_context(context)

    module_key = request.module.strip().upper()
    action_key = request.action.strip().upper()

    users, tenant_roles_map, project_roles_map = await _load_tenant_user_maps(db, tenant_id)
    user = users.get(request.user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if request.project_id is not None:
        project_result = await db.execute(
            select(Project).where(Project.id == request.project_id, Project.tenant_id == tenant_id)
        )
        if project_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    tenant_roles = tenant_roles_map.get(request.user_id, [])
    project_roles = project_roles_map.get(request.user_id, [])
    effective_role = _match_effective_role_for_scope(
        tenant_roles=tenant_roles,
        project_roles=project_roles,
        project_id=request.project_id,
    )

    templates = await _load_effective_role_templates(db, tenant_id)
    if effective_role is None:
        return success_response(
            {
                "allow": False,
                "reason": "No role bound for requested scope",
                "effective_role": None,
                "module": module_key,
                "action": action_key,
            }
        )

    if effective_role == "OWNER":
        return success_response(
            {
                "allow": True,
                "reason": "Owner role bypass",
                "effective_role": effective_role,
                "module": module_key,
                "action": action_key,
            }
        )

    template = templates.get(effective_role) or templates.get("VIEWER")
    allow = _matrix_match(template or {}, module_key, action_key)
    return success_response(
        {
            "allow": allow,
            "reason": "Matched role template" if allow else "Action not allowed by role template",
            "effective_role": effective_role,
            "template": {
                "template_key": effective_role,
                "name": (template or {}).get("name"),
                "source": (template or {}).get("source"),
            },
            "module": module_key,
            "action": action_key,
        }
    )
