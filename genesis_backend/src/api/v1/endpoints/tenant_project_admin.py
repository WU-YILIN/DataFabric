"""
Tenant & Project Management — Admin CRUD API

Endpoints for creating, updating, and listing tenants and projects.
Only users with OWNER or ADMIN tenant roles can perform mutations.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import get_current_user
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.tenant import Tenant
from src.infrastructure.database.models.user import User, UserProjectRole, UserTenantRole
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ELEVATED_ROLES = {"OWNER", "ADMIN"}


# ── Request Schemas ──────────────────────────────────────────────

class CreateTenantRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    slug: str = Field(..., min_length=2, max_length=128, pattern=r"^[a-z0-9_-]+$")


class UpdateTenantRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    status: str | None = Field(default=None, pattern=r"^(ACTIVE|ARCHIVED)$")


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    tags: list[str] | None = None


# ── Helpers ──────────────────────────────────────────────────────

async def _require_tenant_admin(db: AsyncSession, user: User, tenant_id: int) -> None:
    """Ensure the user has OWNER or ADMIN role on the given tenant."""
    result = await db.execute(
        select(UserTenantRole.role).where(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id,
        )
    )
    role = result.scalar_one_or_none()
    if not role or role.upper() not in ELEVATED_ROLES:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant admin access required")


def _tenant_to_dict(tenant: Tenant, project_count: int = 0) -> dict[str, Any]:
    return {
        "id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "project_count": project_count,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "updated_at": tenant.updated_at.isoformat() if tenant.updated_at else None,
    }


def _project_to_dict(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "tenant_id": project.tenant_id,
        "name": project.name,
        "description": project.description,
        "api_key": project.api_key,
        "tags": project.tags or [],
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


# ── Tenant CRUD ──────────────────────────────────────────────────

@router.get("/tenants")
async def list_tenants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all tenants the current user has access to, with project counts."""
    tenant_rows = await db.execute(
        select(Tenant, UserTenantRole.role)
        .join(UserTenantRole, UserTenantRole.tenant_id == Tenant.id)
        .where(UserTenantRole.user_id == user.id)
        .order_by(Tenant.name.asc())
    )
    tenants = tenant_rows.all()

    items = []
    for tenant, role in tenants:
        count_result = await db.execute(
            select(func.count(Project.id)).where(Project.tenant_id == tenant.id)
        )
        project_count = count_result.scalar() or 0
        item = _tenant_to_dict(tenant, project_count)
        item["role"] = role
        items.append(item)

    return success_response({"items": items, "total": len(items)})


@router.post("/tenants")
async def create_tenant(
    request: CreateTenantRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """Create a new tenant. The creator is automatically assigned OWNER role."""
    existing = await db.execute(select(Tenant).where(Tenant.slug == request.slug))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already exists")

    tenant = Tenant(name=request.name, slug=request.slug, status="ACTIVE")
    db.add(tenant)
    await db.flush()

    # Assign OWNER role to creator
    db.add(UserTenantRole(user_id=user.id, tenant_id=tenant.id, role="OWNER"))
    await db.commit()
    await db.refresh(tenant)

    return success_response(_tenant_to_dict(tenant), message="Tenant created", code="TENANT_CREATED")


@router.patch("/tenants/{tenant_id}")
async def update_tenant(
    tenant_id: int,
    request: UpdateTenantRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(db, user, tenant_id)
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    if request.name is not None:
        tenant.name = request.name
    if request.status is not None:
        tenant.status = request.status
    tenant.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(tenant)

    return success_response(_tenant_to_dict(tenant), message="Tenant updated")


@router.delete("/tenants/{tenant_id}")
async def archive_tenant(
    tenant_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(db, user, tenant_id)
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    tenant.status = "ARCHIVED"
    tenant.updated_at = datetime.now(timezone.utc)
    await db.commit()

    return success_response({"id": tenant_id, "status": "ARCHIVED"}, message="Tenant archived")


# ── Project CRUD ─────────────────────────────────────────────────

@router.get("/tenants/{tenant_id}/projects")
async def list_projects(
    tenant_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    """List all projects under a given tenant."""
    # Verify user has access to this tenant
    tenant_role_result = await db.execute(
        select(UserTenantRole.role).where(
            UserTenantRole.user_id == user.id,
            UserTenantRole.tenant_id == tenant_id,
        )
    )
    if not tenant_role_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this tenant")

    projects_result = await db.execute(
        select(Project).where(Project.tenant_id == tenant_id).order_by(Project.name.asc())
    )
    projects = projects_result.scalars().all()

    return success_response({
        "items": [_project_to_dict(p) for p in projects],
        "total": len(projects),
    })


@router.post("/tenants/{tenant_id}/projects")
async def create_project(
    tenant_id: int,
    request: CreateProjectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    await _require_tenant_admin(db, user, tenant_id)

    # Verify tenant exists
    tenant_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant_result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    import secrets
    project = Project(
        tenant_id=tenant_id,
        name=request.name,
        description=request.description or "",
        api_key=f"pk_{secrets.token_hex(16)}",
        tags=[],
        tech_stack={},
    )
    db.add(project)
    await db.flush()

    # Assign OWNER role to creator
    db.add(UserProjectRole(user_id=user.id, project_id=project.id, role="OWNER"))
    await db.commit()
    await db.refresh(project)

    return success_response(_project_to_dict(project), message="Project created", code="PROJECT_CREATED")


@router.patch("/projects/{project_id}")
async def update_project(
    project_id: int,
    request: UpdateProjectRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.tenant_id:
        await _require_tenant_admin(db, user, project.tenant_id)

    if request.name is not None:
        project.name = request.name
    if request.description is not None:
        project.description = request.description
    if request.tags is not None:
        project.tags = request.tags
    project.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(project)

    return success_response(_project_to_dict(project), message="Project updated")


@router.delete("/projects/{project_id}")
async def archive_project(
    project_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if project.tenant_id:
        await _require_tenant_admin(db, user, project.tenant_id)

    await db.delete(project)
    await db.commit()

    return success_response({"id": project_id}, message="Project deleted")
