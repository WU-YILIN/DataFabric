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


async def _register_user_and_headers(client: AsyncClient, tag: str) -> dict[str, str]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod6_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module6 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_module6_data_quality_full_flow(client: AsyncClient):
    headers = await _register_user_and_headers(client, "dq")
    suffix = _unique_suffix()
    event_code = f"evt_mod6_{suffix}"
    object_name = f"fact_mod6_{suffix}"

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"DQ Event {suffix}",
            "description": "module6 data quality event",
            "domain": "quality",
            "properties": {
                "user_id": "string",
                "order_id": "string",
                "amount": "float",
            },
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201
    event = create_event_resp.json()["data"]

    create_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"DQ Asset {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": object_name,
            "domain": "quality",
            "owner": "dq-team",
            "status": "ACTIVE",
            "tags": ["dq", "core"],
            "description": "module6 data quality table",
            "schema_definition": {
                "columns": [
                    {"name": "user_id", "type": "string"},
                    {"name": "order_id", "type": "string"},
                    {"name": "amount", "type": "float"},
                ]
            },
        },
        headers=headers,
    )
    assert create_asset_resp.status_code == 201
    asset = create_asset_resp.json()["data"]

    options_resp = await client.get("/api/v1/data-quality/rule-options", headers=headers)
    assert options_resp.status_code == 200
    options_data = options_resp.json()["data"]
    assert any(item["id"] == event["id"] for item in options_data["events"])
    assert any(item["id"] == asset["id"] for item in options_data["assets"])

    create_rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_not_null_user_id_{suffix}",
            "asset_id": asset["id"],
            "event_id": event["id"],
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.05},
            "alert_channels": ["email", "slack"],
            "severity": "HIGH",
            "status": "ACTIVE",
            "description": "user_id cannot be null",
        },
        headers=headers,
    )
    assert create_rule_resp.status_code == 201
    created_rule = create_rule_resp.json()["data"]
    rule_id = created_rule["id"]
    assert created_rule["asset_id"] == asset["id"]
    assert created_rule["event_id"] == event["id"]

    asset_detail_resp = await client.get(f"/api/v1/catalog/assets/{asset['id']}/detail", headers=headers)
    assert asset_detail_resp.status_code == 200
    asset_detail = asset_detail_resp.json()["data"]
    assert any(item["id"] == rule_id for item in asset_detail["quality"]["rules"])

    list_resp = await client.get(
        "/api/v1/data-quality/rules",
        params={
            "q": "not_null_user_id",
            "asset_id": asset["id"],
            "event_id": event["id"],
            "rule_type": "NOT_NULL",
            "severity": "HIGH",
            "status": "ACTIVE",
        },
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert any(item["id"] == rule_id for item in list_data)

    detail_before_run_resp = await client.get(f"/api/v1/data-quality/rules/{rule_id}/detail", headers=headers)
    assert detail_before_run_resp.status_code == 200
    detail_before_run = detail_before_run_resp.json()["data"]
    assert detail_before_run["rule"]["name"].startswith("dq_not_null_user_id_")
    assert detail_before_run["rule"]["asset"]["id"] == asset["id"]
    assert detail_before_run["rule"]["event"]["id"] == event["id"]
    assert detail_before_run["recent_results"] == []
    assert detail_before_run["alerts"] == []
    assert detail_before_run["version_history"] == []

    update_rule_resp = await client.patch(
        f"/api/v1/data-quality/rules/{rule_id}",
        json={
            "threshold": {"max_failure_rate": 0.01},
            "severity": "CRITICAL",
            "description": "critical not-null rule for user_id",
        },
        headers=headers,
    )
    assert update_rule_resp.status_code == 200
    updated_rule = update_rule_resp.json()["data"]
    assert updated_rule["version"] == "1.0.1"
    assert updated_rule["severity"] == "CRITICAL"
    assert updated_rule["threshold"]["max_failure_rate"] == 0.01

    fail_run_resp = await client.post(
        f"/api/v1/data-quality/rules/{rule_id}/run",
        json={
            "checked_count": 1000,
            "failed_count": 200,
            "trigger_source": "manual",
            "notes": "force fail for integration test",
        },
        headers=headers,
    )
    assert fail_run_resp.status_code == 200
    fail_run = fail_run_resp.json()["data"]
    assert fail_run["result"] == "FAIL"
    assert fail_run["failed_count"] == 200

    detail_after_fail_resp = await client.get(f"/api/v1/data-quality/rules/{rule_id}/detail", headers=headers)
    assert detail_after_fail_resp.status_code == 200
    detail_after_fail = detail_after_fail_resp.json()["data"]
    assert len(detail_after_fail["recent_results"]) >= 1
    assert detail_after_fail["recent_results"][0]["result"] == "FAIL"
    assert len(detail_after_fail["alerts"]) >= 1
    assert detail_after_fail["alerts"][0]["status"] == "OPEN"
    assert len(detail_after_fail["version_history"]) >= 1
    assert detail_after_fail["version_history"][0]["to_version"] == "1.0.1"

    overview_resp = await client.get("/api/v1/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview = overview_resp.json()["data"]
    assert any(
        alert["source_type"] == "DATA_QUALITY_RULE" and str(alert["source_id"]) == str(rule_id)
        for alert in overview["risks"]["unhandled_alerts"]
    )
    assert any(
        todo["type"] == "ALERT" and todo["target"]["type"] == "DATA_QUALITY_RULE" and todo["target"]["id"] == str(rule_id)
        for todo in overview["todos"]
    )

    pass_run_resp = await client.post(
        f"/api/v1/data-quality/rules/{rule_id}/run",
        json={
            "checked_count": 1000,
            "failed_count": 0,
            "trigger_source": "manual",
        },
        headers=headers,
    )
    assert pass_run_resp.status_code == 200
    pass_run = pass_run_resp.json()["data"]
    assert pass_run["result"] == "PASS"
    assert pass_run["failed_count"] == 0

    detail_after_pass_resp = await client.get(f"/api/v1/data-quality/rules/{rule_id}/detail", headers=headers)
    assert detail_after_pass_resp.status_code == 200
    detail_after_pass = detail_after_pass_resp.json()["data"]
    assert len(detail_after_pass["recent_results"]) >= 2
    assert detail_after_pass["recent_results"][0]["result"] == "PASS"
    assert detail_after_pass["recent_results"][1]["result"] == "FAIL"
    assert any(item["status"] == "RESOLVED" for item in detail_after_pass["alerts"])

    overview_after_pass_resp = await client.get("/api/v1/overview", headers=headers)
    assert overview_after_pass_resp.status_code == 200
    overview_after_pass = overview_after_pass_resp.json()["data"]
    assert not any(
        alert["source_type"] == "DATA_QUALITY_RULE" and str(alert["source_id"]) == str(rule_id)
        for alert in overview_after_pass["risks"]["unhandled_alerts"]
    )

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "DQ_RULE_CREATE" in actions
    assert "DQ_RULE_UPDATE" in actions
    assert "DQ_RULE_RUN_FAIL" in actions
    assert "DQ_RULE_RUN_PASS" in actions
