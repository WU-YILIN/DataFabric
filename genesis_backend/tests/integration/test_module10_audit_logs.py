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
            "email": f"it_mod10_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module10 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_module10_audit_logs_full_flow(client: AsyncClient):
    headers = await _register_user(client, "audit")
    suffix = _unique_suffix()

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod10_{suffix}",
            "name": f"Audit Event {suffix}",
            "description": "module10 audit event",
            "domain": "audit",
            "owner": "audit-owner",
            "properties": {"user_id": "string", "amount": "float"},
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201
    event = create_event_resp.json()["data"]

    update_event_resp = await client.patch(
        f"/api/v1/events/{event['id']}",
        json={
            "description": "module10 audit event updated",
            "owner": "audit-owner-updated",
            "tags": ["audit", "module10"],
        },
        headers=headers,
    )
    assert update_event_resp.status_code == 200

    create_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Audit Asset {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"audit_asset_{suffix}",
            "domain": "audit",
            "owner": "audit-owner",
            "status": "ACTIVE",
            "tags": ["audit"],
            "description": "module10 audit asset",
            "schema_definition": {"columns": [{"name": "user_id", "type": "string"}]},
        },
        headers=headers,
    )
    assert create_asset_resp.status_code == 201
    asset = create_asset_resp.json()["data"]

    create_rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_mod10_{suffix}",
            "asset_id": asset["id"],
            "event_id": event["id"],
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.01},
            "alert_channels": ["email"],
            "severity": "HIGH",
            "status": "ACTIVE",
            "description": "module10 dq rule",
        },
        headers=headers,
    )
    assert create_rule_resp.status_code == 201
    rule = create_rule_resp.json()["data"]

    run_fail_resp = await client.post(
        f"/api/v1/data-quality/rules/{rule['id']}/run",
        json={
            "checked_count": 1000,
            "failed_count": 200,
            "trigger_source": "manual",
            "notes": "force fail for module10",
        },
        headers=headers,
    )
    assert run_fail_resp.status_code == 200
    assert run_fail_resp.json()["data"]["result"] == "FAIL"

    list_default_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert list_default_resp.status_code == 200
    default_rows = list_default_resp.json()["data"]
    assert isinstance(default_rows, list)
    actions_default = {item["action"] for item in default_rows}
    assert "EVENT_CREATE" in actions_default
    assert "EVENT_UPDATE" in actions_default
    assert "DQ_RULE_RUN_FAIL" in actions_default

    list_meta_resp = await client.get(
        "/api/v1/audit/logs",
        params={
            "include_meta": True,
            "entity_type": "TRACKING_EVENT",
            "action": "EVENT_UPDATE",
            "status": "SUCCESS",
            "q": "audit-owner-updated",
            "limit": 20,
            "offset": 0,
        },
        headers=headers,
    )
    assert list_meta_resp.status_code == 200
    list_meta = list_meta_resp.json()["data"]
    assert list_meta["total"] >= 1
    assert len(list_meta["items"]) >= 1
    assert "EVENT_UPDATE" in list_meta["facets"]["actions"]
    update_log = list_meta["items"][0]
    assert update_log["entity_type"] == "TRACKING_EVENT"
    assert update_log["status"] == "SUCCESS"
    assert update_log["has_diff"] is True
    assert "description" in update_log["changed_fields"]

    failure_list_resp = await client.get(
        "/api/v1/audit/logs",
        params={"include_meta": True, "status": "FAILURE", "limit": 100},
        headers=headers,
    )
    assert failure_list_resp.status_code == 200
    failure_items = failure_list_resp.json()["data"]["items"]
    assert any(item["action"] == "DQ_RULE_RUN_FAIL" for item in failure_items)
    assert all(item["status"] == "FAILURE" for item in failure_items)

    detail_resp = await client.get(f"/api/v1/audit/logs/{update_log['id']}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["action"] == "EVENT_UPDATE"
    assert detail["target"].startswith("TRACKING_EVENT:")
    assert "diff" in detail
    assert "description" in detail["diff"]
    assert detail["navigation"]["module_route"] == "/events"

    export_csv_resp = await client.post(
        "/api/v1/audit/logs/export",
        json={
            "format": "csv",
            "action": "EVENT_UPDATE",
        },
        headers=headers,
    )
    assert export_csv_resp.status_code == 200
    export_csv = export_csv_resp.json()["data"]
    assert export_csv["format"] == "csv"
    assert export_csv["filename"].endswith(".csv")
    assert "EVENT_UPDATE" in export_csv["content"]

    export_json_resp = await client.post(
        "/api/v1/audit/logs/export",
        json={
            "format": "json",
            "status": "FAILURE",
        },
        headers=headers,
    )
    assert export_json_resp.status_code == 200
    export_json = export_json_resp.json()["data"]
    assert export_json["format"] == "json"
    assert export_json["filename"].endswith(".json")
    assert "DQ_RULE_RUN_FAIL" in export_json["content"]

    after_export_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert after_export_resp.status_code == 200
    after_actions = {item["action"] for item in after_export_resp.json()["data"]}
    assert "AUDIT_LOG_EXPORT" in after_actions
