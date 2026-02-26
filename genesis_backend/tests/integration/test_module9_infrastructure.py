import time

import pytest
from httpx import AsyncClient

from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.pipeline import Pipeline
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
            "email": f"it_mod9_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module9 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    context = register_data["default_context"]
    assert context is not None
    return _context_headers(register_data["access_token"], context), context


async def _seed_infrastructure_records(
    *,
    project_id: int,
    event_code: str,
    topic_name: str,
    dag_id: int,
    suffix: str,
) -> tuple[int, int]:
    async with async_session_factory() as session:
        pipeline_repo = BaseRepository(Pipeline, session)
        alert_repo = BaseRepository(Alert, session)

        dev_pipeline = await pipeline_repo.create(
            {
                "project_id": project_id,
                "event_code": event_code,
                "topic_name": topic_name,
                "flink_job_name": f"flink_dev_{suffix}",
                "status": "RUNNING",
                "config": {
                    "partitions": 8,
                    "replication_factor": 3,
                    "retention_hours": 240,
                    "environment": "dev",
                    "kafka_cluster": "kafka-dev-a",
                    "flink_cluster": "flink-dev-a",
                    "flink_job_id": f"job-dev-{suffix}",
                    "flink_state": "RUNNING",
                },
                "retry_count": 0,
                "error_message": None,
            }
        )
        prod_pipeline = await pipeline_repo.create(
            {
                "project_id": project_id,
                "event_code": f"{event_code}_prod",
                "topic_name": f"tracking.prod.{suffix}",
                "flink_job_name": f"flink_prod_{suffix}",
                "status": "FAILED",
                "config": {
                    "partitions": 6,
                    "replication_factor": 2,
                    "retention_hours": 168,
                    "environment": "prod",
                    "kafka_cluster": "kafka-prod-a",
                    "flink_cluster": "flink-prod-a",
                    "flink_job_id": f"job-prod-{suffix}",
                    "flink_state": "FAILED",
                },
                "retry_count": 2,
                "error_message": "job failed for integration test",
            }
        )

        await alert_repo.create(
            {
                "project_id": project_id,
                "source_type": "PIPELINE",
                "source_id": str(prod_pipeline.id),
                "severity": "CRITICAL",
                "title": "Flink job failed",
                "description": "Job is failing repeatedly",
                "status": "OPEN",
            }
        )
        await alert_repo.create(
            {
                "project_id": project_id,
                "source_type": "SCHEDULER_DAG",
                "source_id": str(dag_id),
                "severity": "HIGH",
                "title": "Scheduler delay",
                "description": "DAG run is delayed",
                "status": "OPEN",
            }
        )

        await session.commit()
        return dev_pipeline.id, prod_pipeline.id


@pytest.mark.asyncio
async def test_module9_infrastructure_overview(client: AsyncClient):
    headers, context = await _register_user(client, "infra")
    suffix = _unique_suffix()
    event_code = f"evt_mod9_{suffix}"
    topic_name = f"tracking.dev.{suffix}"

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"Infrastructure Event {suffix}",
            "description": "module9 infrastructure event",
            "domain": "infra",
            "properties": {"user_id": "string", "ts": "iso8601"},
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201

    create_topic_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Infrastructure Topic Asset {suffix}",
            "asset_type": "TOPIC",
            "source_system": "kafka",
            "database_name": "streaming",
            "object_name": topic_name,
            "domain": "infra",
            "owner": "platform",
            "status": "ACTIVE",
            "tags": ["infra", "dev"],
            "description": "topic asset for infrastructure module test",
            "schema_definition": {"columns": [{"name": "user_id", "type": "string"}]},
        },
        headers=headers,
    )
    assert create_topic_asset_resp.status_code == 201
    topic_asset = create_topic_asset_resp.json()["data"]

    create_table_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Infrastructure Table Asset {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"fact_infra_{suffix}",
            "domain": "infra",
            "owner": "bi",
            "status": "ACTIVE",
            "tags": ["infra", "prod"],
            "description": "warehouse table for infrastructure module test",
            "schema_definition": {"columns": [{"name": "dt", "type": "date"}]},
        },
        headers=headers,
    )
    assert create_table_asset_resp.status_code == 201

    create_dag_resp = await client.post(
        "/api/v1/scheduler/dags",
        json={
            "name": f"scheduler_mod9_{suffix}",
            "description": "module9 scheduler dag",
            "status": "ACTIVE",
            "trigger_mode": "MANUAL",
            "timezone": "UTC",
            "dependency_mode": "ALL_SUCCESS",
            "retry_policy": {"max_retries": 1, "backoff_seconds": 30},
            "schedule_config": {"owner": "platform"},
            "nodes": [
                {
                    "node_key": "sync_topic",
                    "name": "Sync Topic",
                    "task_type": "SYNC",
                    "input_assets": [topic_name],
                    "output_assets": [topic_name],
                    "logic_description": "sync topic data",
                    "config": {"target": topic_name},
                }
            ],
            "edges": [],
        },
        headers=headers,
    )
    assert create_dag_resp.status_code == 201
    dag = create_dag_resp.json()["data"]

    run_dag_resp = await client.post(
        f"/api/v1/scheduler/dags/{dag['id']}/run",
        json={
            "trigger_source": "manual",
            "forced_node_results": {"sync_topic": "SUCCESS"},
            "run_context": {"reason": "module9 test"},
        },
        headers=headers,
    )
    assert run_dag_resp.status_code == 200

    dev_pipeline_id, prod_pipeline_id = await _seed_infrastructure_records(
        project_id=context["project_id"],
        event_code=event_code,
        topic_name=topic_name,
        dag_id=dag["id"],
        suffix=suffix,
    )

    overview_resp = await client.get("/api/v1/infrastructure/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview = overview_resp.json()["data"]

    assert overview["summary"]["kafka_topics"] >= 2
    assert overview["summary"]["flink_jobs"] >= 2
    assert overview["summary"]["open_alerts"] >= 2
    assert "dev" in overview["filters"]["available_environments"]
    assert "prod" in overview["filters"]["available_environments"]
    assert "kafka-dev-a" in overview["filters"]["available_clusters"]
    assert "flink-prod-a" in overview["filters"]["available_clusters"]

    dev_topic = next(item for item in overview["kafka"]["topics"] if item["pipeline_id"] == dev_pipeline_id)
    assert dev_topic["catalog_asset_id"] == topic_asset["id"]
    assert dev_topic["cluster_id"] == "kafka-dev-a"
    assert dev_topic["environment"] == "dev"

    prod_job = next(item for item in overview["flink"]["jobs"] if item["pipeline_id"] == prod_pipeline_id)
    assert prod_job["cluster_id"] == "flink-prod-a"
    assert prod_job["environment"] == "prod"
    assert prod_job["state"] == "FAILED"
    assert dag["id"] in prod_job["scheduler_dag_ids"] or dag["id"] in next(
        item["scheduler_dag_ids"] for item in overview["flink"]["jobs"] if item["pipeline_id"] == dev_pipeline_id
    )

    assert any(item["source_system"] == "kafka" for item in overview["storage"]["systems"])
    assert any(item["source_system"] == "warehouse" for item in overview["storage"]["systems"])
    assert overview["alerts"]["open_count"] >= 2
    assert any(item["source_type"] == "PIPELINE" for item in overview["alerts"]["by_source"])

    filtered_env_resp = await client.get(
        "/api/v1/infrastructure/overview",
        params={"environment": "prod"},
        headers=headers,
    )
    assert filtered_env_resp.status_code == 200
    filtered_env = filtered_env_resp.json()["data"]
    assert all(item["environment"] == "prod" for item in filtered_env["kafka"]["topics"])
    assert all(item["environment"] == "prod" for item in filtered_env["flink"]["jobs"])

    filtered_cluster_resp = await client.get(
        "/api/v1/infrastructure/overview",
        params={"cluster": "kafka-dev-a"},
        headers=headers,
    )
    assert filtered_cluster_resp.status_code == 200
    filtered_cluster = filtered_cluster_resp.json()["data"]
    assert all(item["cluster_id"] == "kafka-dev-a" for item in filtered_cluster["kafka"]["topics"])

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "INFRA_OVERVIEW_VIEW" in actions
