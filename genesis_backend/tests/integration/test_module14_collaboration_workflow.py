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
            "email": f"it_mod14_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module14 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


async def _register_user_with_id(client: AsyncClient, tag: str) -> tuple[dict[str, str], int]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod14_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module14 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"]), data["user"]["id"]


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
async def test_module14_collaboration_event_workflow_flow(client: AsyncClient):
    initiator_headers = await _register_user(client, "initiator")
    approver_headers = await _admin_headers(client)
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod14_{suffix}",
            "name": f"Collab Event {suffix}",
            "description": "module14 collab event",
            "domain": "collaboration",
            "owner": "mod14-owner",
            "properties": {"user_id": "string"},
        },
        headers=initiator_headers,
    )
    assert event_resp.status_code == 201
    event = event_resp.json()["data"]

    create_workflow_resp = await client.post(
        "/api/v1/collaboration/workflows",
        json={
            "workflow_type": "EVENT_GOVERNANCE",
            "source_type": "TRACKING_EVENT",
            "source_id": str(event["id"]),
            "title": f"Approve Event {event['code']}",
            "description": "Need approval for event governance",
            "priority": "HIGH",
            "assignee_role": "OWNER",
            "context_payload": {"governance_check": "manual", "risk_level": "high"},
        },
        headers=initiator_headers,
    )
    assert create_workflow_resp.status_code == 200 or create_workflow_resp.status_code == 201
    workflow = create_workflow_resp.json()["data"]["workflow"]
    workflow_id = workflow["id"]
    assert workflow["status"] == "PENDING_APPROVAL"

    initiator_overview_resp = await client.get("/api/v1/collaboration/overview", headers=initiator_headers)
    assert initiator_overview_resp.status_code == 200
    initiator_overview = initiator_overview_resp.json()["data"]
    assert initiator_overview["summary"]["initiated_count"] >= 1
    assert any(item["id"] == workflow_id for item in initiator_overview["initiated_workflows"])

    approver_list_resp = await client.get(
        "/api/v1/collaboration/workflows",
        params={"my_todos_only": True},
        headers=approver_headers,
    )
    assert approver_list_resp.status_code == 200
    approver_items = approver_list_resp.json()["data"]["items"]
    target_item = next((item for item in approver_items if item["id"] == workflow_id), None)
    assert target_item is not None
    assert target_item["is_my_todo"] is True

    comment_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/comments",
        json={"content": "Please review this @admin workflow."},
        headers=initiator_headers,
    )
    assert comment_resp.status_code == 200
    comment_data = comment_resp.json()["data"]
    assert "admin" in comment_data["mentions"]

    revision_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/actions",
        json={"action": "REQUEST_REVISION", "note": "Need better naming."},
        headers=approver_headers,
    )
    assert revision_resp.status_code == 200
    revision_data = revision_resp.json()["data"]
    assert revision_data["workflow"]["status"] == "REVISION_REQUIRED"
    assert revision_data["backwrite"]["updated"] is True
    assert revision_data["backwrite"]["status"] == "NEEDS_REVISION"

    event_detail_after_revision = await client.get(
        f"/api/v1/events/{event['id']}/detail",
        headers=initiator_headers,
    )
    assert event_detail_after_revision.status_code == 200
    assert event_detail_after_revision.json()["data"]["event"]["governance_status"] == "NEEDS_REVISION"

    approve_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/actions",
        json={"action": "APPROVE", "note": "Looks good now."},
        headers=approver_headers,
    )
    assert approve_resp.status_code == 200
    approve_data = approve_resp.json()["data"]
    assert approve_data["workflow"]["status"] == "COMPLETED"
    assert approve_data["backwrite"]["updated"] is True
    assert approve_data["backwrite"]["status"] == "APPROVED"

    event_detail_after_approve = await client.get(
        f"/api/v1/events/{event['id']}/detail",
        headers=initiator_headers,
    )
    assert event_detail_after_approve.status_code == 200
    assert event_detail_after_approve.json()["data"]["event"]["governance_status"] == "APPROVED"

    workflow_detail_resp = await client.get(
        f"/api/v1/collaboration/workflows/{workflow_id}",
        headers=initiator_headers,
    )
    assert workflow_detail_resp.status_code == 200
    workflow_detail = workflow_detail_resp.json()["data"]
    actions = [item["action"] for item in workflow_detail["action_history"]]
    assert "CREATE" in actions
    assert "COMMENT" in actions
    assert "REQUEST_REVISION" in actions
    assert "APPROVE" in actions

    audit_resp = await client.get("/api/v1/audit/logs", headers=initiator_headers)
    assert audit_resp.status_code == 200
    audit_actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "COLLAB_WORKFLOW_CREATE" in audit_actions
    assert "COLLAB_WORKFLOW_COMMENT" in audit_actions
    assert "COLLAB_WORKFLOW_ACTION" in audit_actions


@pytest.mark.asyncio
async def test_module14_collaboration_reject_backwrites_dq_rule(client: AsyncClient):
    initiator_headers = await _register_user(client, "dq")
    approver_headers = await _admin_headers(client)
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod14_dq_{suffix}",
            "name": f"Collab DQ Event {suffix}",
            "description": "module14 dq event",
            "domain": "dq",
            "properties": {"user_id": "string"},
        },
        headers=initiator_headers,
    )
    assert event_resp.status_code == 201
    event_id = event_resp.json()["data"]["id"]

    rule_resp = await client.post(
        "/api/v1/data-quality/rules",
        json={
            "name": f"dq_mod14_{suffix}",
            "event_id": event_id,
            "rule_type": "NOT_NULL",
            "target_field": "user_id",
            "operator": "IS_NOT_NULL",
            "threshold": {"max_failure_rate": 0.01},
            "alert_channels": ["email"],
            "severity": "HIGH",
            "status": "ACTIVE",
        },
        headers=initiator_headers,
    )
    assert rule_resp.status_code == 201
    rule_id = rule_resp.json()["data"]["id"]

    workflow_resp = await client.post(
        "/api/v1/collaboration/workflows",
        json={
            "workflow_type": "DQ_RULE_CHANGE",
            "source_type": "DATA_QUALITY_RULE",
            "source_id": str(rule_id),
            "title": "Deprecate risky DQ rule",
            "description": "Rule has too many false positives",
            "priority": "MEDIUM",
            "assignee_role": "OWNER",
        },
        headers=initiator_headers,
    )
    assert workflow_resp.status_code == 200 or workflow_resp.status_code == 201
    workflow_id = workflow_resp.json()["data"]["workflow"]["id"]

    reject_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/actions",
        json={"action": "REJECT", "note": "Reject and deprecate this rule"},
        headers=approver_headers,
    )
    assert reject_resp.status_code == 200
    reject_data = reject_resp.json()["data"]
    assert reject_data["workflow"]["status"] == "REJECTED"
    assert reject_data["backwrite"]["updated"] is True
    assert reject_data["backwrite"]["status"] == "DEPRECATED"

    rule_detail_resp = await client.get(f"/api/v1/data-quality/rules/{rule_id}/detail", headers=initiator_headers)
    assert rule_detail_resp.status_code == 200
    assert rule_detail_resp.json()["data"]["rule"]["status"] == "DEPRECATED"


@pytest.mark.asyncio
async def test_module14_collaboration_assign_start_approve_pipeline_flow(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
):
    initiator_headers = await _register_user(client, "pipeline_owner")
    assignee_headers, assignee_user_id = await _register_user_with_id(client, "pipeline_assignee")
    suffix = _unique_suffix()
    event_code = f"evt_mod14_pipeline_{suffix}"

    create_event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": event_code,
            "name": f"Module14 Pipeline Event {suffix}",
            "description": "pipeline workflow source",
            "domain": "streaming",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
        },
        headers=initiator_headers,
    )
    assert create_event_resp.status_code == 201
    event_id = create_event_resp.json()["data"]["id"]

    def fake_llm_init(self):
        self.client = None

    async def fake_hybrid_search(self, query_text: str, query_vector: list[float], limit: int = 10):
        return []

    async def fake_arbitrate(self, prompt: str):
        return ArbitrationResponse(
            verdict="APPROVE",
            score=0.99,
            reasoning="Module14 pipeline event approved",
            recommended_code=None,
        )

    monkeypatch.setattr(LLMAdapter, "__init__", fake_llm_init)
    monkeypatch.setattr(SearchEngine, "hybrid_search", fake_hybrid_search)
    monkeypatch.setattr(LLMAdapter, "arbitrate", fake_arbitrate)

    approve_event_resp = await client.post(
        "/api/v1/governance/check",
        json={
            "event_id": event_id,
            "name": f"Module14 Pipeline Event {suffix}",
            "description": "pipeline workflow source",
            "properties": {"user_id": "string", "timestamp": "iso8601"},
        },
        headers=initiator_headers,
    )
    assert approve_event_resp.status_code == 200

    provision_resp = await client.post(
        "/api/v1/pipelines/provision",
        json={"event_code": event_code},
        headers=initiator_headers,
    )
    assert provision_resp.status_code == 201
    pipeline = provision_resp.json()["data"]
    pipeline_id = pipeline["id"]

    create_workflow_resp = await client.post(
        "/api/v1/collaboration/workflows",
        json={
            "workflow_type": "PIPELINE_CHANGE",
            "source_type": "PIPELINE",
            "source_id": str(pipeline_id),
            "title": f"Review pipeline {pipeline_id}",
            "description": "Assign, start and approve this pipeline change",
            "priority": "HIGH",
        },
        headers=initiator_headers,
    )
    assert create_workflow_resp.status_code == 200 or create_workflow_resp.status_code == 201
    workflow_id = create_workflow_resp.json()["data"]["workflow"]["id"]

    assign_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/actions",
        json={"action": "ASSIGN", "assignee_user_id": assignee_user_id, "note": "Please take this pipeline review"},
        headers=initiator_headers,
    )
    assert assign_resp.status_code == 200
    assign_data = assign_resp.json()["data"]
    assert assign_data["workflow"]["current_assignee_user_id"] == assignee_user_id
    assert any(
        task["status"] == "OPEN" and task["assignee_user_id"] == assignee_user_id
        for task in assign_data["tasks"]
    )

    assignee_todos_resp = await client.get(
        "/api/v1/collaboration/workflows",
        params={"my_todos_only": True},
        headers=assignee_headers,
    )
    assert assignee_todos_resp.status_code == 200
    assert any(item["id"] == workflow_id and item["is_my_todo"] is True for item in assignee_todos_resp.json()["data"]["items"])

    start_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/actions",
        json={"action": "START", "note": "Started handling pipeline review"},
        headers=assignee_headers,
    )
    assert start_resp.status_code == 200
    assert start_resp.json()["data"]["workflow"]["status"] == "IN_PROGRESS"
    assert start_resp.json()["data"]["workflow"]["started_at"] is not None

    approve_workflow_resp = await client.post(
        f"/api/v1/collaboration/workflows/{workflow_id}/actions",
        json={"action": "APPROVE", "note": "Approved for rollout"},
        headers=assignee_headers,
    )
    assert approve_workflow_resp.status_code == 200
    approve_workflow_data = approve_workflow_resp.json()["data"]
    assert approve_workflow_data["workflow"]["status"] == "COMPLETED"
    assert approve_workflow_data["backwrite"]["updated"] is True
    assert approve_workflow_data["backwrite"]["entity"] == "PIPELINE"
    assert approve_workflow_data["backwrite"]["entity_id"] == pipeline_id

    pipeline_detail_resp = await client.get(f"/api/v1/pipelines/{pipeline_id}", headers=initiator_headers)
    assert pipeline_detail_resp.status_code == 200
    pipeline_detail = pipeline_detail_resp.json()["data"]
    assert pipeline_detail["config"]["collaboration_workflow_id"] == workflow_id
    assert pipeline_detail["config"]["collaboration_last_action"] == "APPROVE"
    assert pipeline_detail["config"]["collaboration_last_note"] == "Approved for rollout"
