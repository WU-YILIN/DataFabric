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
            "email": f"it_mod21_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module21 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module21_ingestion_sdk_center_full_flow(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    suffix = _unique_suffix()

    overview_resp = await client.get("/api/v1/ingestion/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert "summary" in overview_data

    options_resp = await client.get("/api/v1/ingestion/options", headers=admin_headers)
    assert options_resp.status_code == 200
    options_data = options_resp.json()["data"]
    assert "WEB" in options_data["platforms"]
    assert "PROD" in options_data["environments"]

    create_resp = await client.post(
        "/api/v1/ingestion/channels",
        json={
            "platform": "WEB",
            "app_name": f"checkout_{suffix}",
            "environment": "PROD",
            "status": "ACTIVE",
            "endpoint_domain": "ingest.demo.local",
            "sampling_mode": "ALL",
            "sampling_rate": 1.0,
            "switches_payload": {
                "enable_schema_check": True,
                "enable_realtime_governance": True,
                "enable_dq_hook": False,
            },
            "blocked_events": ["commerce.blocked_event"],
            "sdk_version": "1.2.3",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()["data"]
    channel = create_data["channel"]
    channel_id = channel["id"]
    app_id = channel["app_id"]
    ingest_key = create_data["generated_ingest_key"]
    assert channel["platform"] == "WEB"
    assert ingest_key.startswith("ing_")
    assert "snippet" in create_data["quickstart"]

    list_resp = await client.get(
        "/api/v1/ingestion/channels",
        params={"platform": "WEB"},
        headers=admin_headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(item["id"] == channel_id for item in list_data["items"])

    detail_resp = await client.get(f"/api/v1/ingestion/channels/{channel_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["channel"]["id"] == channel_id
    assert detail_data["channel"]["ingest_key"] != ingest_key
    assert detail_data["quickstart"]["sample_payload"]["app_id"] == app_id

    update_resp = await client.patch(
        f"/api/v1/ingestion/channels/{channel_id}",
        json={
            "sampling_mode": "ALL",
            "sampling_rate": 1.0,
            "blocked_events": ["commerce.blocked_event", "commerce.another_blocked"],
            "status": "ACTIVE",
        },
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    update_data = update_resp.json()["data"]
    assert "commerce.blocked_event" in update_data["channel"]["blocked_events"]

    rotate_resp = await client.post(
        f"/api/v1/ingestion/channels/{channel_id}/rotate-key",
        json={"reason": "module21 rotate"},
        headers=admin_headers,
    )
    assert rotate_resp.status_code == 200
    rotate_data = rotate_resp.json()["data"]
    new_ingest_key = rotate_data["generated_ingest_key"]
    assert new_ingest_key != ingest_key

    old_key_ingest_resp = await client.post(
        "/api/v1/ingestion/gateway/events",
        json={
            "app_id": app_id,
            "event_name": "commerce.order_created",
            "payload": {"order_id": "o_1001"},
        },
        headers={"X-INGEST-KEY": ingest_key},
    )
    assert old_key_ingest_resp.status_code == 401

    accepted_ingest_resp = await client.post(
        "/api/v1/ingestion/gateway/events",
        json={
            "app_id": app_id,
            "event_name": "commerce.order_created",
            "event_ts": "2026-01-01T10:00:00+00:00",
            "sdk_version": "1.2.3",
            "payload": {"order_id": "o_1001", "user_id": "u_1001"},
        },
        headers={"X-INGEST-KEY": new_ingest_key},
    )
    assert accepted_ingest_resp.status_code == 200
    accepted_data = accepted_ingest_resp.json()["data"]
    assert accepted_data["status"] == "ACCEPTED"
    assert len(accepted_data["next_modules"]) >= 1

    blocked_ingest_resp = await client.post(
        "/api/v1/ingestion/gateway/events",
        json={
            "app_id": app_id,
            "event_name": "commerce.blocked_event",
            "payload": {"order_id": "o_1002"},
        },
        headers={"X-INGEST-KEY": new_ingest_key},
    )
    assert blocked_ingest_resp.status_code == 200
    blocked_data = blocked_ingest_resp.json()["data"]
    assert blocked_data["status"] == "REJECTED"
    assert blocked_data["reason_code"] == "BLOCKED_EVENT"
    assert blocked_data["alert_id"] is not None

    invalid_name_resp = await client.post(
        "/api/v1/ingestion/gateway/events",
        json={
            "app_id": app_id,
            "event_name": "Bad Event Name",
            "payload": {"x": 1},
        },
        headers={"X-INGEST-KEY": new_ingest_key},
    )
    assert invalid_name_resp.status_code == 200
    invalid_name_data = invalid_name_resp.json()["data"]
    assert invalid_name_data["status"] == "REJECTED"
    assert invalid_name_data["reason_code"] == "INVALID_EVENT_NAME"

    alerts_resp = await client.get(
        "/api/v1/monitoring/alerts",
        params={"q": app_id, "limit": 200},
        headers=admin_headers,
    )
    assert alerts_resp.status_code == 200
    alert_items = alerts_resp.json()["data"]["items"]
    assert any(item["source_type"] == "INGESTION" for item in alert_items)

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "INGESTION_CHANNEL_CREATE" in actions
    assert "INGESTION_CHANNEL_UPDATE" in actions
    assert "INGESTION_CHANNEL_ROTATE_KEY" in actions


@pytest.mark.asyncio
async def test_module21_ingestion_sdk_center_permission_guard(client: AsyncClient):
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/ingestion/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/ingestion/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_create_resp = await client.post(
        "/api/v1/ingestion/channels",
        json={
            "platform": "WEB",
            "app_name": f"forbidden_{_unique_suffix()}",
            "environment": "PROD",
        },
        headers=viewer_headers,
    )
    assert viewer_create_resp.status_code == 403

    missing_key_resp = await client.post(
        "/api/v1/ingestion/gateway/events",
        json={"app_id": "aa", "event_name": "commerce.order_created", "payload": {}},
    )
    assert missing_key_resp.status_code == 401
