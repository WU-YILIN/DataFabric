import time

import pytest
from httpx import AsyncClient

from src.domain.search.engine import SearchEngine
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
            "email": f"it_mod4_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module4 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_module4_pipeline_lifecycle_and_filters(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    headers = await _register_user_and_headers(client, "lifecycle")
    suffix = _unique_suffix()
    event_code = f"evt_mod4_{suffix}"

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"Pipeline Event {suffix}",
            "description": "module4 pipeline event",
            "domain": "streaming",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201
    event_id = create_event_resp.json()["data"]["id"]

    provision_before_approve = await client.post(
        "/api/v1/pipelines/provision",
        json={"event_code": event_code},
        headers=headers,
    )
    assert provision_before_approve.status_code == 400
    assert "governance approved" in provision_before_approve.json()["message"].lower()

    def fake_llm_init(self):
        self.client = None

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return []

    async def fake_arbitrate(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.98,
            reasoning="Compliant event",
            recommended_code=None,
        )

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)

    approve_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": f"Pipeline Event {suffix}",
            "description": "module4 pipeline event",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
        },
        headers=headers,
    )
    assert approve_resp.status_code == 200

    options_resp = await client.get("/api/v1/pipelines/provision-options", headers=headers)
    assert options_resp.status_code == 200
    options = options_resp.json()["data"]["approved_events"]
    assert any(item["code"] == event_code for item in options)

    provision_resp = await client.post(
        "/api/v1/pipelines/provision",
        json={
            "event_code": event_code,
            "partitions": 3,
            "replication_factor": 2,
            "retention_hours": 48,
            "resource_tier": "small",
            "topic_prefix": "tracking",
            "job_name_template": "job_{project_id}_{event_code}",
        },
        headers=headers,
    )
    assert provision_resp.status_code == 201
    pipeline = provision_resp.json()["data"]
    pipeline_id = pipeline["id"]
    assert pipeline["status"] in {"RUNNING", "PROVISIONING"}
    assert pipeline["config"]["resource_tier"] == "small"

    list_filtered_resp = await client.get(
        "/api/v1/pipelines/",
        params={"status": "RUNNING", "event_code": event_code, "q": "job_"},
        headers=headers,
    )
    assert list_filtered_resp.status_code == 200
    filtered_rows = list_filtered_resp.json()["data"]
    assert any(row["id"] == pipeline_id for row in filtered_rows)

    pause_resp = await client.post(f"/api/v1/pipelines/{pipeline_id}/pause", headers=headers)
    assert pause_resp.status_code == 200
    assert pause_resp.json()["data"]["status"] in {"STOPPED", "FAILED"}

    resume_resp = await client.post(f"/api/v1/pipelines/{pipeline_id}/resume", headers=headers)
    assert resume_resp.status_code == 200
    assert resume_resp.json()["data"]["status"] in {"RUNNING", "FAILED"}

    sync_resp = await client.post(f"/api/v1/pipelines/{pipeline_id}/sync", headers=headers)
    assert sync_resp.status_code == 200
    assert sync_resp.json()["data"]["status"] in {"RUNNING", "FAILED"}

    rollback_resp = await client.post(f"/api/v1/pipelines/{pipeline_id}/rollback", headers=headers)
    assert rollback_resp.status_code == 200
    assert rollback_resp.json()["data"]["status"] in {"STOPPED", "FAILED"}

    history_resp = await client.get(f"/api/v1/pipelines/{pipeline_id}/history", headers=headers)
    assert history_resp.status_code == 200
    history = history_resp.json()["data"]
    to_statuses = [item["to_status"] for item in history]
    assert "PROVISIONING" in to_statuses
    assert any(status in {"RUNNING", "STOPPED"} for status in to_statuses)

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {row["action"] for row in audit_resp.json()["data"]}
    assert "PIPELINE_PROVISION" in actions
    assert "PIPELINE_PAUSE" in actions
    assert "PIPELINE_RESUME" in actions
    assert "PIPELINE_ROLLBACK" in actions
