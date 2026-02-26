import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.user import User, UserProjectRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import async_session_factory


def _unique_suffix() -> str:
    return str(time.time_ns())


async def _create_project(tenant_id: int, name_prefix: str) -> Project:
    suffix = _unique_suffix()
    async with async_session_factory() as session:
        repo = BaseRepository(Project, session)
        project = await repo.create(
            {
                "tenant_id": tenant_id,
                "name": f"{name_prefix}_{suffix}",
                "api_key": f"{name_prefix}-key-{suffix}",
                "description": "module12 project",
                "tags": ["module12"],
                "default_domain": "module12",
                "tech_stack": {"mode": "test"},
            }
        )
        await session.commit()
        return project


async def _assign_project_role(email: str, project_id: int, role: str) -> None:
    async with async_session_factory() as session:
        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one_or_none()
        assert user is not None

        role_result = await session.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == user.id,
                UserProjectRole.project_id == project_id,
            )
        )
        role_row = role_result.scalar_one_or_none()
        role_repo = BaseRepository(UserProjectRole, session)
        if role_row:
            await role_repo.update(role_row, {"role": role})
        else:
            await role_repo.create(
                {
                    "user_id": user.id,
                    "project_id": project_id,
                    "role": role,
                }
            )
        await session.commit()


@pytest.mark.asyncio
async def test_module12_context_switch_for_elevated_tenant_role(client: AsyncClient):
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@demo.local", "password": "demo123456"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()["data"]
    access_token = login_data["access_token"]
    default_context = login_data["default_context"]
    assert default_context is not None
    tenant_id = default_context["tenant_id"]

    extra_project = await _create_project(tenant_id, "mod12_admin_project")

    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    tenant_entry = next((item for item in me_data["tenants"] if item["id"] == tenant_id), None)
    assert tenant_entry is not None
    assert any(item["id"] == extra_project.id for item in tenant_entry["projects"])

    switch_resp = await client.post(
        "/api/v1/auth/context/switch",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "tenant_id": tenant_id,
            "project_id": extra_project.id,
        },
    )
    assert switch_resp.status_code == 200
    switch_data = switch_resp.json()["data"]
    assert switch_data["context"]["tenant_id"] == tenant_id
    assert switch_data["context"]["project_id"] == extra_project.id

    overview_resp = await client.get(
        "/api/v1/overview",
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-TENANT-ID": str(tenant_id),
            "X-PROJECT-ID": str(extra_project.id),
        },
    )
    assert overview_resp.status_code == 200


@pytest.mark.asyncio
async def test_module12_project_visibility_filter_and_switch_permission(client: AsyncClient):
    admin_login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@demo.local", "password": "demo123456"},
    )
    assert admin_login_resp.status_code == 200
    admin_data = admin_login_resp.json()["data"]
    tenant_id = admin_data["default_context"]["tenant_id"]

    allowed_project = await _create_project(tenant_id, "mod12_allowed_project")
    blocked_project = await _create_project(tenant_id, "mod12_blocked_project")

    suffix = _unique_suffix()
    user_email = f"it_mod12_user_{suffix}@demo.local"
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": user_email,
            "password": "demo123456",
            "name": f"Module12 User {suffix}",
            "project_id": allowed_project.id,
        },
    )
    assert register_resp.status_code == 200

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": "demo123456"},
    )
    assert login_resp.status_code == 200
    user_token = login_resp.json()["data"]["access_token"]

    projects_resp = await client.get(
        "/api/v1/auth/projects",
        params={"tenant_id": tenant_id},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert projects_resp.status_code == 200
    projects = projects_resp.json()["data"]
    assert any(item["id"] == allowed_project.id for item in projects)
    assert all(item["id"] != blocked_project.id for item in projects)

    forbidden_switch_resp = await client.post(
        "/api/v1/auth/context/switch",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "tenant_id": tenant_id,
            "project_id": blocked_project.id,
        },
    )
    assert forbidden_switch_resp.status_code == 404

    await _assign_project_role(user_email, blocked_project.id, "EDITOR")

    allowed_switch_resp = await client.post(
        "/api/v1/auth/context/switch",
        headers={"Authorization": f"Bearer {user_token}"},
        json={
            "tenant_id": tenant_id,
            "project_id": blocked_project.id,
        },
    )
    assert allowed_switch_resp.status_code == 200
    context = allowed_switch_resp.json()["data"]["context"]
    assert context["project_id"] == blocked_project.id
    assert context["project_role"] == "EDITOR"
