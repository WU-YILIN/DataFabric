import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.domain.settings import decrypt_mapping, encrypt_mapping
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.project_integration_setting import ProjectIntegrationSetting
from src.infrastructure.database.models.project_member_invitation import ProjectMemberInvitation
from src.infrastructure.database.models.tenant_security_policy import TenantSecurityPolicy
from src.infrastructure.database.models.user import User, UserProjectRole, UserTenantRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ALLOWED_PROJECT_MEMBER_ROLES = {"VIEWER", "EDITOR", "APPROVER", "ADMIN"}
PROJECT_WRITE_ROLES = {"OWNER", "ADMIN", "EDITOR"}
PROJECT_MEMBER_MANAGE_ROLES = {"OWNER", "ADMIN"}
PROJECT_INTEGRATION_MANAGE_ROLES = {"OWNER", "ADMIN", "EDITOR"}
SECURITY_MANAGE_ROLES = {"OWNER", "ADMIN"}

INTEGRATION_TYPES = {"LLM", "KAFKA", "FLINK", "QDRANT"}
INTEGRATION_SECRET_FIELDS = {
    "LLM": {"api_key"},
    "KAFKA": {"sasl_password"},
    "FLINK": {"token"},
    "QDRANT": {"api_key"},
}


class GeneralSettingsUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = None
    default_domain: str | None = Field(default=None, max_length=128)


class InviteMemberRequest(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    name: str | None = Field(default=None, max_length=255)
    role: str = Field(default="VIEWER", min_length=3, max_length=64)


class UpdateMemberRoleRequest(BaseModel):
    role: str = Field(..., min_length=3, max_length=64)


class TestIntegrationRequest(BaseModel):
    integration_type: str = Field(..., min_length=2, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)


class UpsertIntegrationRequest(BaseModel):
    enabled: bool | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class SecuritySettingsUpdateRequest(BaseModel):
    sso_enabled: bool | None = None
    mfa_required: bool | None = None
    password_min_length: int | None = Field(default=None, ge=8, le=64)
    password_require_upper: bool | None = None
    password_require_lower: bool | None = None
    password_require_number: bool | None = None
    password_require_symbol: bool | None = None
    audit_log_retention_days: int | None = Field(default=None, ge=7, le=3650)
    audit_export_requires_approval: bool | None = None
    max_exports_per_day: int | None = Field(default=None, ge=1, le=10000)


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Settings API requires bearer user context",
        )


def _require_project_role(context: RequestContext, allowed_roles: set[str]) -> None:
    role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if role in allowed_roles:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (allowed_roles & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Permission denied for this settings operation",
    )


def _normalize_tags(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    normalized: list[str] = []
    for item in values:
        value = item.strip()
        if not value:
            continue
        if value not in normalized:
            normalized.append(value)
    return normalized


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if "@" not in normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
    return normalized


def _normalize_member_role(value: str) -> str:
    role = value.strip().upper()
    if role not in ALLOWED_PROJECT_MEMBER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported member role: {value}",
        )
    return role


def _normalize_integration_type(value: str) -> str:
    integration_type = value.strip().upper()
    if integration_type not in INTEGRATION_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported integration_type: {value}",
        )
    return integration_type


def _tenant_id_from_context(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current project is not bound to tenant",
        )
    return context.project.tenant_id


def _mask_secret(value: Any) -> str:
    if value is None:
        return ""
    raw = str(value)
    if len(raw) <= 4:
        return "*" * len(raw)
    return f"{raw[:2]}***{raw[-2:]}"


def _mask_config(integration_type: str, config: dict[str, Any]) -> dict[str, Any]:
    secret_fields = INTEGRATION_SECRET_FIELDS.get(integration_type, set())
    output: dict[str, Any] = {}
    for key, value in config.items():
        output[key] = _mask_secret(value) if key in secret_fields else value
    return output


def _merge_config(
    integration_type: str,
    existing: dict[str, Any],
    incoming: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(existing)
    secret_fields = INTEGRATION_SECRET_FIELDS.get(integration_type, set())
    for key, value in incoming.items():
        if key in secret_fields:
            if value is None:
                continue
            if isinstance(value, str) and (value.strip() == "" or "***" in value):
                continue
        merged[key] = value
    return merged


def _validate_integration_config(
    integration_type: str,
    config: dict[str, Any],
) -> tuple[str, str]:
    if integration_type == "LLM":
        api_key = str(config.get("api_key", "")).strip()
        if not api_key:
            return "FAILURE", "LLM config missing api_key"
        if not api_key.startswith("sk-"):
            return "FAILURE", "LLM api_key should start with sk-"
        base_url = str(config.get("base_url", "")).strip()
        if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
            return "FAILURE", "LLM base_url should use http(s)"
        return "SUCCESS", "LLM connection validation passed"

    if integration_type == "KAFKA":
        bootstrap = str(config.get("bootstrap_servers", "")).strip()
        if not bootstrap:
            return "FAILURE", "Kafka config missing bootstrap_servers"
        nodes = [item.strip() for item in bootstrap.split(",") if item.strip()]
        if not nodes or any(":" not in node for node in nodes):
            return "FAILURE", "Kafka bootstrap_servers should be host:port list"
        return "SUCCESS", "Kafka connection validation passed"

    if integration_type == "FLINK":
        rest_url = str(config.get("rest_url", "")).strip()
        if not rest_url:
            return "FAILURE", "Flink config missing rest_url"
        if not (rest_url.startswith("http://") or rest_url.startswith("https://")):
            return "FAILURE", "Flink rest_url should use http(s)"
        return "SUCCESS", "Flink connection validation passed"

    if integration_type == "QDRANT":
        host = str(config.get("host", "")).strip()
        if not host:
            return "FAILURE", "Qdrant config missing host"
        try:
            port = int(config.get("port", 6333))
        except (TypeError, ValueError):
            return "FAILURE", "Qdrant port must be integer"
        if port <= 0 or port > 65535:
            return "FAILURE", "Qdrant port out of range"
        return "SUCCESS", "Qdrant connection validation passed"

    return "FAILURE", "Unknown integration type"


def _role_rank(role: str | None) -> int:
    order = {
        "OWNER": 5,
        "ADMIN": 4,
        "APPROVER": 3,
        "EDITOR": 2,
        "VIEWER": 1,
        "MEMBER": 0,
    }
    return order.get((role or "").upper(), -1)


def _project_general_to_dict(context: RequestContext) -> dict[str, Any]:
    project = context.project
    return {
        "project_id": project.id,
        "tenant_id": project.tenant_id,
        "name": project.name,
        "description": project.description,
        "tags": project.tags or [],
        "default_domain": project.default_domain,
        "updated_at": project.updated_at.isoformat(),
    }


def _member_to_dict(
    user: User,
    project_role: UserProjectRole,
    tenant_role: str | None,
) -> dict[str, Any]:
    joined_at = project_role.created_at or user.created_at
    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "project_role": project_role.role,
        "tenant_role": tenant_role,
        "joined_at": joined_at.isoformat() if joined_at else None,
        "auth_provider": user.auth_provider,
        "is_active": user.is_active,
    }


def _invitation_to_dict(invitation: ProjectMemberInvitation) -> dict[str, Any]:
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "status": invitation.status,
        "expires_at": invitation.expires_at.isoformat(),
        "created_at": invitation.created_at.isoformat(),
        "updated_at": invitation.updated_at.isoformat(),
    }


def _integration_to_dict(
    integration_type: str,
    row: ProjectIntegrationSetting | None,
) -> dict[str, Any]:
    if not row:
        return {
            "integration_type": integration_type,
            "enabled": False,
            "config": {},
            "has_stored_secret": False,
            "last_test": None,
            "updated_at": None,
        }

    decrypted = decrypt_mapping(row.encrypted_config)
    secret_fields = INTEGRATION_SECRET_FIELDS.get(integration_type, set())
    has_stored_secret = any(bool(decrypted.get(key)) for key in secret_fields)

    return {
        "integration_type": integration_type,
        "enabled": row.enabled,
        "config": _mask_config(integration_type, decrypted),
        "has_stored_secret": has_stored_secret,
        "last_test": {
            "status": row.last_test_status,
            "message": row.last_test_message,
            "tested_at": row.last_tested_at.isoformat() if row.last_tested_at else None,
        }
        if row.last_test_status
        else None,
        "updated_at": row.updated_at.isoformat(),
    }


def _security_policy_to_dict(policy: TenantSecurityPolicy) -> dict[str, Any]:
    return {
        "tenant_id": policy.tenant_id,
        "sso_enabled": policy.sso_enabled,
        "mfa_required": policy.mfa_required,
        "password_policy": {
            "min_length": policy.password_min_length,
            "require_upper": policy.password_require_upper,
            "require_lower": policy.password_require_lower,
            "require_number": policy.password_require_number,
            "require_symbol": policy.password_require_symbol,
        },
        "audit_policy": {
            "retention_days": policy.audit_log_retention_days,
            "export_requires_approval": policy.audit_export_requires_approval,
            "max_exports_per_day": policy.max_exports_per_day,
        },
        "updated_at": policy.updated_at.isoformat(),
    }


def _permissions(context: RequestContext) -> dict[str, bool]:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    return {
        "can_manage_general": project_role in PROJECT_WRITE_ROLES or tenant_role in TENANT_ELEVATED_ROLES,
        "can_manage_members": project_role in PROJECT_MEMBER_MANAGE_ROLES
        or tenant_role in TENANT_ELEVATED_ROLES,
        "can_manage_integrations": project_role in PROJECT_INTEGRATION_MANAGE_ROLES
        or tenant_role in TENANT_ELEVATED_ROLES,
        "can_manage_security": tenant_role in SECURITY_MANAGE_ROLES,
    }


async def _get_project_members(
    db: AsyncSession,
    project_id: int,
    tenant_id: int | None,
) -> list[dict[str, Any]]:
    query = (
        select(User, UserProjectRole, UserTenantRole.role)
        .join(UserProjectRole, UserProjectRole.user_id == User.id)
        .outerjoin(
            UserTenantRole,
            and_(
                UserTenantRole.user_id == User.id,
                UserTenantRole.tenant_id == tenant_id,
            ),
        )
        .where(UserProjectRole.project_id == project_id)
    )
    result = await db.execute(query)
    rows = result.all()
    members = [
        _member_to_dict(user=user, project_role=project_role, tenant_role=tenant_role)
        for user, project_role, tenant_role in rows
    ]
    members.sort(key=lambda item: (-_role_rank(item["project_role"]), item["email"]))
    return members


async def _get_pending_invitations(
    db: AsyncSession,
    project_id: int,
    tenant_id: int,
) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    await db.execute(
        delete(ProjectMemberInvitation).where(
            ProjectMemberInvitation.project_id == project_id,
            ProjectMemberInvitation.tenant_id == tenant_id,
            ProjectMemberInvitation.status == "PENDING",
            ProjectMemberInvitation.expires_at < now,
        )
    )
    invite_result = await db.execute(
        select(ProjectMemberInvitation)
        .where(
            ProjectMemberInvitation.project_id == project_id,
            ProjectMemberInvitation.tenant_id == tenant_id,
            ProjectMemberInvitation.status == "PENDING",
        )
        .order_by(ProjectMemberInvitation.created_at.desc())
    )
    return [_invitation_to_dict(item) for item in invite_result.scalars().all()]


async def _ensure_tenant_security_policy(
    db: AsyncSession,
    tenant_id: int,
) -> TenantSecurityPolicy:
    result = await db.execute(
        select(TenantSecurityPolicy).where(TenantSecurityPolicy.tenant_id == tenant_id)
    )
    policy = result.scalar_one_or_none()
    if policy:
        return policy
    repo = BaseRepository(TenantSecurityPolicy, db)
    return await repo.create({"tenant_id": tenant_id})


async def _ensure_tenant_user_membership(
    db: AsyncSession,
    user_id: int,
    tenant_id: int,
    role: str,
) -> None:
    result = await db.execute(
        select(UserTenantRole).where(
            UserTenantRole.user_id == user_id,
            UserTenantRole.tenant_id == tenant_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if role == "ADMIN" and existing.role != "OWNER":
            await BaseRepository(UserTenantRole, db).update(existing, {"role": "ADMIN"})
        return
    tenant_role_repo = BaseRepository(UserTenantRole, db)
    await tenant_role_repo.create(
        {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "role": "ADMIN" if role == "ADMIN" else "MEMBER",
        }
    )


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
            "details": json.dumps(details, ensure_ascii=True),
        }
    )


@router.get("")
async def get_settings_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)

    members = await _get_project_members(db, context.project.id, tenant_id)
    pending_invites = await _get_pending_invitations(db, context.project.id, tenant_id)

    integration_result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id
        )
    )
    integration_map = {item.integration_type: item for item in integration_result.scalars().all()}
    integrations = [
        _integration_to_dict(integration_type, integration_map.get(integration_type))
        for integration_type in sorted(INTEGRATION_TYPES)
    ]

    policy = await _ensure_tenant_security_policy(db, tenant_id)
    data = {
        "general": _project_general_to_dict(context),
        "members": {
            "items": members,
            "pending_invitations": pending_invites,
        },
        "integrations": integrations,
        "security": _security_policy_to_dict(policy),
        "permissions": _permissions(context),
    }
    return success_response(data)


@router.get("/general")
async def get_general_settings(
    context: RequestContext = Depends(get_request_context),
):
    _require_user_context(context)
    return success_response(_project_general_to_dict(context))


@router.patch("/general")
async def update_general_settings(
    request: GeneralSettingsUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_WRITE_ROLES)

    patch_data = {key: value for key, value in request.model_dump().items() if value is not None}
    if "tags" in patch_data:
        patch_data["tags"] = _normalize_tags(patch_data["tags"])

    if not patch_data:
        return success_response(
            _project_general_to_dict(context),
            message="No changes detected",
            code="SETTINGS_GENERAL_NO_CHANGES",
        )

    before = _project_general_to_dict(context)
    project = await BaseRepository(Project, db).update(context.project, patch_data)
    after = {
        "name": project.name,
        "description": project.description,
        "tags": project.tags,
        "default_domain": project.default_domain,
    }
    await _write_audit(
        db,
        context,
        action="SETTINGS_GENERAL_UPDATE",
        entity_type="PROJECT_SETTINGS",
        entity_id=str(project.id),
        details={"before": before, "after": after},
    )
    return success_response(
        _project_general_to_dict(context),
        message="General settings updated",
        code="SETTINGS_GENERAL_UPDATED",
    )


@router.get("/members")
async def list_members(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)
    return success_response(
        {
            "items": await _get_project_members(db, context.project.id, tenant_id),
            "pending_invitations": await _get_pending_invitations(db, context.project.id, tenant_id),
        }
    )


@router.post("/members/invite")
async def invite_member(
    request: InviteMemberRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_MEMBER_MANAGE_ROLES)

    email = _normalize_email(request.email)
    role = _normalize_member_role(request.role)
    tenant_id = _tenant_id_from_context(context)
    now = datetime.now(timezone.utc)

    user_result = await db.execute(select(User).where(User.email == email))
    user = user_result.scalar_one_or_none()
    if user:
        await _ensure_tenant_user_membership(db, user.id, tenant_id, role)

        role_result = await db.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == user.id,
                UserProjectRole.project_id == context.project.id,
            )
        )
        role_row = role_result.scalar_one_or_none()
        role_repo = BaseRepository(UserProjectRole, db)
        if role_row:
            role_row = await role_repo.update(role_row, {"role": role})
        else:
            role_row = await role_repo.create(
                {
                    "user_id": user.id,
                    "project_id": context.project.id,
                    "role": role,
                }
            )

        pending_invites_result = await db.execute(
            select(ProjectMemberInvitation).where(
                ProjectMemberInvitation.project_id == context.project.id,
                ProjectMemberInvitation.tenant_id == tenant_id,
                ProjectMemberInvitation.email == email,
                ProjectMemberInvitation.status == "PENDING",
            )
        )
        invite_repo = BaseRepository(ProjectMemberInvitation, db)
        for item in pending_invites_result.scalars().all():
            await invite_repo.update(item, {"status": "ACCEPTED", "accepted_at": now})

        await _write_audit(
            db,
            context,
            action="SETTINGS_MEMBER_UPSERT",
            entity_type="PROJECT_MEMBER",
            entity_id=str(user.id),
            details={"email": email, "role": role, "mode": "existing_user"},
        )
        return success_response(
            {
                "mode": "member_updated",
                "member": _member_to_dict(user, role_row, context.tenant_role),
                "pending_invitation": None,
            },
            message="Member access updated",
            code="SETTINGS_MEMBER_UPDATED",
        )

    invite_result = await db.execute(
        select(ProjectMemberInvitation)
        .where(
            ProjectMemberInvitation.project_id == context.project.id,
            ProjectMemberInvitation.tenant_id == tenant_id,
            ProjectMemberInvitation.email == email,
            ProjectMemberInvitation.status == "PENDING",
        )
        .order_by(ProjectMemberInvitation.created_at.desc())
        .limit(1)
    )
    existing_invite = invite_result.scalar_one_or_none()
    invitation_repo = BaseRepository(ProjectMemberInvitation, db)
    if existing_invite:
        invitation = await invitation_repo.update(
            existing_invite,
            {
                "role": role,
                "invite_token": secrets.token_urlsafe(24),
                "expires_at": now + timedelta(days=7),
            },
        )
    else:
        invitation = await invitation_repo.create(
            {
                "tenant_id": tenant_id,
                "project_id": context.project.id,
                "email": email,
                "role": role,
                "status": "PENDING",
                "invite_token": secrets.token_urlsafe(24),
                "invited_by_user_id": context.user.id,
                "expires_at": now + timedelta(days=7),
            }
        )

    await _write_audit(
        db,
        context,
        action="SETTINGS_MEMBER_INVITE",
        entity_type="PROJECT_MEMBER_INVITATION",
        entity_id=str(invitation.id),
        details={
            "email": email,
            "role": role,
            "name": request.name,
            "expires_at": invitation.expires_at.isoformat(),
        },
    )
    return success_response(
        {
            "mode": "invitation_sent",
            "member": None,
            "pending_invitation": _invitation_to_dict(invitation),
        },
        message="Member invitation created",
        code="SETTINGS_MEMBER_INVITED",
    )


@router.patch("/members/{user_id}/role")
async def update_member_role(
    user_id: int,
    request: UpdateMemberRoleRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_MEMBER_MANAGE_ROLES)

    role = _normalize_member_role(request.role)
    member_result = await db.execute(
        select(UserProjectRole).where(
            UserProjectRole.project_id == context.project.id,
            UserProjectRole.user_id == user_id,
        )
    )
    member_role = member_result.scalar_one_or_none()
    if not member_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member_role.role == "OWNER":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner role cannot be modified")

    if context.user and context.user.id == user_id and role == "VIEWER":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot downgrade current user to VIEWER",
        )

    previous_role = member_role.role
    role_repo = BaseRepository(UserProjectRole, db)
    updated = await role_repo.update(member_role, {"role": role})

    tenant_id = _tenant_id_from_context(context)
    await _ensure_tenant_user_membership(db, user_id, tenant_id, role)

    await _write_audit(
        db,
        context,
        action="SETTINGS_MEMBER_ROLE_UPDATE",
        entity_type="PROJECT_MEMBER",
        entity_id=str(user_id),
        details={"before_role": previous_role, "after_role": role},
    )

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return success_response(
        _member_to_dict(user=user, project_role=updated, tenant_role=context.tenant_role),
        message="Member role updated",
        code="SETTINGS_MEMBER_ROLE_UPDATED",
    )


@router.delete("/members/{user_id}")
async def remove_member(
    user_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_MEMBER_MANAGE_ROLES)

    if context.user and context.user.id == user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot remove current user")

    member_result = await db.execute(
        select(UserProjectRole).where(
            UserProjectRole.project_id == context.project.id,
            UserProjectRole.user_id == user_id,
        )
    )
    member_role = member_result.scalar_one_or_none()
    if not member_role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
    if member_role.role == "OWNER":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Owner cannot be removed")

    await BaseRepository(UserProjectRole, db).remove(member_role.id)

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    await _write_audit(
        db,
        context,
        action="SETTINGS_MEMBER_REMOVE",
        entity_type="PROJECT_MEMBER",
        entity_id=str(user_id),
        details={
            "email": user.email if user else None,
            "previous_role": member_role.role,
        },
    )
    return success_response(
        {"user_id": user_id},
        message="Member removed",
        code="SETTINGS_MEMBER_REMOVED",
    )


@router.get("/integrations")
async def list_integrations(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id
        )
    )
    row_map = {row.integration_type: row for row in result.scalars().all()}
    data = [
        _integration_to_dict(integration_type, row_map.get(integration_type))
        for integration_type in sorted(INTEGRATION_TYPES)
    ]
    return success_response(data)


@router.post("/integrations/test")
async def test_integration(
    request: TestIntegrationRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_INTEGRATION_MANAGE_ROLES)

    integration_type = _normalize_integration_type(request.integration_type)
    existing_result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id,
            ProjectIntegrationSetting.integration_type == integration_type,
        )
    )
    existing = existing_result.scalar_one_or_none()
    existing_config = decrypt_mapping(existing.encrypted_config) if existing else {}
    merged_config = _merge_config(integration_type, existing_config, request.config)
    test_status, test_message = _validate_integration_config(integration_type, merged_config)

    await _write_audit(
        db,
        context,
        action="SETTINGS_INTEGRATION_TEST",
        entity_type="PROJECT_INTEGRATION",
        entity_id=integration_type,
        details={"status": test_status, "message": test_message},
    )
    return success_response(
        {
            "integration_type": integration_type,
            "status": test_status,
            "message": test_message,
        },
        message="Integration test executed",
        code="SETTINGS_INTEGRATION_TESTED",
    )


@router.put("/integrations/{integration_type}")
async def upsert_integration(
    integration_type: str,
    request: UpsertIntegrationRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, PROJECT_INTEGRATION_MANAGE_ROLES)
    normalized_type = _normalize_integration_type(integration_type)

    existing_result = await db.execute(
        select(ProjectIntegrationSetting).where(
            ProjectIntegrationSetting.project_id == context.project.id,
            ProjectIntegrationSetting.integration_type == normalized_type,
        )
    )
    existing = existing_result.scalar_one_or_none()
    existing_config = decrypt_mapping(existing.encrypted_config) if existing else {}
    merged_config = _merge_config(normalized_type, existing_config, request.config)
    test_status, test_message = _validate_integration_config(normalized_type, merged_config)

    enabled = request.enabled if request.enabled is not None else (existing.enabled if existing else False)
    if enabled and test_status != "SUCCESS":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Integration test failed: {test_message}",
        )

    patch = {
        "enabled": enabled,
        "encrypted_config": encrypt_mapping(merged_config),
        "last_test_status": test_status,
        "last_test_message": test_message,
        "last_tested_at": datetime.now(timezone.utc),
    }
    repo = BaseRepository(ProjectIntegrationSetting, db)
    if existing:
        row = await repo.update(existing, patch)
    else:
        row = await repo.create(
            {
                "project_id": context.project.id,
                "integration_type": normalized_type,
                **patch,
            }
        )

    await _write_audit(
        db,
        context,
        action="SETTINGS_INTEGRATION_SAVE",
        entity_type="PROJECT_INTEGRATION",
        entity_id=normalized_type,
        details={"enabled": enabled, "test_status": test_status, "test_message": test_message},
    )
    return success_response(
        _integration_to_dict(normalized_type, row),
        message="Integration settings saved",
        code="SETTINGS_INTEGRATION_SAVED",
    )


@router.get("/security")
async def get_security_settings(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)
    policy = await _ensure_tenant_security_policy(db, tenant_id)
    return success_response(_security_policy_to_dict(policy))


@router.patch("/security")
async def update_security_settings(
    request: SecuritySettingsUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_project_role(context, SECURITY_MANAGE_ROLES)
    tenant_id = _tenant_id_from_context(context)

    policy = await _ensure_tenant_security_policy(db, tenant_id)
    patch_data = {key: value for key, value in request.model_dump().items() if value is not None}
    if not patch_data:
        return success_response(
            _security_policy_to_dict(policy),
            message="No changes detected",
            code="SETTINGS_SECURITY_NO_CHANGES",
        )

    mapped_patch: dict[str, Any] = {}
    if "sso_enabled" in patch_data:
        mapped_patch["sso_enabled"] = patch_data["sso_enabled"]
    if "mfa_required" in patch_data:
        mapped_patch["mfa_required"] = patch_data["mfa_required"]
    if "password_min_length" in patch_data:
        mapped_patch["password_min_length"] = patch_data["password_min_length"]
    if "password_require_upper" in patch_data:
        mapped_patch["password_require_upper"] = patch_data["password_require_upper"]
    if "password_require_lower" in patch_data:
        mapped_patch["password_require_lower"] = patch_data["password_require_lower"]
    if "password_require_number" in patch_data:
        mapped_patch["password_require_number"] = patch_data["password_require_number"]
    if "password_require_symbol" in patch_data:
        mapped_patch["password_require_symbol"] = patch_data["password_require_symbol"]
    if "audit_log_retention_days" in patch_data:
        mapped_patch["audit_log_retention_days"] = patch_data["audit_log_retention_days"]
    if "audit_export_requires_approval" in patch_data:
        mapped_patch["audit_export_requires_approval"] = patch_data["audit_export_requires_approval"]
    if "max_exports_per_day" in patch_data:
        mapped_patch["max_exports_per_day"] = patch_data["max_exports_per_day"]

    updated = await BaseRepository(TenantSecurityPolicy, db).update(policy, mapped_patch)
    await _write_audit(
        db,
        context,
        action="SETTINGS_SECURITY_UPDATE",
        entity_type="TENANT_SECURITY_POLICY",
        entity_id=str(updated.tenant_id),
        details={"patch": mapped_patch},
    )
    return success_response(
        _security_policy_to_dict(updated),
        message="Security settings updated",
        code="SETTINGS_SECURITY_UPDATED",
    )
