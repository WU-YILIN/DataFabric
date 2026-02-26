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


async def _login_admin(client: AsyncClient) -> dict[str, str]:
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
    return _context_headers(data["access_token"], data["default_context"])


async def _register_user(client: AsyncClient, tag: str) -> tuple[dict[str, str], str]:
    suffix = _unique_suffix()
    email = f"it_mod11_{tag}_{suffix}@demo.local"
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "demo123456",
            "name": f"Module11 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"]), email


@pytest.mark.asyncio
async def test_module11_settings_full_flow(client: AsyncClient):
    admin_headers = await _login_admin(client)
    member_headers, member_email = await _register_user(client, "member")

    overview_resp = await client.get("/api/v1/settings", headers=admin_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert "general" in overview_data
    assert "members" in overview_data
    assert "integrations" in overview_data
    assert "security" in overview_data
    assert overview_data["permissions"]["can_manage_members"] is True

    forbidden_general_resp = await client.patch(
        "/api/v1/settings/general",
        json={"description": "forbidden update from viewer"},
        headers=member_headers,
    )
    assert forbidden_general_resp.status_code == 403

    general_resp = await client.patch(
        "/api/v1/settings/general",
        json={
            "description": "module11 settings integration test",
            "tags": ["module11", "settings"],
            "default_domain": "module11",
        },
        headers=admin_headers,
    )
    assert general_resp.status_code == 200
    general_data = general_resp.json()["data"]
    assert general_data["description"] == "module11 settings integration test"
    assert "module11" in general_data["tags"]

    invite_resp = await client.post(
        "/api/v1/settings/members/invite",
        json={
            "email": member_email,
            "role": "EDITOR",
        },
        headers=admin_headers,
    )
    assert invite_resp.status_code == 200
    invite_data = invite_resp.json()["data"]
    assert invite_data["mode"] == "member_updated"
    assert invite_data["member"]["project_role"] == "EDITOR"

    members_resp = await client.get("/api/v1/settings/members", headers=admin_headers)
    assert members_resp.status_code == 200
    members_data = members_resp.json()["data"]["items"]
    member_item = next((item for item in members_data if item["email"] == member_email), None)
    assert member_item is not None
    assert member_item["project_role"] == "EDITOR"
    member_user_id = member_item["user_id"]

    update_role_resp = await client.patch(
        f"/api/v1/settings/members/{member_user_id}/role",
        json={"role": "APPROVER"},
        headers=admin_headers,
    )
    assert update_role_resp.status_code == 200
    assert update_role_resp.json()["data"]["project_role"] == "APPROVER"

    test_integration_fail_resp = await client.post(
        "/api/v1/settings/integrations/test",
        json={
            "integration_type": "LLM",
            "config": {"api_key": "invalid"},
        },
        headers=admin_headers,
    )
    assert test_integration_fail_resp.status_code == 200
    assert test_integration_fail_resp.json()["data"]["status"] == "FAILURE"

    save_disabled_integration_resp = await client.put(
        "/api/v1/settings/integrations/LLM",
        json={
            "enabled": False,
            "config": {"api_key": "invalid"},
        },
        headers=admin_headers,
    )
    assert save_disabled_integration_resp.status_code == 200
    assert save_disabled_integration_resp.json()["data"]["enabled"] is False

    save_enabled_fail_resp = await client.put(
        "/api/v1/settings/integrations/LLM",
        json={
            "enabled": True,
            "config": {"api_key": "invalid"},
        },
        headers=admin_headers,
    )
    assert save_enabled_fail_resp.status_code == 400

    save_enabled_success_resp = await client.put(
        "/api/v1/settings/integrations/LLM",
        json={
            "enabled": True,
            "config": {"api_key": "sk-module11-valid"},
        },
        headers=admin_headers,
    )
    assert save_enabled_success_resp.status_code == 200
    llm_data = save_enabled_success_resp.json()["data"]
    assert llm_data["enabled"] is True
    assert "sk-module11-valid" not in str(llm_data["config"])

    forbidden_security_resp = await client.patch(
        "/api/v1/settings/security",
        json={
            "sso_enabled": True,
        },
        headers=member_headers,
    )
    assert forbidden_security_resp.status_code == 403

    security_resp = await client.patch(
        "/api/v1/settings/security",
        json={
            "sso_enabled": True,
            "mfa_required": True,
            "password_min_length": 12,
            "audit_log_retention_days": 365,
            "max_exports_per_day": 50,
        },
        headers=admin_headers,
    )
    assert security_resp.status_code == 200
    security_data = security_resp.json()["data"]
    assert security_data["sso_enabled"] is True
    assert security_data["mfa_required"] is True
    assert security_data["password_policy"]["min_length"] == 12
    assert security_data["audit_policy"]["retention_days"] == 365
    assert security_data["audit_policy"]["max_exports_per_day"] == 50

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "SETTINGS_GENERAL_UPDATE" in actions
    assert "SETTINGS_MEMBER_UPSERT" in actions
    assert "SETTINGS_INTEGRATION_SAVE" in actions
    assert "SETTINGS_SECURITY_UPDATE" in actions


@pytest.mark.asyncio
async def test_module11_invitation_role_applies_on_register(client: AsyncClient):
    admin_headers = await _login_admin(client)
    suffix = _unique_suffix()
    invited_email = f"it_mod11_invited_{suffix}@demo.local"
    invited_name = f"Invited {suffix}"

    invite_resp = await client.post(
        "/api/v1/settings/members/invite",
        json={
            "email": invited_email,
            "name": invited_name,
            "role": "ADMIN",
        },
        headers=admin_headers,
    )
    assert invite_resp.status_code == 200
    invite_data = invite_resp.json()["data"]
    assert invite_data["mode"] == "invitation_sent"
    assert invite_data["pending_invitation"]["role"] == "ADMIN"

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": invited_email,
            "password": "demo123456",
            "name": invited_name,
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    default_context = register_data["default_context"]
    assert default_context is not None
    headers = _context_headers(register_data["access_token"], default_context)

    settings_resp = await client.get("/api/v1/settings", headers=headers)
    assert settings_resp.status_code == 200
    permissions = settings_resp.json()["data"]["permissions"]
    assert permissions["can_manage_members"] is True
    assert permissions["can_manage_integrations"] is True
