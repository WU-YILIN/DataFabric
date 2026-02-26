import time

import pytest
from httpx import AsyncClient

from src.domain.search.engine import SearchEngine
from src.infrastructure.llm.client import ArbitrationResponse, LLMAdapter


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
            "email": f"it_mod16_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module16 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@demo.local", "password": "demo123456"},
    )
    assert login_resp.status_code == 200
    data = login_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module16_cost_usage_project_overview_and_resource_detail(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register_user(client, "project")
    suffix = _unique_suffix()
    event_code = f"evt_mod16_{suffix}"

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"Cost Event {suffix}",
            "description": "module16 event",
            "domain": "cost",
            "owner": "mod16-owner",
            "properties": {"user_id": "string", "ts": "iso8601"},
        },
        headers=headers,
    )
    assert event_resp.status_code == 201
    event_id = event_resp.json()["data"]["id"]

    def fake_llm_init(self):
        self.client = None

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return []

    async def fake_arbitrate(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.98,
            reasoning="Module16 governance pass",
            recommended_code=None,
        )

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)

    governance_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": f"Cost Event {suffix}",
            "description": "module16 event",
            "properties": {"user_id": "string", "ts": "iso8601"},
        },
        headers=headers,
    )
    assert governance_resp.status_code == 200

    pipeline_resp = await client.post(
        "/api/v1/pipelines/provision",
        json={"event_code": event_code},
        headers=headers,
    )
    assert pipeline_resp.status_code == 201
    pipeline_id = pipeline_resp.json()["data"]["id"]

    asset_resp = await client.post(
        "/api/v1/catalog/assets",
        json={
            "name": f"Cost Asset {suffix}",
            "asset_type": "TABLE",
            "source_system": "warehouse",
            "database_name": "dwh",
            "object_name": f"cost_asset_{suffix}",
            "domain": "cost",
            "owner": "platform",
            "status": "ACTIVE",
            "tags": ["module16"],
            "description": "module16 asset",
            "schema_definition": {"columns": [{"name": "user_id", "type": "string"}]},
        },
        headers=headers,
    )
    assert asset_resp.status_code == 201
    asset_id = asset_resp.json()["data"]["id"]

    rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_mod16_{suffix}",
            "asset_id": asset_id,
            "event_id": event_id,
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.01},
            "alert_channels": ["email"],
            "severity": "HIGH",
            "status": "ACTIVE",
            "description": "module16 dq rule",
        },
        headers=headers,
    )
    assert rule_resp.status_code == 201
    rule_id = rule_resp.json()["data"]["id"]

    dq_run_resp = await client.post(
        f"/api/v1/data-quality/rules/{rule_id}/run",
        json={"checked_count": 1200, "failed_count": 180, "trigger_source": "manual"},
        headers=headers,
    )
    assert dq_run_resp.status_code == 200

    dag_resp = await client.post(
        "/api/v1/scheduler/dags",
        json={
            "name": f"scheduler_mod16_{suffix}",
            "description": "module16 scheduler dag",
            "status": "ACTIVE",
            "trigger_mode": "MANUAL",
            "nodes": [
                {
                    "node_key": "extract",
                    "name": "Extract Node",
                    "task_type": "BATCH",
                    "input_assets": [str(asset_id)],
                    "output_assets": ["tmp.extract"],
                    "logic_description": "extract",
                    "config": {"sql": "select 1"},
                }
            ],
            "edges": [],
        },
        headers=headers,
    )
    assert dag_resp.status_code == 201
    dag_id = dag_resp.json()["data"]["id"]

    dag_run_resp = await client.post(
        f"/api/v1/scheduler/dags/{dag_id}/run",
        json={"trigger_source": "manual", "forced_node_results": {"extract": "SUCCESS"}},
        headers=headers,
    )
    assert dag_run_resp.status_code == 200

    overview_resp = await client.get(
        "/api/v1/cost/overview",
        params={"scope": "PROJECT", "window_days": 30, "granularity": "DAY"},
        headers=headers,
    )
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert overview_data["summary"]["scope"] == "PROJECT"
    assert overview_data["summary"]["total_cost"] > 0
    assert len(overview_data["trend"]) > 0
    assert len(overview_data["module_breakdown"]) > 0
    assert len(overview_data["resource_type_breakdown"]) > 0
    assert len(overview_data["top_resources"]) > 0
    assert any(item["module"] == "PIPELINES" for item in overview_data["top_resources"])

    resources_resp = await client.get(
        "/api/v1/cost/resources",
        params={"scope": "PROJECT", "module": "PIPELINES", "sort_by": "COST", "limit": 300},
        headers=headers,
    )
    assert resources_resp.status_code == 200
    resources_data = resources_resp.json()["data"]
    assert resources_data["total"] >= 1
    pipeline_resource = next(
        (item for item in resources_data["items"] if item["source_type"] == "PIPELINE"),
        None,
    )
    assert pipeline_resource is not None

    detail_resp = await client.get(
        f"/api/v1/cost/resources/{pipeline_resource['source_type']}/{pipeline_resource['source_id']}",
        params={"scope": "PROJECT", "window_days": 30, "granularity": "DAY"},
        headers=headers,
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["resource"]["source_type"] == "PIPELINE"
    assert detail_data["resource"]["route"] == "/pipelines"
    assert len(detail_data["trend"]) > 0
    assert len(detail_data["optimization_actions"]) > 0
    assert detail_data["navigation"]["module_route"] == "/pipelines"


@pytest.mark.asyncio
async def test_module16_cost_usage_tenant_scope_permission(client: AsyncClient):
    member_headers = await _register_user(client, "tenant_scope_member")
    member_tenant_scope_resp = await client.get(
        "/api/v1/cost/overview",
        params={"scope": "TENANT", "window_days": 7},
        headers=member_headers,
    )
    assert member_tenant_scope_resp.status_code == 403

    admin_headers = await _admin_headers(client)
    admin_tenant_scope_resp = await client.get(
        "/api/v1/cost/overview",
        params={"scope": "TENANT", "window_days": 7, "granularity": "HOUR"},
        headers=admin_headers,
    )
    assert admin_tenant_scope_resp.status_code == 200
    data = admin_tenant_scope_resp.json()["data"]
    assert data["summary"]["scope"] == "TENANT"
    assert data["summary"]["project_count"] >= 1
    assert len(data["project_ranking"]) >= 1
