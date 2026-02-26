import json
import time

import pytest
from httpx import AsyncClient

from src.infrastructure.database.models.pipeline import Pipeline, PipelineStatus
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import async_session_factory


def _unique_suffix() -> str:
    return str(time.time_ns())


def _context_headers(access_token: str, context: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


async def _register_user(client: AsyncClient, tag: str) -> tuple[dict[str, str], dict]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod8_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module8 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    context = register_data["default_context"]
    assert context is not None
    return _context_headers(register_data["access_token"], context), context


async def _insert_pipeline(project_id: int, event_code: str, suffix: str) -> int:
    async with async_session_factory() as session:
        repo = BaseRepository(Pipeline, session)
        pipeline = await repo.create(
            {
                "project_id": project_id,
                "event_code": event_code,
                "topic_name": f"tracking.mod8_{suffix}",
                "flink_job_name": f"flink_mod8_{suffix}",
                "status": PipelineStatus.RUNNING.value,
                "config": {"tier": "standard"},
                "retry_count": 0,
            }
        )
        await session.commit()
        return pipeline.id


@pytest.mark.asyncio
async def test_module8_explore_full_flow(client: AsyncClient):
    headers, context = await _register_user(client, "explore")
    suffix = _unique_suffix()

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod8_{suffix}",
            "name": f"Explore Event {suffix}",
            "description": "module8 explore event",
            "domain": "explore",
            "properties": {"user_id": "string", "amount": "float"},
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201
    event = create_event_resp.json()["data"]

    create_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Explore Asset {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"fact_mod8_{suffix}",
            "domain": "explore",
            "owner": "data-platform",
            "status": "ACTIVE",
            "tags": ["explore"],
            "description": "module8 explore table",
            "schema_definition": {
                "columns": [
                    {"name": "user_id", "type": "string"},
                    {"name": "amount", "type": "float"},
                    {"name": "is_valid", "type": "bool"},
                ]
            },
        },
        headers=headers,
    )
    assert create_asset_resp.status_code == 201
    asset = create_asset_resp.json()["data"]

    create_rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_mod8_{suffix}",
            "asset_id": asset["id"],
            "event_id": event["id"],
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.01},
            "alert_channels": ["email"],
            "severity": "HIGH",
            "status": "ACTIVE",
            "description": "module8 prefill rule",
        },
        headers=headers,
    )
    assert create_rule_resp.status_code == 201
    rule = create_rule_resp.json()["data"]

    create_dag_resp = await client.post(
        "/api/v1/scheduler/dags",
        json={
            "name": f"scheduler_mod8_{suffix}",
            "description": "module8 scheduler dag",
            "status": "ACTIVE",
            "trigger_mode": "MANUAL",
            "timezone": "UTC",
            "dependency_mode": "ALL_SUCCESS",
            "retry_policy": {"max_retries": 1, "backoff_seconds": 30},
            "schedule_config": {"owner": "platform"},
            "nodes": [
                {
                    "node_key": "extract",
                    "name": "Extract Asset",
                    "task_type": "BATCH",
                    "input_assets": [str(asset["id"])],
                    "output_assets": ["staging.extract"],
                    "logic_description": "extract source rows",
                    "config": {"sql": "select * from source"},
                }
            ],
            "edges": [],
        },
        headers=headers,
    )
    assert create_dag_resp.status_code == 201
    dag = create_dag_resp.json()["data"]

    pipeline_id = await _insert_pipeline(context["project_id"], event["code"], suffix)

    sources_resp = await client.get("/api/v1/explore/sources", headers=headers)
    assert sources_resp.status_code == 200
    sources = sources_resp.json()["data"]
    assert any(item["source_system"] == "warehouse" for item in sources)

    tree_resp = await client.get(
        "/api/v1/explore/catalog/tree",
        params={"source_system": "warehouse"},
        headers=headers,
    )
    assert tree_resp.status_code == 200
    tree = tree_resp.json()["data"]
    warehouse_node = next(item for item in tree if item["source_system"] == "warehouse")
    assert any(asset_item["id"] == asset["id"] for db_node in warehouse_node["databases"] for asset_item in db_node["assets"])

    profile_resp = await client.get(f"/api/v1/explore/assets/{asset['id']}/profile", headers=headers)
    assert profile_resp.status_code == 200
    profile = profile_resp.json()["data"]
    assert profile["asset"]["virtual_table"] == f"asset_{asset['id']}"
    assert len(profile["columns"]) >= 3
    assert len(profile["sample_rows"]) >= 1

    query_resp = await client.post(
        "/api/v1/explore/query",
        json={
            "sql": f"SELECT * FROM asset_{asset['id']} LIMIT 5",
            "page": 1,
            "page_size": 2,
        },
        headers=headers,
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()["data"]
    assert query_data["total_rows"] == 5
    assert query_data["total_pages"] == 3
    assert len(query_data["rows"]) == 2
    assert "guidance" in query_data

    query_page3_resp = await client.post(
        "/api/v1/explore/query",
        json={
            "sql": f"SELECT * FROM asset_{asset['id']} LIMIT 5",
            "page": 3,
            "page_size": 2,
        },
        headers=headers,
    )
    assert query_page3_resp.status_code == 200
    assert len(query_page3_resp.json()["data"]["rows"]) == 1

    forbidden_sql_resp = await client.post(
        "/api/v1/explore/query",
        json={"sql": "DELETE FROM events"},
        headers=headers,
    )
    assert forbidden_sql_resp.status_code == 400

    multi_statement_resp = await client.post(
        "/api/v1/explore/query",
        json={"sql": "SELECT 1; SELECT 2"},
        headers=headers,
    )
    assert multi_statement_resp.status_code == 400

    export_csv_resp = await client.post(
        "/api/v1/explore/query/export",
        json={
            "sql": "SELECT id, source_system FROM catalog_assets ORDER BY id DESC LIMIT 3",
            "format": "csv",
        },
        headers=headers,
    )
    assert export_csv_resp.status_code == 200
    export_csv_data = export_csv_resp.json()["data"]
    assert export_csv_data["format"] == "csv"
    assert export_csv_data["filename"].endswith(".csv")
    assert "id,source_system" in export_csv_data["content"]

    export_json_resp = await client.post(
        "/api/v1/explore/query/export",
        json={
            "sql": f"SELECT * FROM events WHERE id = {event['id']}",
            "format": "json",
        },
        headers=headers,
    )
    assert export_json_resp.status_code == 200
    export_json_data = export_json_resp.json()["data"]
    assert export_json_data["format"] == "json"
    exported_rows = json.loads(export_json_data["content"])
    assert isinstance(exported_rows, list)
    assert len(exported_rows) >= 1
    assert int(exported_rows[0]["id"]) == event["id"]

    prefill_asset_resp = await client.get(
        "/api/v1/explore/prefill",
        params={"source_type": "DATA_ASSET", "source_id": asset["id"]},
        headers=headers,
    )
    assert prefill_asset_resp.status_code == 200
    assert f"asset_{asset['id']}" in prefill_asset_resp.json()["data"]["sql"]

    prefill_event_resp = await client.get(
        "/api/v1/explore/prefill",
        params={"source_type": "EVENT", "source_id": event["id"]},
        headers=headers,
    )
    assert prefill_event_resp.status_code == 200
    assert f"id = {event['id']}" in prefill_event_resp.json()["data"]["sql"]

    prefill_pipeline_resp = await client.get(
        "/api/v1/explore/prefill",
        params={"source_type": "PIPELINE", "source_id": pipeline_id},
        headers=headers,
    )
    assert prefill_pipeline_resp.status_code == 200
    assert f"id = {pipeline_id}" in prefill_pipeline_resp.json()["data"]["sql"]

    prefill_rule_resp = await client.get(
        "/api/v1/explore/prefill",
        params={"source_type": "DATA_QUALITY_RULE", "source_id": rule["id"]},
        headers=headers,
    )
    assert prefill_rule_resp.status_code == 200
    assert f"id = {rule['id']}" in prefill_rule_resp.json()["data"]["sql"]

    prefill_dag_resp = await client.get(
        "/api/v1/explore/prefill",
        params={"source_type": "SCHEDULER_DAG", "source_id": dag["id"]},
        headers=headers,
    )
    assert prefill_dag_resp.status_code == 200
    assert f"d.id = {dag['id']}" in prefill_dag_resp.json()["data"]["sql"]

    unsupported_prefill_resp = await client.get(
        "/api/v1/explore/prefill",
        params={"source_type": "UNKNOWN", "source_id": "1"},
        headers=headers,
    )
    assert unsupported_prefill_resp.status_code == 400

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "EXPLORE_QUERY_EXECUTE" in actions
    assert "EXPLORE_QUERY_EXPORT" in actions
