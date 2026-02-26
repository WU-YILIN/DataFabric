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
            "email": f"it_mod3_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module3 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    assert register_data["default_context"] is not None
    return _context_headers(register_data["access_token"], register_data["default_context"])


@pytest.mark.asyncio
async def test_governance_workbench_revision_apply_and_recheck(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    headers = await _register_user_and_headers(client, "flow")
    suffix = _unique_suffix()

    create_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod3_{suffix}",
            "name": f"Governance Loop Event {suffix}",
            "description": "raw checkout event",
            "domain": "commerce",
            "owner": "owner_mod3",
            "tags": ["mod3"],
            "status": "draft",
            "properties": {"uid": "string", "price": "number"},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    created = create_resp.json()["data"]
    event_id = created["id"]

    def fake_llm_init(self):
        self.client = None

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return [
            {
                "id": 101,
                "score": 0.81,
                "payload": {
                    "name": "checkout_completed",
                    "description": "existing checkout completion event",
                },
                "source": "keyword",
            }
        ]

    async def fake_arbitrate_revision(self, prompt: str):
        return ArbitrationResponse(
            verdict="NEEDS_REVISION",
            score=0.73,
            reasoning="Description and property naming are ambiguous",
            recommended_code="evt_checkout_completed",
            risks=[
                "Property uid is ambiguous; use user_id",
                "Event description lacks business trigger context",
            ],
            suggestions=[
                {
                    "title": "Clarify description",
                    "rationale": "Provide concrete trigger and business meaning",
                    "patch": {
                        "description": "Triggered when user confirms checkout order and payment request is created",
                    },
                },
                {
                    "title": "Normalize schema fields",
                    "rationale": "Align with naming conventions",
                    "patch": {
                        "properties": {
                            "user_id": "string",
                            "order_amount": "number",
                        }
                    },
                },
            ],
        )

    async def fake_arbitrate_approve(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.95,
            reasoning="Event definition is now consistent with catalog conventions",
            recommended_code=None,
            risks=[],
            suggestions=[],
        )

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate_revision)

    first_check_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": created["name"],
            "description": created["description"],
            "properties": created["properties"],
        },
        headers=headers,
    )
    assert first_check_resp.status_code == 200
    first_check = first_check_resp.json()["data"]
    assert first_check["verdict"] == "NEEDS_REVISION"
    assert first_check["event_id"] == event_id
    assert len(first_check["risks"]) == 2
    assert len(first_check["suggestions"]) == 2
    assert first_check["check_id"] > 0

    apply_resp = await client.post(
        f"/api/v1/governance/{first_check['check_id']}/apply-suggestions",
        json={"event_id": event_id, "suggestion_indexes": [0, 1]},
        headers=headers,
    )
    assert apply_resp.status_code == 200
    apply_data = apply_resp.json()["data"]
    assert apply_data["event"]["version"] == "1.0.1"
    assert apply_data["event"]["description"].startswith("Triggered when user confirms checkout")
    assert "user_id" in apply_data["event"]["properties"]
    assert "order_amount" in apply_data["event"]["properties"]

    detail_resp = await client.get(f"/api/v1/events/{event_id}/detail", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert detail["event"]["governance_status"] == "NEEDS_REVISION"
    assert len(detail["version_history"]) >= 1
    assert detail["version_history"][0]["to_version"] == "1.0.1"
    assert detail["governance_records"][0]["verdict"] == "NEEDS_REVISION"

    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate_approve)

    second_check_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": apply_data["event"]["name"],
            "description": apply_data["event"]["description"],
            "properties": apply_data["event"]["properties"],
        },
        headers=headers,
    )
    assert second_check_resp.status_code == 200
    second_check = second_check_resp.json()["data"]
    assert second_check["verdict"] == "APPROVE"
    assert second_check["suggestions"] == []

    approved_filter_resp = await client.get(
        "/api/v1/events/",
        params={"governance_status": "APPROVED"},
        headers=headers,
    )
    assert approved_filter_resp.status_code == 200
    approved_rows = approved_filter_resp.json()["data"]
    assert any(row["id"] == event_id for row in approved_rows)

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    actions = {row["action"] for row in audit_resp.json()["data"]}
    assert "GOVERNANCE_NEEDS_REVISION" in actions
    assert "GOVERNANCE_APPLY_SUGGESTIONS" in actions
    assert "GOVERNANCE_APPROVE" in actions
