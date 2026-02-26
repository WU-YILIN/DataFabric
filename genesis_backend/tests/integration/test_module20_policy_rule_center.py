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


async def _register_viewer(client: AsyncClient, tag: str) -> dict[str, str]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod20_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module20 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module20_policy_rule_center_full_flow(client: AsyncClient):
    admin_headers, admin_context = await _login_admin(client)
    suffix = _unique_suffix()

    overview_resp = await client.get("/api/v1/policy/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert "summary" in overview_data
    assert "type_distribution" in overview_data

    templates_resp = await client.get("/api/v1/policy/templates", headers=admin_headers)
    assert templates_resp.status_code == 200
    templates_data = templates_resp.json()["data"]
    assert templates_data["total"] >= 1
    assert any(item["key"] == "EVENT_NAMING_STANDARD" for item in templates_data["items"])

    create_naming_resp = await client.post(
        "/api/v1/policy/rules",
        json={
            "template_key": "EVENT_NAMING_STANDARD",
            "name": f"event naming {suffix}",
            "status": "ACTIVE",
            "scope_type": "PROJECT",
            "project_id": admin_context["project_id"],
        },
        headers=admin_headers,
    )
    assert create_naming_resp.status_code == 200
    naming_rule = create_naming_resp.json()["data"]
    assert naming_rule["rule_type"] == "EVENT_NAMING"
    assert naming_rule["status"] == "ACTIVE"
    naming_rule_id = naming_rule["id"]

    create_dq_guard_resp = await client.post(
        "/api/v1/policy/rules",
        json={
            "template_key": "DQ_FAILURE_GUARD",
            "name": f"dq guard {suffix}",
            "status": "ACTIVE",
            "scope_type": "PROJECT",
            "project_id": admin_context["project_id"],
        },
        headers=admin_headers,
    )
    assert create_dq_guard_resp.status_code == 200
    dq_rule = create_dq_guard_resp.json()["data"]
    assert dq_rule["rule_type"] == "DQ_TEMPLATE"
    dq_rule_id = dq_rule["id"]

    list_resp = await client.get(
        "/api/v1/policy/rules",
        params={"rule_type": "EVENT_NAMING"},
        headers=admin_headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(item["id"] == naming_rule_id for item in list_data["items"])

    detail_resp = await client.get(f"/api/v1/policy/rules/{naming_rule_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["rule"]["id"] == naming_rule_id
    assert len(detail_data["versions"]) >= 1
    initial_version_id = detail_data["versions"][0]["id"]
    assert detail_data["versions"][0]["version_no"] == 1

    update_resp = await client.patch(
        f"/api/v1/policy/rules/{naming_rule_id}",
        json={
            "severity": "HIGH",
            "change_note": "raise severity for module20 testing",
            "conditions_payload": {
                "regex_event_name": r"^[a-z]+(\\.[a-z0-9_]+)+$",
                "modules": ["GOVERNANCE"],
            },
            "actions_payload": {
                "on_violation": "WARN",
                "recommendation": "rename event to namespace.action",
            },
            "content_payload": {
                "guidance": "module20 policy guidance",
            },
        },
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    update_data = update_resp.json()["data"]
    assert update_data["severity"] == "HIGH"
    assert update_data["version_no"] >= 2

    action_resp = await client.post(
        f"/api/v1/policy/rules/{dq_rule_id}/actions",
        json={"action": "DEACTIVATE", "change_note": "temporary disable"},
        headers=admin_headers,
    )
    assert action_resp.status_code == 200
    assert action_resp.json()["data"]["status"] == "INACTIVE"

    rollback_resp = await client.post(
        f"/api/v1/policy/rules/{naming_rule_id}/versions/{initial_version_id}/rollback",
        json={"change_note": "rollback to v1"},
        headers=admin_headers,
    )
    assert rollback_resp.status_code == 200
    rollback_data = rollback_resp.json()["data"]
    assert rollback_data["version_no"] >= 3

    evaluate_resp = await client.post(
        "/api/v1/policy/evaluate",
        json={
            "module": "GOVERNANCE",
            "action": "APPROVE",
            "context_payload": {
                "event_name": "Bad Event Name",
                "failure_rate": 0.12,
                "risk_score": 0.82,
                "fields": {"user_id": "string"},
                "domain": "core",
            },
            "include_draft": False,
            "limit": 200,
        },
        headers=admin_headers,
    )
    assert evaluate_resp.status_code == 200
    evaluate_data = evaluate_resp.json()["data"]
    assert evaluate_data["decision"] in {"WARN", "REJECT"}
    assert evaluate_data["matched_rule_count"] >= 1

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "POLICY_RULE_CREATE" in actions
    assert "POLICY_RULE_UPDATE" in actions
    assert "POLICY_RULE_ACTION" in actions
    assert "POLICY_RULE_ROLLBACK" in actions


@pytest.mark.asyncio
async def test_module20_policy_rule_center_permission_guard(client: AsyncClient):
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/policy/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/policy/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_create_resp = await client.post(
        "/api/v1/policy/rules",
        json={
            "rule_type": "EVENT_SCHEMA",
            "name": f"forbidden create {_unique_suffix()}",
            "scope_type": "PROJECT",
            "status": "DRAFT",
            "conditions_payload": {"required_fields": ["user_id"]},
        },
        headers=viewer_headers,
    )
    assert viewer_create_resp.status_code == 403
