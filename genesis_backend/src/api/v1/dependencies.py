from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.domain.auth.security import decode_access_token
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.user import User, UserProjectRole, UserTenantRole
from src.infrastructure.database.repositories.project_repo import ProjectRepository
from src.infrastructure.database.session import get_async_session

API_KEY_NAME = "X-API-KEY"
PROJECT_ID_HEADER = "X-PROJECT-ID"
TENANT_ID_HEADER = "X-TENANT-ID"
TENANT_ELEVATED_ROLES = {"OWNER", "ADMIN"}

api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass
class RequestContext:
    auth_mode: str
    project: Project
    user: User | None = None
    tenant_role: str | None = None
    project_role: str | None = None

    @property
    def actor_id(self) -> str:
        if self.user:
            return f"user:{self.user.email}|project:{self.project.id}"
        return f"project:{self.project.id}"


def _raise_auth_error(detail: str) -> None:
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def _resolve_user_from_token(
    credentials: HTTPAuthorizationCredentials | None,
    db: AsyncSession,
) -> User:
    if not credentials:
        _raise_auth_error("Missing bearer token")
    if credentials.scheme.lower() != "bearer":
        _raise_auth_error("Invalid authorization scheme")

    try:
        payload = decode_access_token(credentials.credentials, settings.AUTH_SECRET_KEY)
    except ValueError as exc:
        _raise_auth_error(str(exc))

    user_id = payload.get("sub")
    if not isinstance(user_id, int):
        _raise_auth_error("Invalid token subject")

    query = select(User).where(User.id == user_id, User.is_active.is_(True))
    result = await db.execute(query)
    user = result.scalar_one_or_none()
    if not user:
        _raise_auth_error("User not found or inactive")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: AsyncSession = Depends(get_async_session),
) -> User:
    return await _resolve_user_from_token(credentials, db)


async def _resolve_user_project_context(
    *,
    db: AsyncSession,
    user: User,
    project_id: int,
    tenant_id: int | None,
) -> RequestContext:
    project_repo = ProjectRepository(db)
    project = await project_repo.get(project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")

    if tenant_id is not None and project.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Project does not belong to current tenant",
        )

    project_role_result = await db.execute(
        select(UserProjectRole.role).where(
            UserProjectRole.user_id == user.id,
            UserProjectRole.project_id == project.id,
        )
    )
    project_role = project_role_result.scalar_one_or_none()

    tenant_role = None
    if project.tenant_id is not None:
        tenant_role_result = await db.execute(
            select(UserTenantRole.role).where(
                UserTenantRole.user_id == user.id,
                UserTenantRole.tenant_id == project.tenant_id,
            )
        )
        tenant_role = tenant_role_result.scalar_one_or_none()

    is_allowed = bool(project_role) or (tenant_role in TENANT_ELEVATED_ROLES)
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No permission for current project",
        )

    return RequestContext(
        auth_mode="bearer",
        project=project,
        user=user,
        tenant_role=tenant_role,
        project_role=project_role,
    )


async def get_request_context(
    api_key: str | None = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    x_project_id: int | None = Header(default=None, alias=PROJECT_ID_HEADER),
    x_tenant_id: int | None = Header(default=None, alias=TENANT_ID_HEADER),
    db: AsyncSession = Depends(get_async_session),
) -> RequestContext:
    if api_key:
        project_repo = ProjectRepository(db)
        project = await project_repo.get_by_api_key(api_key)
        if project:
            return RequestContext(auth_mode="api_key", project=project)
        if not credentials:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Could not validate API key",
            )

    if not credentials:
        _raise_auth_error("Missing credentials")
    if x_project_id is None:
        _raise_auth_error("Missing X-PROJECT-ID header")

    user = await _resolve_user_from_token(credentials, db)
    return await _resolve_user_project_context(
        db=db,
        user=user,
        project_id=x_project_id,
        tenant_id=x_tenant_id,
    )


async def get_current_project(
    context: RequestContext = Depends(get_request_context),
) -> Project:
    return context.project
