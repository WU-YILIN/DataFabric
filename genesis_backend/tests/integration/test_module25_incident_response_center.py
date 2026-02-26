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


async def _login_admin(client: AsyncClient) -> tuple[dict[str, str], dict]:
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "admin@demo.local",
            "password": "demo123456",
        },
    )
    assert login_resp.status_code == 200
    data = login_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"]), data["default_context"]


async def _register_viewer(client: AsyncClient, tag: str) -> dict[str, str]:
    suffix = _unique_suffix()
    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod25_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module25 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module25_incident_response_center_full_flow(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    suffix = _unique_suffix()

    overview_resp = await client.get("/api/v1/incidents/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert "summary" in overview_data

    create_resp = await client.post(
        "/api/v1/incidents/cases",
        json={
            "source_type": "ALERT",
            "source_id": f"alert-{suffix}",
            "title": f"payment failure spike {suffix}",
            "summary": "Payment failures increasing in prod",
            "severity": "HIGH",
            "assignee": "oncall@demo.local",
            "context_payload": {"service": "checkout", "env": "prod"},
            "impact_payload": {"users_affected": 120},
            "resolution_payload": {"status": "pending"},
            "note": "created by module25 test",
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 200
    case_data = create_resp.json()["data"]
    case_id = case_data["id"]
    assert case_data["status"] == "OPEN"
    assert case_data["severity"] == "HIGH"
    assert case_data["owner"] == "admin@demo.local"

    list_resp = await client.get(
        "/api/v1/incidents/cases",
        params={"q": suffix, "status": "OPEN"},
        headers=admin_headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(item["id"] == case_id for item in list_data["items"])

    detail_resp = await client.get(f"/api/v1/incidents/cases/{case_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["case"]["id"] == case_id
    assert len(detail_data["timeline"]) >= 1

    update_resp = await client.patch(
        f"/api/v1/incidents/cases/{case_id}",
        json={
            "summary": "Updated summary for investigation",
            "severity": "CRITICAL",
            "assignee": "incident-commander@demo.local",
            "note": "metadata refinement",
            "impact_payload": {"users_affected": 180},
        },
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["severity"] == "CRITICAL"
    assert update_resp.json()["data"]["assignee"] == "incident-commander@demo.local"

    triage_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "TRIAGE", "note": "triage started"},
        headers=admin_headers,
    )
    assert triage_resp.status_code == 200
    assert triage_resp.json()["data"]["status"] == "TRIAGED"

    investigate_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "START_INVESTIGATION", "note": "root cause analysis"},
        headers=admin_headers,
    )
    assert investigate_resp.status_code == 200
    assert investigate_resp.json()["data"]["status"] == "INVESTIGATING"

    mitigate_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "MITIGATE", "impact_payload": {"users_affected": 40}, "note": "traffic shifted"},
        headers=admin_headers,
    )
    assert mitigate_resp.status_code == 200
    assert mitigate_resp.json()["data"]["status"] == "MITIGATED"

    resolve_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={
            "action": "RESOLVE",
            "resolution_payload": {"root_cause": "cache invalidation issue", "fix": "rollback release"},
            "note": "resolved by rollback",
        },
        headers=admin_headers,
    )
    assert resolve_resp.status_code == 200
    assert resolve_resp.json()["data"]["status"] == "RESOLVED"

    runbook_resp = await client.post(
        "/api/v1/knowledge/documents",
        json={
            "doc_type": "RUNBOOK",
            "module": "MONITORING",
            "title": f"incident runbook {suffix}",
            "summary": "Runbook for payment incidents",
            "content": "# Runbook\n\n1. Detect\n2. Mitigate\n3. Recover",
            "status": "DRAFT",
        },
        headers=admin_headers,
    )
    assert runbook_resp.status_code == 200
    runbook_id = runbook_resp.json()["data"]["document"]["id"]

    link_runbook_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "LINK_RUNBOOK", "runbook_doc_id": runbook_id, "note": "link official runbook"},
        headers=admin_headers,
    )
    assert link_runbook_resp.status_code == 200
    assert link_runbook_resp.json()["data"]["runbook_doc_id"] == runbook_id

    close_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "CLOSE", "note": "incident closed after verification"},
        headers=admin_headers,
    )
    assert close_resp.status_code == 200
    assert close_resp.json()["data"]["status"] == "CLOSED"

    reopen_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "REOPEN", "note": "new regression detected"},
        headers=admin_headers,
    )
    assert reopen_resp.status_code == 200
    assert reopen_resp.json()["data"]["status"] == "OPEN"

    assign_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "ASSIGN", "assignee": "new-oncall@demo.local", "note": "handover"},
        headers=admin_headers,
    )
    assert assign_resp.status_code == 200
    assert assign_resp.json()["data"]["assignee"] == "new-oncall@demo.local"

    add_note_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "ADD_NOTE", "note": "postmortem scheduled"},
        headers=admin_headers,
    )
    assert add_note_resp.status_code == 200

    final_detail_resp = await client.get(f"/api/v1/incidents/cases/{case_id}", headers=admin_headers)
    assert final_detail_resp.status_code == 200
    final_detail_data = final_detail_resp.json()["data"]
    assert final_detail_data["case"]["status"] == "OPEN"
    assert len(final_detail_data["timeline"]) >= 10

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "INCIDENT_CREATE" in actions
    assert "INCIDENT_UPDATE" in actions
    assert "INCIDENT_TRIAGE" in actions
    assert "INCIDENT_LINK_RUNBOOK" in actions
    assert "INCIDENT_CLOSE" in actions


@pytest.mark.asyncio
async def test_module25_incident_response_center_permission_guard(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/incidents/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/incidents/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_create_resp = await client.post(
        "/api/v1/incidents/cases",
        json={
            "source_type": "OTHER",
            "source_id": "viewer-attempt",
            "title": f"forbidden create {_unique_suffix()}",
            "severity": "LOW",
        },
        headers=viewer_headers,
    )
    assert viewer_create_resp.status_code == 403

    create_target_resp = await client.post(
        "/api/v1/incidents/cases",
        json={
            "source_type": "OTHER",
            "source_id": f"permission-{_unique_suffix()}",
            "title": f"permission target {_unique_suffix()}",
            "severity": "MEDIUM",
        },
        headers=admin_headers,
    )
    assert create_target_resp.status_code == 200
    case_id = create_target_resp.json()["data"]["id"]

    viewer_update_resp = await client.patch(
        f"/api/v1/incidents/cases/{case_id}",
        json={"summary": "viewer should not update"},
        headers=viewer_headers,
    )
    assert viewer_update_resp.status_code == 403

    viewer_action_resp = await client.post(
        f"/api/v1/incidents/cases/{case_id}/actions",
        json={"action": "TRIAGE"},
        headers=viewer_headers,
    )
    assert viewer_action_resp.status_code == 403
