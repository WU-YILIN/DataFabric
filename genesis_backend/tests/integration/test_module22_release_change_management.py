import time
from datetime import datetime, timedelta, timezone

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
            "email": f"it_mod22_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module22 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module22_release_change_management_full_flow(client: AsyncClient):
    admin_headers, context = await _login_admin(client)
    suffix = _unique_suffix()
    project_id = context["project_id"]

    overview_resp = await client.get("/api/v1/release/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    assert "summary" in overview_resp.json()["data"]

    create_resp = await client.post(
        "/api/v1/release/changes",
        json={
            "change_type": "PIPELINE_CHANGE",
            "source_type": "PIPELINE",
            "source_id": f"pipeline_mod22_{suffix}",
            "title": f"Module22 pipeline rollout {suffix}",
            "description": "Roll out pipeline config update with release gate",
            "priority": "HIGH",
            "impact_scope": {
                "tenant_id": context["tenant_id"],
                "project_ids": [project_id],
                "tenant_wide": False,
            },
            "before_payload": {"parallelism": 2, "checkpoint_interval": 60},
            "after_payload": {"parallelism": 4, "checkpoint_interval": 30},
            "release_plan_payload": {"window": "02:00-03:00 UTC", "strategy": "rolling"},
            "rollback_plan_payload": {"strategy": "restore_previous_snapshot"},
            "manual_review_note": "Reviewed by platform owner",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 200
    change = create_resp.json()["data"]
    change_id = change["id"]
    assert change["status"] == "PENDING_APPROVAL"

    list_resp = await client.get("/api/v1/release/changes", headers=admin_headers)
    assert list_resp.status_code == 200
    list_items = list_resp.json()["data"]["items"]
    assert any(item["id"] == change_id for item in list_items)

    detail_resp = await client.get(f"/api/v1/release/changes/{change_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["change"]["id"] == change_id
    assert len(detail_data["history"]) >= 1

    approve_resp = await client.post(
        f"/api/v1/release/changes/{change_id}/actions",
        json={"action": "APPROVE", "note": "approved for release window"},
        headers=admin_headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == "APPROVED"

    scheduled_at = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    schedule_resp = await client.post(
        f"/api/v1/release/changes/{change_id}/actions",
        json={"action": "SCHEDULE", "scheduled_at": scheduled_at, "note": "schedule now"},
        headers=admin_headers,
    )
    assert schedule_resp.status_code == 200
    assert schedule_resp.json()["data"]["status"] == "SCHEDULED"

    execute_resp = await client.post(
        f"/api/v1/release/changes/{change_id}/actions",
        json={"action": "EXECUTE", "simulate_failure": False, "note": "execute release"},
        headers=admin_headers,
    )
    assert execute_resp.status_code == 200
    execute_data = execute_resp.json()["data"]
    assert execute_data["change"]["status"] == "COMPLETED"
    assert execute_data["execution"]["result"] == "SUCCESS"

    failure_create_resp = await client.post(
        "/api/v1/release/changes",
        json={
            "change_type": "POLICY_CHANGE",
            "source_type": "POLICY_RULE",
            "source_id": f"policy_mod22_{suffix}",
            "title": f"Module22 policy rollout {suffix}",
            "priority": "CRITICAL",
            "impact_scope": {
                "tenant_id": context["tenant_id"],
                "project_ids": [project_id],
                "tenant_wide": True,
            },
            "before_payload": {"threshold": 0.8},
            "after_payload": {"threshold": 0.95},
            "release_plan_payload": {"window": "03:00-03:30 UTC", "strategy": "immediate"},
            "rollback_plan_payload": {"strategy": "fallback_threshold_0_8"},
        },
        headers=admin_headers,
    )
    assert failure_create_resp.status_code == 200
    failure_change_id = failure_create_resp.json()["data"]["id"]

    approve_failure_resp = await client.post(
        f"/api/v1/release/changes/{failure_change_id}/actions",
        json={"action": "APPROVE"},
        headers=admin_headers,
    )
    assert approve_failure_resp.status_code == 200
    assert approve_failure_resp.json()["data"]["status"] == "APPROVED"

    failure_execute_resp = await client.post(
        f"/api/v1/release/changes/{failure_change_id}/actions",
        json={
            "action": "EXECUTE",
            "simulate_failure": True,
            "failure_reason": "integration pipeline smoke test failed",
            "trigger_rollback": True,
        },
        headers=admin_headers,
    )
    assert failure_execute_resp.status_code == 200
    failure_execute_data = failure_execute_resp.json()["data"]
    assert failure_execute_data["execution"]["result"] == "FAILED"
    assert failure_execute_data["change"]["status"] == "ROLLED_BACK"

    alerts_resp = await client.get(
        "/api/v1/monitoring/alerts",
        params={"q": f"change:{failure_change_id}", "limit": 200},
        headers=admin_headers,
    )
    assert alerts_resp.status_code == 200
    alert_items = alerts_resp.json()["data"]["items"]
    assert any(item["source_type"] == "RELEASE" for item in alert_items)

    reject_create_resp = await client.post(
        "/api/v1/release/changes",
        json={
            "change_type": "OTHER",
            "source_type": "TASK",
            "source_id": f"task_mod22_{suffix}",
            "title": f"Module22 reject flow {suffix}",
            "priority": "LOW",
            "before_payload": {"enabled": False},
            "after_payload": {"enabled": True},
        },
        headers=admin_headers,
    )
    assert reject_create_resp.status_code == 200
    reject_change_id = reject_create_resp.json()["data"]["id"]

    reject_resp = await client.post(
        f"/api/v1/release/changes/{reject_change_id}/actions",
        json={"action": "REJECT", "note": "not aligned with release baseline"},
        headers=admin_headers,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["data"]["status"] == "REJECTED"

    overview_after_resp = await client.get("/api/v1/release/overview", headers=admin_headers)
    assert overview_after_resp.status_code == 200
    overview_after = overview_after_resp.json()["data"]["summary"]
    assert overview_after["total_changes"] >= 3
    assert overview_after["completed"] >= 1
    assert overview_after["rolled_back"] >= 1

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "RELEASE_CHANGE_CREATE" in actions
    assert "RELEASE_CHANGE_APPROVE" in actions
    assert "RELEASE_CHANGE_EXECUTE_SUCCESS" in actions
    assert "RELEASE_CHANGE_EXECUTE_FAILED" in actions


@pytest.mark.asyncio
async def test_module22_release_change_management_permission_guard(client: AsyncClient):
    admin_headers, context = await _login_admin(client)
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/release/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/release/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_create_resp = await client.post(
        "/api/v1/release/changes",
        json={
            "change_type": "PIPELINE_CHANGE",
            "source_type": "PIPELINE",
            "source_id": f"viewer_forbidden_{_unique_suffix()}",
            "title": "viewer should not create release change",
        },
        headers=viewer_headers,
    )
    assert viewer_create_resp.status_code == 403

    admin_create_resp = await client.post(
        "/api/v1/release/changes",
        json={
            "change_type": "EVENT_CHANGE",
            "source_type": "EVENT",
            "source_id": f"event_mod22_perm_{_unique_suffix()}",
            "title": "permission guard action target",
            "impact_scope": {"project_ids": [context["project_id"]]},
            "before_payload": {"owner": "a"},
            "after_payload": {"owner": "b"},
        },
        headers=admin_headers,
    )
    assert admin_create_resp.status_code == 200
    change_id = admin_create_resp.json()["data"]["id"]

    viewer_action_resp = await client.post(
        f"/api/v1/release/changes/{change_id}/actions",
        json={"action": "APPROVE"},
        headers=viewer_headers,
    )
    assert viewer_action_resp.status_code == 403
