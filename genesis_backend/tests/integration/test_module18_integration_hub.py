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


async def _register_viewer(client: AsyncClient, tag: str) -> dict[str, str]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod18_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module18 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module18_integration_hub_full_flow(client: AsyncClient):
    admin_headers = await _login_admin(client)
    integration_type = "WEBHOOK"

    overview_resp = await client.get("/api/v1/integration-hub/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert "summary" in overview_data
    assert "items" in overview_data
    assert len(overview_data["items"]) >= 1

    list_resp = await client.get("/api/v1/integration-hub/integrations", headers=admin_headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert integration_type in list_data["facets"]["types"]

    detail_resp = await client.get(
        f"/api/v1/integration-hub/integrations/{integration_type}",
        headers=admin_headers,
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["integration"]["integration_type"] == integration_type
    assert "endpoint" in detail_data["template"]

    test_invalid_resp = await client.post(
        "/api/v1/integration-hub/test",
        json={"integration_type": integration_type, "config": {}},
        headers=admin_headers,
    )
    assert test_invalid_resp.status_code == 200
    test_invalid_data = test_invalid_resp.json()["data"]
    assert test_invalid_data["status"] == "FAILURE"
    assert test_invalid_data["error_code"] == "INVALID_ENDPOINT"

    save_disabled_resp = await client.put(
        f"/api/v1/integration-hub/integrations/{integration_type}",
        json={
            "enabled": False,
            "config": {},
        },
        headers=admin_headers,
    )
    assert save_disabled_resp.status_code == 200
    assert save_disabled_resp.json()["data"]["enabled"] is False

    invoke_disabled_resp = await client.post(
        f"/api/v1/integration-hub/integrations/{integration_type}/invoke",
        json={
            "caller_module": "ALERTS",
            "action": "SEND_NOTIFICATION",
            "payload": {"title": "mod18 disabled invoke"},
        },
        headers=admin_headers,
    )
    assert invoke_disabled_resp.status_code == 200
    invoke_disabled_data = invoke_disabled_resp.json()["data"]
    assert invoke_disabled_data["status"] == "FAILURE"
    assert invoke_disabled_data["error_code"] == "INTEGRATION_DISABLED"
    assert invoke_disabled_data["alert_id"] is not None
    disabled_alert_id = invoke_disabled_data["alert_id"]

    save_enabled_resp = await client.put(
        f"/api/v1/integration-hub/integrations/{integration_type}",
        json={
            "enabled": True,
            "config": {
                "endpoint": "https://hooks.example.com/events",
                "secret": "mod18-webhook-secret",
            },
        },
        headers=admin_headers,
    )
    assert save_enabled_resp.status_code == 200
    save_enabled_data = save_enabled_resp.json()["data"]
    assert save_enabled_data["enabled"] is True
    assert save_enabled_data["has_stored_secret"] is True
    assert "mod18-webhook-secret" not in str(save_enabled_data["config"])

    invoke_success_resp = await client.post(
        f"/api/v1/integration-hub/integrations/{integration_type}/invoke",
        json={
            "caller_module": "ALERTS",
            "action": "SEND_NOTIFICATION",
            "payload": {"title": "mod18 success invoke"},
        },
        headers=admin_headers,
    )
    assert invoke_success_resp.status_code == 200
    invoke_success_data = invoke_success_resp.json()["data"]
    assert invoke_success_data["status"] == "SUCCESS"
    assert invoke_success_data["external_request_id"].startswith("ext_webhook_")

    invoke_failure_resp = await client.post(
        f"/api/v1/integration-hub/integrations/{integration_type}/invoke",
        json={
            "caller_module": "ALERTS",
            "action": "SEND_NOTIFICATION",
            "payload": {"title": "mod18 simulated failure"},
            "simulate_failure": True,
            "error_code": "DOWNSTREAM_TIMEOUT",
            "note": "simulated from integration test",
        },
        headers=admin_headers,
    )
    assert invoke_failure_resp.status_code == 200
    invoke_failure_data = invoke_failure_resp.json()["data"]
    assert invoke_failure_data["status"] == "FAILURE"
    assert invoke_failure_data["error_code"] == "DOWNSTREAM_TIMEOUT"
    assert invoke_failure_data["alert_id"] is not None

    filtered_resp = await client.get(
        "/api/v1/integration-hub/integrations",
        params={"integration_type": integration_type},
        headers=admin_headers,
    )
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()["data"]
    assert filtered_data["total"] == 1
    assert filtered_data["items"][0]["integration_type"] == integration_type

    alerts_resp = await client.get(
        "/api/v1/monitoring/alerts",
        params={"q": integration_type, "limit": 200},
        headers=admin_headers,
    )
    assert alerts_resp.status_code == 200
    alerts = alerts_resp.json()["data"]["items"]
    assert any(item["id"] == disabled_alert_id for item in alerts)
    assert any(item["source_type"] == "INTEGRATION" for item in alerts)

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "INTEGRATION_HUB_TEST" in actions
    assert "INTEGRATION_HUB_SAVE" in actions
    assert "INTEGRATION_HUB_INVOKE_SUCCESS" in actions
    assert "INTEGRATION_HUB_INVOKE_FAILURE" in actions


@pytest.mark.asyncio
async def test_module18_integration_hub_permissions_and_auth_mode(client: AsyncClient):
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/integration-hub/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/integration-hub/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_list_resp = await client.get("/api/v1/integration-hub/integrations", headers=viewer_headers)
    assert viewer_list_resp.status_code == 200

    viewer_test_resp = await client.post(
        "/api/v1/integration-hub/test",
        json={"integration_type": "WEBHOOK", "config": {"endpoint": "https://hooks.example.com/events"}},
        headers=viewer_headers,
    )
    assert viewer_test_resp.status_code == 403

    viewer_save_resp = await client.put(
        "/api/v1/integration-hub/integrations/WEBHOOK",
        json={"enabled": False, "config": {"endpoint": "https://hooks.example.com/events"}},
        headers=viewer_headers,
    )
    assert viewer_save_resp.status_code == 403
