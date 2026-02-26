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


@pytest.mark.asyncio
async def test_register_login_and_me(client: AsyncClient):
    suffix = _unique_suffix()
    email = f"it_user_{suffix}@demo.local"
    password = "demo123456"
    name = f"IT User {suffix}"

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": name,
        },
    )
    assert register_resp.status_code == 200
    register_body = register_resp.json()
    assert register_body["code"] == "REGISTER_SUCCESS"
    register_data = register_body["data"]
    assert register_data["access_token"]
    assert register_data["default_context"] is not None
    assert register_data["user"]["email"] == email

    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": password,
        },
    )
    assert login_resp.status_code == 200
    login_body = login_resp.json()
    assert login_body["code"] == "LOGIN_SUCCESS"
    login_data = login_body["data"]
    assert login_data["user"]["email"] == email
    assert login_data["access_token"]

    me_resp = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
    )
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    assert me_data["user"]["email"] == email
    assert len(me_data["tenants"]) >= 1


@pytest.mark.asyncio
async def test_overview_flow_with_event_and_pipeline(client: AsyncClient, monkeypatch: pytest.MonkeyPatch):
    suffix = _unique_suffix()
    email = f"it_overview_{suffix}@demo.local"
    password = "demo123456"
    name = f"Overview User {suffix}"
    event_code = f"evt_it_{suffix}"

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "name": name,
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])

    before_overview_resp = await client.get("/api/v1/overview", headers=headers)
    assert before_overview_resp.status_code == 200
    before_overview = before_overview_resp.json()["data"]

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"Integration Event {suffix}",
            "description": "integration overview flow event",
            "domain": "integration",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
        },
        headers=headers,
    )
    assert create_event_resp.status_code == 201

    def fake_llm_init(self):
        self.client = None

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return []

    async def fake_arbitrate(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.94,
            reasoning="Event definition is valid",
            recommended_code=None,
        )

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)

    approve_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": create_event_resp.json()["data"]["id"],
            "name": f"Integration Event {suffix}",
            "description": "integration overview flow event",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
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
    provision_data = provision_resp.json()["data"]
    assert provision_data["status"] in {"RUNNING", "PROVISIONING"}

    after_overview_resp = await client.get("/api/v1/overview", headers=headers)
    assert after_overview_resp.status_code == 200
    after_overview = after_overview_resp.json()["data"]

    assert after_overview["kpis"]["total_events"] >= before_overview["kpis"]["total_events"] + 1
    assert after_overview["kpis"]["active_pipelines"] >= before_overview["kpis"]["active_pipelines"]
    assert isinstance(after_overview["recent_activity"], list)
    assert "risks" in after_overview
    assert "todos" in after_overview
