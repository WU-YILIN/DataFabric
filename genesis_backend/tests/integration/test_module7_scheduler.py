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
            "email": f"it_mod7_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module7 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_module7_scheduler_full_flow(client: AsyncClient):
    headers = await _register_user_and_headers(client, "scheduler")
    suffix = _unique_suffix()

    create_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Scheduler Source {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"src_scheduler_{suffix}",
            "domain": "ops",
            "owner": "data-platform",
            "status": "ACTIVE",
            "tags": ["scheduler"],
            "description": "source table for scheduler module test",
            "schema_definition": {"columns": [{"name": "id", "type": "string"}]},
        },
        headers=headers,
    )
    assert create_asset_resp.status_code == 201
    source_asset = create_asset_resp.json()["data"]

    options_resp = await client.get("/api/v1/scheduler/options", headers=headers)
    assert options_resp.status_code == 200
    options = options_resp.json()["data"]
    assert "BATCH" in options["task_types"]
    assert any(item["id"] == source_asset["id"] for item in options["assets"])

    create_dag_resp = await client.post(
        "/api/v1/scheduler/dags",
        json={
            "name": f"scheduler_mod7_{suffix}",
            "description": "module7 scheduler dag",
            "status": "ACTIVE",
            "trigger_mode": "CRON",
            "cron_expr": "*/5 * * * *",
            "timezone": "UTC",
            "dependency_mode": "ALL_SUCCESS",
            "retry_policy": {"max_retries": 2, "backoff_seconds": 60},
            "schedule_config": {"owner": "platform"},
            "nodes": [
                {
                    "node_key": "extract",
                    "name": "Extract Source",
                    "task_type": "BATCH",
                    "input_assets": [str(source_asset["id"])],
                    "output_assets": ["staging.extract"],
                    "logic_description": "extract rows from source table",
                    "config": {"sql": "select * from src"},
                },
                {
                    "node_key": "validate",
                    "name": "Validate Rows",
                    "task_type": "VALIDATION",
                    "input_assets": ["staging.extract"],
                    "output_assets": ["staging.validated"],
                    "logic_description": "validate basic constraints",
                    "config": {"rules": ["not_null:id"]},
                },
                {
                    "node_key": "publish",
                    "name": "Publish Data",
                    "task_type": "SYNC",
                    "input_assets": ["staging.validated"],
                    "output_assets": ["warehouse.fact"],
                    "logic_description": "publish validated dataset",
                    "config": {"target": "warehouse.fact"},
                },
            ],
            "edges": [
                {"from_node_key": "extract", "to_node_key": "validate"},
                {"from_node_key": "validate", "to_node_key": "publish"},
            ],
        },
        headers=headers,
    )
    assert create_dag_resp.status_code == 201
    created_dag = create_dag_resp.json()["data"]
    dag_id = created_dag["id"]
    assert created_dag["node_count"] == 3
    assert created_dag["edge_count"] == 2
    assert created_dag["trigger_mode"] == "CRON"

    list_resp = await client.get(
        "/api/v1/scheduler/dags",
        params={"q": "mod7", "status": "ACTIVE", "trigger_mode": "CRON"},
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert any(item["id"] == dag_id for item in list_data)

    detail_resp = await client.get(f"/api/v1/scheduler/dags/{dag_id}/detail", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert len(detail_data["topology"]["nodes"]) == 3
    assert len(detail_data["topology"]["edges"]) == 2
    assert detail_data["recent_runs"] == []

    run_resp = await client.post(
        f"/api/v1/scheduler/dags/{dag_id}/run",
        json={
            "trigger_source": "manual",
            "forced_node_results": {
                "extract": "SUCCESS",
                "validate": "FAILED",
                "publish": "SKIPPED",
            },
            "run_context": {"env": "test"},
        },
        headers=headers,
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()["data"]
    run = run_data["run"]
    assert run["status"] == "FAILED"
    run_id = run["id"]

    run_detail_resp = await client.get(f"/api/v1/scheduler/runs/{run_id}/detail", headers=headers)
    assert run_detail_resp.status_code == 200
    run_detail = run_detail_resp.json()["data"]
    latest_status = run_detail["latest_node_status"]
    assert latest_status["extract"] == "SUCCESS"
    assert latest_status["validate"] == "FAILED"
    assert latest_status["publish"] == "SKIPPED"

    failed_node_run = next(item for item in run_detail["node_runs"] if item["node_key"] == "validate")
    fix_action_resp = await client.post(
        f"/api/v1/scheduler/runs/{run_id}/actions",
        json={
            "action": "MARK_SUCCESS",
            "node_run_id": failed_node_run["id"],
            "reason": "manual validation waiver for test",
        },
        headers=headers,
    )
    assert fix_action_resp.status_code == 200
    run_after_fix = fix_action_resp.json()["data"]["run"]
    assert run_after_fix["status"] in {"PARTIAL", "SUCCESS"}

    skipped_node_run = next(
        item
        for item in fix_action_resp.json()["data"]["node_runs"]
        if item["node_key"] == "publish" and item["status"] == "SKIPPED"
    )
    retry_action_resp = await client.post(
        f"/api/v1/scheduler/runs/{run_id}/actions",
        json={
            "action": "RETRY",
            "node_run_id": skipped_node_run["id"],
            "reason": "retry skipped publish node",
        },
        headers=headers,
    )
    assert retry_action_resp.status_code == 200
    run_after_retry = retry_action_resp.json()["data"]["run"]
    assert run_after_retry["status"] == "SUCCESS"

    dag_runs_resp = await client.get(f"/api/v1/scheduler/dags/{dag_id}/runs", headers=headers)
    assert dag_runs_resp.status_code == 200
    dag_runs = dag_runs_resp.json()["data"]
    assert any(item["id"] == run_id for item in dag_runs)

    tick_resp = await client.post(
        "/api/v1/scheduler/engine/tick",
        json={"run_immediately": True, "limit": 20},
        headers=headers,
    )
    assert tick_resp.status_code == 200
    tick_data = tick_resp.json()["data"]
    assert tick_data["executed_count"] >= 1
    assert any(item["dag_id"] == dag_id for item in tick_data["executed_runs"])

    detail_after_tick_resp = await client.get(f"/api/v1/scheduler/dags/{dag_id}/detail", headers=headers)
    assert detail_after_tick_resp.status_code == 200
    detail_after_tick = detail_after_tick_resp.json()["data"]
    assert detail_after_tick["dag"]["last_scheduled_at"] is not None
    assert detail_after_tick["dag"]["next_scheduled_at"] is not None
    assert len(detail_after_tick["recent_runs"]) >= 2

    overview_resp = await client.get("/api/v1/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview = overview_resp.json()["data"]
    assert isinstance(overview["todos"], list)
    assert isinstance(overview["risks"]["unhandled_alerts"], list)

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "SCHEDULER_DAG_CREATE" in actions
    assert "SCHEDULER_RUN_TRIGGER" in actions
    assert "SCHEDULER_RUN_ACTION" in actions
    assert "SCHEDULER_ENGINE_TICK" in actions
