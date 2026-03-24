from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import TENANT_ELEVATED_ROLES, get_current_user
from src.config import settings
from src.domain.auth.security import hash_password, sign_access_token, verify_password
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.project_member_invitation import ProjectMemberInvitation
from src.infrastructure.database.models.tenant import Tenant
from src.infrastructure.database.models.user import User, UserProjectRole, UserTenantRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.user_repo import UserRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str
    tenant_slug: str | None = None
    project_id: int | None = None


class SwitchContextRequest(BaseModel):
    tenant_id: int
    project_id: int


class UpdateProfileRequest(BaseModel):
    name: str


def _role_priority(role: str) -> int:
    order = {
        "OWNER": 5,
        "ADMIN": 4,
        "APPROVER": 3,
        "EDITOR": 2,
        "VIEWER": 1,
    }
    return order.get(role.upper(), 0)


async def _build_access_tree(user: User, db: AsyncSession) -> list[dict]:
    tenant_rows = await db.execute(
        select(Tenant, UserTenantRole.role)
        .join(UserTenantRole, UserTenantRole.tenant_id == Tenant.id)
        .where(UserTenantRole.user_id == user.id)
        .order_by(Tenant.name.asc())
    )
    project_rows = await db.execute(
        select(Project, UserProjectRole.role)
        .join(UserProjectRole, UserProjectRole.project_id == Project.id)
        .where(UserProjectRole.user_id == user.id)
        .order_by(Project.name.asc())
    )

    tree: dict[int, dict] = {}
    for tenant, role in tenant_rows.all():
        tree[tenant.id] = {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "status": tenant.status,
            "role": role,
            "projects": [],
        }

    project_map: dict[tuple[int, int], dict] = {}
    for project, role in project_rows.all():
        if project.tenant_id is None:
            continue
        tenant_entry = tree.get(project.tenant_id)
        if not tenant_entry:
            tenant_result = await db.execute(select(Tenant).where(Tenant.id == project.tenant_id))
            tenant = tenant_result.scalar_one_or_none()
            if not tenant:
                continue
            tenant_entry = {
                "id": tenant.id,
                "name": tenant.name,
                "slug": tenant.slug,
                "status": tenant.status,
                "role": "MEMBER",
                "projects": [],
            }
            tree[tenant.id] = tenant_entry
        item = {
            "id": project.id,
            "name": project.name,
            "role": role,
        }
        tenant_entry["projects"].append(item)
        project_map[(project.tenant_id, project.id)] = item

    for tenant_id, tenant_entry in tree.items():
        tenant_role = tenant_entry["role"]
        if tenant_role not in TENANT_ELEVATED_ROLES:
            continue
        all_projects_result = await db.execute(
            select(Project).where(Project.tenant_id == tenant_id).order_by(Project.name.asc())
        )
        for project in all_projects_result.scalars().all():
            key = (tenant_id, project.id)
            if key in project_map:
                continue
            tenant_entry["projects"].append(
                {
                    "id": project.id,
                    "name": project.name,
                    "role": tenant_role,
                }
            )

    for tenant_entry in tree.values():
        tenant_entry["projects"] = sorted(
            tenant_entry["projects"],
            key=lambda item: (-_role_priority(item["role"]), item["name"]),
        )

    return sorted(tree.values(), key=lambda item: item["name"])


def _build_default_context(access_tree: list[dict]) -> dict | None:
    for tenant in access_tree:
        if tenant["projects"]:
            first_project = tenant["projects"][0]
            return {
                "tenant_id": tenant["id"],
                "project_id": first_project["id"],
            }
    return None


def _resolve_context(access_tree: list[dict], tenant_id: int, project_id: int) -> dict:
    tenant_entry = next((item for item in access_tree if item["id"] == tenant_id), None)
    if not tenant_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    project_entry = next((item for item in tenant_entry["projects"] if item["id"] == project_id), None)
    if not project_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return {
        "tenant_id": tenant_entry["id"],
        "tenant_name": tenant_entry["name"],
        "tenant_slug": tenant_entry["slug"],
        "tenant_role": tenant_entry["role"],
        "project_id": project_entry["id"],
        "project_name": project_entry["name"],
        "project_role": project_entry["role"],
    }


async def _build_login_result(user: User, db: AsyncSession) -> dict:
    access_tree = await _build_access_tree(user, db)
    if not access_tree:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tenant/project access assigned",
        )

    expires_seconds = settings.AUTH_TOKEN_EXPIRE_HOURS * 3600
    access_token = sign_access_token(
        payload={"sub": user.id, "email": user.email},
        secret_key=settings.AUTH_SECRET_KEY,
        expires_in_seconds=expires_seconds,
    )
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    default_context = _build_default_context(access_tree)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
        "tenants": access_tree,
        "default_context": default_context,
    }


@router.post("/login")
async def login(
    request: LoginRequest,
    db: AsyncSession = Depends(get_async_session),
):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(request.email.lower())
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    data = await _build_login_result(user, db)
    return success_response(data, message="Login success", code="LOGIN_SUCCESS")


@router.post("/register")
async def register(
    request: RegisterRequest,
    db: AsyncSession = Depends(get_async_session),
):
    email = request.email.strip().lower()
    name = request.name.strip()
    if "@" not in email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid email")
    if len(request.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 8 characters",
        )
    if len(name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must be at least 2 characters",
        )

    user_repo = UserRepository(db)
    existing = await user_repo.get_by_email(email)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    tenant_query = select(Tenant).order_by(Tenant.id.asc())
    if request.tenant_slug:
        tenant_query = select(Tenant).where(Tenant.slug == request.tenant_slug)
    tenant_result = await db.execute(tenant_query)
    if request.tenant_slug:
        tenant = tenant_result.scalar_one_or_none()
    else:
        tenant = tenant_result.scalars().first()
    if not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    project_query = select(Project).where(Project.tenant_id == tenant.id).order_by(Project.id.asc())
    if request.project_id is not None:
        project_query = select(Project).where(
            Project.tenant_id == tenant.id,
            Project.id == request.project_id,
        )
    project_result = await db.execute(project_query)
    if request.project_id is not None:
        project = project_result.scalar_one_or_none()
    else:
        project = project_result.scalars().first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    now = datetime.now(timezone.utc)
    invitation_result = await db.execute(
        select(ProjectMemberInvitation).where(
            ProjectMemberInvitation.tenant_id == tenant.id,
            ProjectMemberInvitation.project_id == project.id,
            ProjectMemberInvitation.email == email,
            ProjectMemberInvitation.status == "PENDING",
            ProjectMemberInvitation.expires_at >= now,
        )
    )
    invitations = list(invitation_result.scalars().all())
    assigned_project_role = "VIEWER"
    if invitations:
        assigned_project_role = max(
            (item.role for item in invitations),
            key=_role_priority,
        )

    user = await user_repo.create(
        {
            "email": email,
            "name": name,
            "auth_provider": "local",
            "password_hash": hash_password(request.password),
            "is_active": True,
        }
    )
    tenant_role_repo = BaseRepository(UserTenantRole, db)
    project_role_repo = BaseRepository(UserProjectRole, db)
    await tenant_role_repo.create(
        {
            "user_id": user.id,
            "tenant_id": tenant.id,
            "role": "ADMIN" if assigned_project_role == "ADMIN" else "MEMBER",
        }
    )
    await project_role_repo.create(
        {
            "user_id": user.id,
            "project_id": project.id,
            "role": assigned_project_role,
        }
    )

    if invitations:
        invitation_repo = BaseRepository(ProjectMemberInvitation, db)
        for invitation in invitations:
            await invitation_repo.update(
                invitation,
                {
                    "status": "ACCEPTED",
                    "accepted_at": now,
                },
            )

    data = await _build_login_result(user, db)
    return success_response(data, message="Register success", code="REGISTER_SUCCESS")


@router.get("/me")
async def me(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    access_tree = await _build_access_tree(user, db)
    data = {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
        "tenants": access_tree,
        "default_context": _build_default_context(access_tree),
    }
    return success_response(data)


@router.patch("/me")
async def update_me(
    request: UpdateProfileRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    name = request.name.strip()
    if len(name) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Name must be at least 2 characters",
        )
    updated = await BaseRepository(User, db).update(user, {"name": name})
    data = await _build_login_result(updated, db)
    return success_response(data, message="Profile updated", code="PROFILE_UPDATED")


@router.get("/tenants")
async def list_tenants(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    access_tree = await _build_access_tree(user, db)
    return success_response(access_tree)


@router.get("/projects")
async def list_projects(
    tenant_id: int = Query(..., ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    access_tree = await _build_access_tree(user, db)
    tenant_entry = next((item for item in access_tree if item["id"] == tenant_id), None)
    if not tenant_entry:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
    return success_response(tenant_entry["projects"])


@router.post("/context/switch")
async def switch_context(
    request: SwitchContextRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_async_session),
):
    access_tree = await _build_access_tree(user, db)
    context = _resolve_context(access_tree, request.tenant_id, request.project_id)
    data = {
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
        "context": context,
        "tenants": access_tree,
        "default_context": _build_default_context(access_tree),
    }
    return success_response(data, message="Context switched", code="CONTEXT_SWITCHED")
