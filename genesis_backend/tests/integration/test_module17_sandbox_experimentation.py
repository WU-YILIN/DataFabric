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


async def _register_user(client: AsyncClient, tag: str) -> dict[str, str]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod17_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module17 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module17_sandbox_event_experiment_full_flow(client: AsyncClient):
    headers = await _register_user(client, "event_flow")
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod17_{suffix}",
            "name": f"Sandbox Event {suffix}",
            "description": "module17 baseline event",
            "domain": "sandbox",
            "properties": {"user_id": "string", "order_id": "string"},
        },
        headers=headers,
    )
    assert event_resp.status_code == 201
    event = event_resp.json()["data"]

    create_resp = await client.post(
        "/api/v1/sandbox/experiments",
        json={
            "experiment_type": "EVENT_EXPERIMENT",
            "title": f"Event experiment {suffix}",
            "description": "validate schema and naming",
            "source_type": "TRACKING_EVENT",
            "source_id": str(event["id"]),
            "config_payload": {"strict": True},
        },
        headers=headers,
    )
    assert create_resp.status_code == 201
    experiment = create_resp.json()["data"]
    experiment_id = experiment["id"]

    options_resp = await client.get(
        "/api/v1/sandbox/options",
        params={"experiment_type": "EVENT_EXPERIMENT"},
        headers=headers,
    )
    assert options_resp.status_code == 200
    options_data = options_resp.json()["data"]
    assert "TRACKING_EVENT" in options_data["source_types"]
    assert any(item["id"] == str(event["id"]) for item in options_data["source_options"]["TRACKING_EVENT"])

    list_resp = await client.get(
        "/api/v1/sandbox/experiments",
        params={"experiment_type": "EVENT_EXPERIMENT"},
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(item["id"] == experiment_id for item in list_data["items"])

    run_resp = await client.post(
        f"/api/v1/sandbox/experiments/{experiment_id}/runs",
        json={
            "sample_size": 2000,
            "traffic_ratio": 0.25,
            "notes": "run from integration test",
            "candidate_payloads": [
                {
                    "key": "candidate_a",
                    "title": "strict mode",
                    "config": {
                        "strict": True,
                        "event_patch": {
                            "description": "updated via sandbox promotion",
                            "properties": {
                                "user_id": "string",
                                "order_id": "string",
                                "session_id": "string",
                            },
                        },
                    },
                },
                {
                    "key": "candidate_b",
                    "title": "normal mode",
                    "config": {
                        "strict": False,
                    },
                },
            ],
        },
        headers=headers,
    )
    assert run_resp.status_code == 200
    run_data = run_resp.json()["data"]
    assert run_data["run"]["run_no"] >= 1
    assert run_data["recommendation"]["best_candidate_key"] in {"candidate_a", "candidate_b"}

    detail_resp = await client.get(f"/api/v1/sandbox/experiments/{experiment_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["experiment"]["status"] == "COMPLETED"
    assert len(detail_data["runs"]) >= 1

    promote_resp = await client.post(
        f"/api/v1/sandbox/experiments/{experiment_id}/promote",
        json={"candidate_key": "candidate_a", "note": "promote from test"},
        headers=headers,
    )
    assert promote_resp.status_code == 200
    promote_data = promote_resp.json()["data"]
    assert promote_data["experiment"]["status"] == "PROMOTED"
    assert promote_data["promotion_target"]["target_type"] == "TRACKING_EVENT"

    event_after_resp = await client.get(f"/api/v1/events/{event['id']}/detail", headers=headers)
    assert event_after_resp.status_code == 200
    event_after = event_after_resp.json()["data"]["event"]
    assert "session_id" in event_after["properties"]

    overview_resp = await client.get("/api/v1/sandbox/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert overview_data["summary"]["total_experiments"] >= 1
    assert overview_data["summary"]["promoted_count"] >= 1
    audit_actions = {item["action"] for item in overview_data["recent_activity"]}
    assert "SANDBOX_EXPERIMENT_CREATE" in audit_actions
    assert "SANDBOX_EXPERIMENT_RUN" in audit_actions
    assert "SANDBOX_EXPERIMENT_PROMOTE_EVENT" in audit_actions


@pytest.mark.asyncio
async def test_module17_sandbox_source_type_validation(client: AsyncClient):
    headers = await _register_user(client, "compatibility")

    create_resp = await client.post(
        "/api/v1/sandbox/experiments",
        json={
            "experiment_type": "PIPELINE_EXPERIMENT",
            "title": "invalid source test",
            "source_type": "TRACKING_EVENT",
            "source_id": "1",
        },
        headers=headers,
    )
    assert create_resp.status_code == 400


@pytest.mark.asyncio
async def test_module17_sandbox_requires_bearer_user_context(client: AsyncClient):
    api_key_headers = {"X-API-KEY": "demo-key-001"}
    resp = await client.get("/api/v1/sandbox/overview", headers=api_key_headers)
    assert resp.status_code == 403
