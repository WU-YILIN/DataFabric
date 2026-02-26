import time

import pytest
from httpx import AsyncClient

from src.domain.search.engine import SearchEngine
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import async_session_factory
from src.infrastructure.llm.client import ArbitrationResponse, LLMAdapter


def _unique_suffix() -> str:
    return str(int(time.time() * 1000))


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
            "email": f"it_mod5_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module5 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_module5_data_catalog_asset_flow(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    headers = await _register_user_and_headers(client, "catalog")
    suffix = _unique_suffix()
    event_code = f"evt_mod5_{suffix}"

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"Catalog Event {suffix}",
            "description": "module5 catalog event",
            "domain": "analytics",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201
    created_event = create_event_resp.json()["data"]
    event_id = created_event["id"]
    project_id = created_event["project_id"]

    def fake_llm_init(self):
        self.client = None

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return []

    async def fake_arbitrate(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.97,
            reasoning="Event is compliant",
            recommended_code=None,
        )

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)

    approve_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": created_event["name"],
            "description": created_event["description"],
            "properties": created_event["properties"],
        },
        headers=headers,
    )
    assert approve_resp.status_code == 200

    provision_resp = await client.post(
        "/api/v1/pipelines/provision",
        json={"event_code": event_code},
        headers=headers,
    )
    assert provision_resp.status_code == 201
    pipeline = provision_resp.json()["data"]

    async with async_session_factory() as session:
        dq_repo = BaseRepository(DataQualityRule, session)
        await dq_repo.create(
            {
                "project_id": project_id,
                "event_id": event_id,
                "name": "timestamp_not_null",
                "rule_type": "NOT_NULL",
                "target_field": "timestamp",
                "operator": "IS_NOT_NULL",
                "threshold": {},
                "severity": "MEDIUM",
                "status": "ACTIVE",
                "description": "timestamp should not be null",
                "version": "1.0.0",
            }
        )
        await session.commit()

    create_topic_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Tracking Topic {suffix}",
            "asset_type": "TOPIC",
            "source_system": "kafka",
            "database_name": "streaming",
            "object_name": pipeline["topic_name"],
            "domain": "analytics",
            "owner": "data-team",
            "status": "ACTIVE",
            "tags": ["tracking", "kafka"],
            "description": "raw tracking topic",
            "schema_definition": {"columns": [{"name": "user_id", "type": "string"}]},
        },
        headers=headers,
    )
    assert create_topic_asset_resp.status_code == 201
    topic_asset = create_topic_asset_resp.json()["data"]

    create_table_asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"DW Fact Table {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"fact_tracking_{suffix}",
            "domain": "analytics",
            "owner": "bi-team",
            "status": "DRAFT",
            "tags": ["warehouse"],
            "description": "downstream fact table",
            "schema_definition": {"columns": [{"name": "dt", "type": "date"}]},
            "upstream_asset_ids": [topic_asset["id"]],
        },
        headers=headers,
    )
    assert create_table_asset_resp.status_code == 201
    table_asset = create_table_asset_resp.json()["data"]

    list_resp = await client.get(
        "/api/v1/catalog/assets",
        params={
            "q": "tracking",
            "asset_type": "TOPIC",
            "domain": "analytics",
            "source_system": "kafka",
            "status": "ACTIVE",
        },
        headers=headers,
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()["data"]
    assert any(item["id"] == topic_asset["id"] for item in listed)

    topic_detail_resp = await client.get(f"/api/v1/catalog/assets/{topic_asset['id']}/detail", headers=headers)
    assert topic_detail_resp.status_code == 200
    topic_detail = topic_detail_resp.json()["data"]
    assert len(topic_detail["relations"]["pipelines"]) >= 1
    assert any(item["event_code"] == event_code for item in topic_detail["relations"]["pipelines"])
    assert any(item["code"] == event_code for item in topic_detail["relations"]["events"])
    assert any(item["name"] == "timestamp_not_null" for item in topic_detail["quality"]["rules"])

    table_detail_resp = await client.get(f"/api/v1/catalog/assets/{table_asset['id']}/detail", headers=headers)
    assert table_detail_resp.status_code == 200
    table_detail = table_detail_resp.json()["data"]
    assert any(item["id"] == topic_asset["id"] for item in table_detail["lineage"]["upstream"])

    update_table_resp = await client.patch(
        f"/api/v1/catalog/assets/{table_asset['id']}",
        json={
            "owner": "growth-bi",
            "status": "ACTIVE",
            "tags": ["warehouse", "core"],
            "description": "curated downstream fact table",
            "upstream_asset_ids": [topic_asset["id"]],
            "downstream_asset_ids": [],
        },
        headers=headers,
    )
    assert update_table_resp.status_code == 200
    updated_table = update_table_resp.json()["data"]
    assert updated_table["version"] == "1.0.1"
    assert updated_table["owner"] == "growth-bi"
    assert updated_table["status"] == "ACTIVE"

    updated_table_detail_resp = await client.get(f"/api/v1/catalog/assets/{table_asset['id']}/detail", headers=headers)
    assert updated_table_detail_resp.status_code == 200
    updated_table_detail = updated_table_detail_resp.json()["data"]
    assert len(updated_table_detail["version_history"]) >= 1
    assert updated_table_detail["version_history"][0]["to_version"] == "1.0.1"

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "DATA_ASSET_CREATE" in actions
    assert "DATA_ASSET_UPDATE" in actions
