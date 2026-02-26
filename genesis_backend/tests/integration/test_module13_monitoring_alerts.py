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


async def _register_user(client: AsyncClient, tag: str) -> dict[str, str]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod13_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module13 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module13_monitoring_alerts_full_flow(client: AsyncClient):
    headers = await _register_user(client, "flow")
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod13_{suffix}",
            "name": f"Monitoring Event {suffix}",
            "description": "module13 monitoring event",
            "domain": "monitoring",
            "owner": "mod13-owner",
            "properties": {"user_id": "string"},
        },
        headers=headers,
    )
    assert event_resp.status_code == 201
    event = event_resp.json()["data"]

    asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Monitoring Asset {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"mod13_asset_{suffix}",
            "domain": "monitoring",
            "owner": "mod13-owner",
            "status": "ACTIVE",
            "tags": ["module13"],
            "description": "module13 monitoring asset",
            "schema_definition": {"columns": [{"name": "user_id", "type": "string"}]},
        },
        headers=headers,
    )
    assert asset_resp.status_code == 201
    asset = asset_resp.json()["data"]

    rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_mod13_{suffix}",
            "asset_id": asset["id"],
            "event_id": event["id"],
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.01},
            "alert_channels": ["email"],
            "severity": "HIGH",
            "status": "ACTIVE",
            "description": "module13 monitoring rule",
        },
        headers=headers,
    )
    assert rule_resp.status_code == 201
    rule = rule_resp.json()["data"]

    run_fail_resp = await client.post(
        f"/api/v1/data-quality/rules/{rule['id']}/run",
        json={
            "checked_count": 1000,
            "failed_count": 300,
            "trigger_source": "manual",
            "notes": "force fail for module13",
        },
        headers=headers,
    )
    assert run_fail_resp.status_code == 200
    assert run_fail_resp.json()["data"]["result"] == "FAIL"

    overview_resp = await client.get(
        "/api/v1/monitoring/overview",
        params={"modules": "DQ", "window_minutes": 180},
        headers=headers,
    )
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert overview_data["summary"]["open_alerts"] >= 1
    assert len(overview_data["trends"]) > 0
    assert any(item["module"] == "DQ" for item in overview_data["module_health"])

    list_resp = await client.get(
        "/api/v1/monitoring/alerts",
        params={"source_module": "DQ", "status": "OPEN", "limit": 20},
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    first_alert = list_data["items"][0]
    assert first_alert["source_module"] == "DQ"
    alert_id = first_alert["id"]

    detail_resp = await client.get(f"/api/v1/monitoring/alerts/{alert_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["metadata"]["source_module"] == "DQ"
    assert len(detail_data["context_metrics"]["timeline"]) > 0

    claim_resp = await client.post(
        f"/api/v1/monitoring/alerts/{alert_id}/actions",
        json={"action": "CLAIM", "note": "taking ownership"},
        headers=headers,
    )
    assert claim_resp.status_code == 200
    assert claim_resp.json()["data"]["alert"]["status"] == "ACKNOWLEDGED"

    note_resp = await client.post(
        f"/api/v1/monitoring/alerts/{alert_id}/actions",
        json={"action": "NOTE", "note": "investigation running"},
        headers=headers,
    )
    assert note_resp.status_code == 200
    assert note_resp.json()["data"]["alert"]["last_note"] == "investigation running"

    resolve_resp = await client.post(
        f"/api/v1/monitoring/alerts/{alert_id}/actions",
        json={"action": "RESOLVE", "note": "issue fixed"},
        headers=headers,
    )
    assert resolve_resp.status_code == 200
    resolved_alert = resolve_resp.json()["data"]["alert"]
    assert resolved_alert["status"] == "RESOLVED"
    assert resolved_alert["resolved_at"] is not None

    detail_after_resp = await client.get(f"/api/v1/monitoring/alerts/{alert_id}", headers=headers)
    assert detail_after_resp.status_code == 200
    detail_after = detail_after_resp.json()["data"]
    actions = [item["action"] for item in detail_after["history"]]
    assert "CLAIM" in actions
    assert "NOTE" in actions
    assert "RESOLVE" in actions

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    audit_actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "ALERT_CLAIM" in audit_actions
    assert "ALERT_NOTE" in audit_actions
    assert "ALERT_RESOLVE" in audit_actions


@pytest.mark.asyncio
async def test_module13_monitoring_alert_note_requires_text(client: AsyncClient):
    headers = await _register_user(client, "note")
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod13_note_{suffix}",
            "name": f"Monitoring Event Note {suffix}",
            "description": "module13 note event",
            "domain": "monitoring",
            "properties": {"user_id": "string"},
        },
        headers=headers,
    )
    assert event_resp.status_code == 201
    event = event_resp.json()["data"]

    rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_mod13_note_{suffix}",
            "event_id": event["id"],
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.01},
            "alert_channels": ["email"],
            "severity": "HIGH",
            "status": "ACTIVE",
        },
        headers=headers,
    )
    assert rule_resp.status_code == 201
    rule = rule_resp.json()["data"]

    run_fail_resp = await client.post(
        f"/api/v1/data-quality/rules/{rule['id']}/run",
        json={"checked_count": 1000, "failed_count": 100, "trigger_source": "manual"},
        headers=headers,
    )
    assert run_fail_resp.status_code == 200

    list_resp = await client.get(
        "/api/v1/monitoring/alerts",
        params={"source_module": "DQ", "status": "OPEN", "limit": 1},
        headers=headers,
    )
    assert list_resp.status_code == 200
    alert_id = list_resp.json()["data"]["items"][0]["id"]

    invalid_note_resp = await client.post(
        f"/api/v1/monitoring/alerts/{alert_id}/actions",
        json={"action": "NOTE"},
        headers=headers,
    )
    assert invalid_note_resp.status_code == 400
