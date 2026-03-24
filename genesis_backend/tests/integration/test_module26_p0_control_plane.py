import time

import pytest
from httpx import AsyncClient

from src.infrastructure.database.models.contract_artifact import ContractArtifact
from src.infrastructure.database.models.governance_decision_record import GovernanceDecisionRecord
from src.infrastructure.database.models.inference_candidate import InferenceCandidate
from src.infrastructure.database.models.observation_source_profile import ObservationSourceProfile
from src.infrastructure.database.session import async_session_factory


def _unique_suffix() -> str:
    return str(int(time.time() * 1000))


def _context_headers(access_token: str, context: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


@pytest.mark.asyncio
async def test_p0_overview_list_and_detail_endpoints(client: AsyncClient):
    suffix = _unique_suffix()
    email = f"it_p0_{suffix}@demo.local"
    password = "demo123456"
    name = f"P0 User {suffix}"

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
    context = register_data["default_context"]
    headers = _context_headers(register_data["access_token"], context)
    project_id = context["project_id"]

    async with async_session_factory() as session:
        source_profile = ObservationSourceProfile(
            project_id=project_id,
            channel_id=None,
            event_name=f"evt_obs_{suffix}",
            heat="HOT",
            total_events=128,
            accepted_events=120,
            sdk_version="1.0.0",
            profile_payload={"source": "integration-test", "heat": "HOT"},
        )
        inference_candidate = InferenceCandidate(
            project_id=project_id,
            candidate_type="SEMANTIC_MAPPING",
            status="PENDING",
            target_field=f"user_id_{suffix}",
            source_paths=["payload.user_id"],
            confidence_score=0.93,
            field_frequency=64,
            proposed_by="ai",
            reasoning="High-confidence semantic mapping candidate",
            recommended_action="FAST_REVIEW",
        )
        governance_record = GovernanceDecisionRecord(
            project_id=project_id,
            target_field=f"user_id_{suffix}",
            decision_status="PENDING",
            queue_status="OPEN",
            confidence_score=0.93,
            field_frequency=64,
            recommended_action="FAST_REVIEW",
        )
        contract_artifact = ContractArtifact(
            project_id=project_id,
            event_code=f"evt_contract_{suffix}",
            contract_name=f"contract.evt_contract_{suffix}",
            serving_status="PUBLISHED",
            approved_rule_count=3,
        )
        session.add_all([source_profile, inference_candidate, governance_record, contract_artifact])
        await session.commit()
        await session.refresh(source_profile)
        await session.refresh(inference_candidate)
        await session.refresh(governance_record)
        await session.refresh(contract_artifact)

    overview_resp = await client.get("/api/v1/p0/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert "summary" in overview_data
    assert "observation" in overview_data
    assert "inference" in overview_data
    assert "governance" in overview_data
    assert "contract" in overview_data

    source_list_resp = await client.get(
        "/api/v1/p0/source-profiles",
        headers=headers,
        params={"heat": "HOT", "limit": 20},
    )
    assert source_list_resp.status_code == 200
    source_items = source_list_resp.json()["data"]["items"]
    assert any(item["id"] == source_profile.id for item in source_items)

    source_detail_resp = await client.get(
        f"/api/v1/p0/source-profiles/{source_profile.id}",
        headers=headers,
    )
    assert source_detail_resp.status_code == 200
    assert source_detail_resp.json()["data"]["event_name"] == source_profile.event_name

    inference_list_resp = await client.get(
        "/api/v1/p0/inference-candidates",
        headers=headers,
        params={"candidate_type": "SEMANTIC_MAPPING", "limit": 20},
    )
    assert inference_list_resp.status_code == 200
    inference_items = inference_list_resp.json()["data"]["items"]
    assert any(item["id"] == inference_candidate.id for item in inference_items)

    inference_detail_resp = await client.get(
        f"/api/v1/p0/inference-candidates/{inference_candidate.id}",
        headers=headers,
    )
    assert inference_detail_resp.status_code == 200
    assert inference_detail_resp.json()["data"]["recommended_action"] == "FAST_REVIEW"

    governance_list_resp = await client.get(
        "/api/v1/p0/governance-records",
        headers=headers,
        params={"queue_status": "OPEN", "limit": 20},
    )
    assert governance_list_resp.status_code == 200
    governance_items = governance_list_resp.json()["data"]["items"]
    assert any(item["id"] == governance_record.id for item in governance_items)

    governance_detail_resp = await client.get(
        f"/api/v1/p0/governance-records/{governance_record.id}",
        headers=headers,
    )
    assert governance_detail_resp.status_code == 200
    assert governance_detail_resp.json()["data"]["queue_status"] == "OPEN"

    contract_list_resp = await client.get(
        "/api/v1/p0/contract-artifacts",
        headers=headers,
        params={"serving_status": "PUBLISHED", "limit": 20},
    )
    assert contract_list_resp.status_code == 200
    contract_items = contract_list_resp.json()["data"]["items"]
    assert any(item["id"] == contract_artifact.id for item in contract_items)

    contract_detail_resp = await client.get(
        f"/api/v1/p0/contract-artifacts/{contract_artifact.id}",
        headers=headers,
    )
    assert contract_detail_resp.status_code == 200
    assert contract_detail_resp.json()["data"]["contract_name"] == contract_artifact.contract_name
