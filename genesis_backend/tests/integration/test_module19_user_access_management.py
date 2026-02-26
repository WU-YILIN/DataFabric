import time

import pytest
from httpx import AsyncClient


def _unique_suffix() -> str:
    return str(time.time_ns())


def _context_headers(access_token: str, context: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


async def _login_admin(client: AsyncClient) -> tuple[dict[str, str], dict]:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@demo.local",
            "password": "demo123456",
        },
    )
    assert login_resp.status_code == 200
    data = login_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"]), data["default_context"]


async def _register_user(client: AsyncClient, tag: str) -> tuple[dict[str, str], str]:
    suffix = _unique_suffix()
    email = f"it_mod19_{tag}_{suffix}@demo.local"
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "demo123456",
            "name": f"Module19 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"]), email


@pytest.mark.asyncio
async def test_module19_access_management_full_flow(client: AsyncClient):
    admin_headers, admin_context = await _login_admin(client)
    suffix = _unique_suffix()
    invited_email = f"it_mod19_invited_{suffix}@demo.local"

    overview_resp = await client.get("/api/v1/access/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert overview_data["summary"]["total_users"] >= 1
    assert "recent_security_activity" in overview_data

    list_resp = await client.get("/api/v1/access/users", headers=admin_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1

    invite_resp = await client.post(
        "/api/v1/access/users/invite",
        json={
            "email": invited_email,
            "tenant_role": "MEMBER",
            "project_role": "EDITOR",
            "expires_in_hours": 72,
        },
        headers=admin_headers,
    )
    assert invite_resp.status_code == 200
    invite_data = invite_resp.json()["data"]
    assert invite_data["mode"] == "invitation_sent"
    assert invite_data["pending_invitation"]["project_role"] == "EDITOR"

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": invited_email,
            "password": "demo123456",
            "name": f"Invited {suffix}",
        },
    )
    assert register_resp.status_code == 200

    list_by_email_resp = await client.get(
        "/api/v1/access/users",
        params={"q": invited_email},
        headers=admin_headers,
    )
    assert list_by_email_resp.status_code == 200
    list_by_email_data = list_by_email_resp.json()["data"]
    assert list_by_email_data["total"] >= 1
    invited_user = next((item for item in list_by_email_data["items"] if item["email"] == invited_email), None)
    assert invited_user is not None
    invited_user_id = invited_user["user_id"]

    detail_resp = await client.get(f"/api/v1/access/users/{invited_user_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["user"]["email"] == invited_email
    assert len(detail_data["user"]["project_roles"]) >= 1

    role_update_resp = await client.patch(
        f"/api/v1/access/users/{invited_user_id}/roles",
        json={
            "tenant_role_action": "UPSERT",
            "tenant_role": "MEMBER",
            "project_roles": [
                {
                    "project_id": admin_context["project_id"],
                    "action": "UPSERT",
                    "role": "APPROVER",
                }
            ],
        },
        headers=admin_headers,
    )
    assert role_update_resp.status_code == 200
    role_update_data = role_update_resp.json()["data"]
    assert any(item["role"] == "APPROVER" for item in role_update_data["project_roles"])

    status_off_resp = await client.patch(
        f"/api/v1/access/users/{invited_user_id}/status",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert status_off_resp.status_code == 200
    assert status_off_resp.json()["data"]["is_active"] is False

    status_on_resp = await client.patch(
        f"/api/v1/access/users/{invited_user_id}/status",
        json={"is_active": True},
        headers=admin_headers,
    )
    assert status_on_resp.status_code == 200
    assert status_on_resp.json()["data"]["is_active"] is True

    templates_resp = await client.get("/api/v1/access/role-templates", headers=admin_headers)
    assert templates_resp.status_code == 200
    templates_data = templates_resp.json()["data"]
    assert templates_data["total"] >= 1
    assert any(item["template_key"] == "ADMIN" for item in templates_data["items"])

    custom_template_resp = await client.put(
        "/api/v1/access/role-templates/GOVERNANCE_SPECIALIST",
        json={
            "name": "治理专员增强版",
            "description": "module19 test template",
            "permission_matrix": {
                "modules": {
                    "GOVERNANCE": ["VIEW", "APPROVE"],
                    "AUDIT_LOGS": ["VIEW"],
                }
            },
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert custom_template_resp.status_code == 200
    assert custom_template_resp.json()["data"]["template_key"] == "GOVERNANCE_SPECIALIST"

    evaluate_allow_resp = await client.post(
        "/api/v1/access/evaluate",
        json={
            "user_id": invited_user_id,
            "module": "GOVERNANCE",
            "action": "APPROVE",
            "project_id": admin_context["project_id"],
        },
        headers=admin_headers,
    )
    assert evaluate_allow_resp.status_code == 200
    evaluate_allow_data = evaluate_allow_resp.json()["data"]
    assert evaluate_allow_data["allow"] is True

    evaluate_deny_resp = await client.post(
        "/api/v1/access/evaluate",
        json={
            "user_id": invited_user_id,
            "module": "EVENTS",
            "action": "DELETE",
            "project_id": admin_context["project_id"],
        },
        headers=admin_headers,
    )
    assert evaluate_deny_resp.status_code == 200
    assert evaluate_deny_resp.json()["data"]["allow"] is False

    delete_template_resp = await client.delete(
        "/api/v1/access/role-templates/GOVERNANCE_SPECIALIST",
        headers=admin_headers,
    )
    assert delete_template_resp.status_code == 200
    assert delete_template_resp.json()["data"]["deleted"] is True

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "ACCESS_USER_INVITE" in actions
    assert "ACCESS_USER_ROLE_UPDATE" in actions
    assert "ACCESS_USER_STATUS_UPDATE" in actions
    assert "ACCESS_ROLE_TEMPLATE_SAVE" in actions
    assert "ACCESS_ROLE_TEMPLATE_DELETE" in actions


@pytest.mark.asyncio
async def test_module19_access_management_permission_guard(client: AsyncClient):
    member_headers, _ = await _register_user(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/access/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    overview_resp = await client.get("/api/v1/access/overview", headers=member_headers)
    assert overview_resp.status_code == 403

    invite_resp = await client.post(
        "/api/v1/access/users/invite",
        json={
            "email": f"it_mod19_forbidden_{_unique_suffix()}@demo.local",
            "tenant_role": "MEMBER",
            "project_role": "VIEWER",
        },
        headers=member_headers,
    )
    assert invite_resp.status_code == 403
