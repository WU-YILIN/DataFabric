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
            "email": f"it_mod2_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module2 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_event_catalog_create_filter_detail_update_and_audit(client: AsyncClient):
    headers = await _register_user_and_headers(client, "flow")
    suffix = _unique_suffix()
    event_code = f"evt_mod2_{suffix}"
    event_name = f"Event Catalog {suffix}"

    create_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": event_name,
            "description": "module2 create event",
            "domain": "payments",
            "owner": "alice",
            "tags": ["critical", "billing"],
            "status": "draft",
            "properties": {"order_id": "string", "amount": "number"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    create_body = create_resp.json()
    assert create_body["code"] == "EVENT_CREATED"
    created = create_body["data"]
    event_id = created["id"]
    assert created["governance_status"] == "NOT_CHECKED"
    assert created["owner"] == "alice"
    assert created["tags"] == ["critical", "billing"]

    list_resp = await client.get(
        "/api/v1/events/",
        params={
            "q": "mod2",
            "domain": "payments",
            "owner": "alice",
            "status": "draft",
            "governance_status": "NOT_CHECKED",
        },
        headers=headers,
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()["data"]
    assert any(row["id"] == event_id for row in listed)

    detail_resp = await client.get(f"/api/v1/events/{event_id}/detail", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["event"]["id"] == event_id
    assert detail["event"]["name"] == event_name
    assert detail["event"]["properties"]["order_id"] == "string"
    assert detail["governance_records"] == []
    assert detail["version_history"] == []

    update_resp = await client.patch(
        f"/api/v1/events/{event_id}",
        json={
            "description": "module2 update event",
            "status": "active",
            "tags": ["critical", "billing", "v2"],
            "properties": {"order_id": "string", "amount": "number", "currency": "string"},
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    update_body = update_resp.json()
    assert update_body["code"] == "EVENT_UPDATED"
    assert update_body["data"]["version"] == "1.0.1"
    assert update_body["data"]["status"] == "active"

    no_change_resp = await client.patch(
        f"/api/v1/events/{event_id}",
        json={},
        headers=headers,
    )
    assert no_change_resp.status_code == 200
    assert no_change_resp.json()["code"] == "EVENT_NO_CHANGES"

    detail_after_update_resp = await client.get(f"/api/v1/events/{event_id}/detail", headers=headers)
    assert detail_after_update_resp.status_code == 200
    detail_after_update = detail_after_update_resp.json()["data"]
    assert detail_after_update["event"]["version"] == "1.0.1"
    assert len(detail_after_update["version_history"]) >= 1
    latest_change = detail_after_update["version_history"][0]
    assert latest_change["from_version"] == "1.0.0"
    assert latest_change["to_version"] == "1.0.1"
    assert "status" in latest_change["diff"]

    submit_resp = await client.post(f"/api/v1/events/{event_id}/submit-governance", headers=headers)
    assert submit_resp.status_code == 200
    submit_data = submit_resp.json()["data"]
    assert submit_data["event_id"] == event_id
    assert submit_data["name"] == event_name

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    logs = audit_resp.json()["data"]
    event_logs = [row for row in logs if row["target"] == f"TRACKING_EVENT:{event_code}"]
    actions = {row["action"] for row in event_logs}
    assert "EVENT_CREATE" in actions
    assert "EVENT_UPDATE" in actions


@pytest.mark.asyncio
async def test_event_catalog_submit_governance_updates_event_status(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register_user_and_headers(client, "gov")
    suffix = _unique_suffix()

    create_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod2_gov_{suffix}",
            "name": f"Governance Event {suffix}",
            "description": "module2 governance event",
            "domain": "risk",
            "owner": "bob",
            "tags": ["governance"],
            "status": "draft",
            "properties": {"customer_id": "string"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    event_id = created["id"]

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return [
            {
                "id": 999,
                "score": 0.92,
                "payload": {
                    "name": "similar_event",
                    "description": "similar catalog event",
                },
                "source": "keyword",
            }
        ]

    async def fake_arbitrate(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.96,
            reasoning="Naming and schema look compliant",
            recommended_code="evt_governance_approved",
        )

    def fake_llm_init(self):
        self.client = None

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)

    gov_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": created["name"],
            "description": created["description"],
            "properties": created["properties"],
        },
        headers=headers,
    )
    assert gov_resp.status_code == 200
    gov_data = gov_resp.json()["data"]
    assert gov_data["verdict"] == "APPROVE"
    assert gov_data["score"] == pytest.approx(0.96, rel=0.001)

    filtered_resp = await client.get(
        "/api/v1/events/",
        params={"governance_status": "APPROVED"},
        headers=headers,
    )
    assert filtered_resp.status_code == 200
    filtered_rows = filtered_resp.json()["data"]
    assert any(row["id"] == event_id for row in filtered_rows)

    detail_resp = await client.get(f"/api/v1/events/{event_id}/detail", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["event"]["governance_status"] == "APPROVED"
    assert len(detail["governance_records"]) >= 1
    assert detail["governance_records"][0]["verdict"] == "APPROVE"


@pytest.mark.asyncio
async def test_event_catalog_detail_returns_related_data_quality_rules(client: AsyncClient):
    headers = await _register_user_and_headers(client, "dq")
    suffix = _unique_suffix()

    create_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod2_dq_{suffix}",
            "name": f"DQ Event {suffix}",
            "description": "module2 dq event",
            "domain": "orders",
            "owner": "carol",
            "tags": ["quality"],
            "status": "active",
            "properties": {"order_id": "string", "amount": "number"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    event_id = created["id"]
    project_id = created["project_id"]

    async with async_session_factory() as session:
        repo = BaseRepository(DataQualityRule, session)
        await repo.create(
            {
                "project_id": project_id,
                "event_id": event_id,
                "name": "amount_positive",
                "rule_type": "VALUE_RANGE",
                "target_field": "amount",
                "operator": ">=",
                "threshold": {"min": 0},
                "severity": "HIGH",
                "status": "ACTIVE",
                "description": "Order amount should be non-negative",
                "version": "1.0.0",
            }
        )
        await session.commit()

    detail_resp = await client.get(f"/api/v1/events/{event_id}/detail", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert len(detail["data_quality_rules"]) == 1
    dq_rule = detail["data_quality_rules"][0]
    assert dq_rule["name"] == "amount_positive"
    assert dq_rule["rule_type"] == "VALUE_RANGE"
    assert dq_rule["target_field"] == "amount"
    assert dq_rule["severity"] == "HIGH"
    assert dq_rule["threshold"] == {"min": 0}
