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
            "email": f"it_mod15_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module15 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module15_knowledge_document_flow(client: AsyncClient):
    headers = await _register_user(client, "flow")
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod15_{suffix}",
            "name": f"Knowledge Event {suffix}",
            "description": "module15 event for related docs",
            "domain": "knowledge",
            "properties": {"user_id": "string"},
        },
        headers=headers,
    )
    assert event_resp.status_code == 201
    event_id = event_resp.json()["data"]["id"]

    create_resp = await client.post(
        "/api/v1/knowledge/documents",
        json={
            "doc_type": "EVENT_SPEC",
            "module": "EVENTS",
            "title": f"Event Spec {suffix}",
            "summary": "First draft of event spec",
            "template_key": "EVENT_SPEC",
            "format": "MARKDOWN",
            "status": "DRAFT",
            "tags": ["module15", "event"],
            "related_objects": [
                {
                    "source_type": "TRACKING_EVENT",
                    "source_id": str(event_id),
                    "label": "primary event",
                }
            ],
            "meta_payload": {"audience": "analytics"},
            "change_note": "initial draft",
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    create_data = create_resp.json()["data"]
    document = create_data["document"]
    document_id = document["id"]
    assert document["status"] == "DRAFT"
    assert document["version_no"] == 1
    assert len(create_data["version_history"]) >= 1
    assert create_data["version_history"][0]["action"] in {"CREATE", "PUBLISH"}
    assert document["related_objects"][0]["exists"] is True

    list_resp = await client.get(
        "/api/v1/knowledge/documents",
        params={"module": "EVENTS", "tag": "module15"},
        headers=headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(item["id"] == document_id for item in list_data["items"])

    related_resp = await client.get(
        "/api/v1/knowledge/documents/related",
        params={"source_type": "TRACKING_EVENT", "source_id": str(event_id)},
        headers=headers,
    )
    assert related_resp.status_code == 200
    related_items = related_resp.json()["data"]["items"]
    assert any(item["id"] == document_id for item in related_items)

    update_resp = await client.patch(
        f"/api/v1/knowledge/documents/{document_id}",
        json={
            "summary": "Updated event spec summary",
            "content": "# Event Overview\n\nUpdated body for module15 test.",
            "tags": ["module15", "event", "published-ready"],
            "change_note": "polish wording",
        },
        headers=headers,
    )
    assert update_resp.status_code == 200
    update_doc = update_resp.json()["data"]["document"]
    assert update_doc["version_no"] == 2
    assert "published-ready" in update_doc["tags"]

    comment_resp = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/comments",
        json={"content": "Please review this draft @qa_team"},
        headers=headers,
    )
    assert comment_resp.status_code == 200
    assert "qa_team" in comment_resp.json()["data"]["mentions"]

    publish_resp = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/actions",
        json={"action": "PUBLISH", "change_note": "ready for team"},
        headers=headers,
    )
    assert publish_resp.status_code == 200
    publish_doc = publish_resp.json()["data"]["document"]
    assert publish_doc["status"] == "PUBLISHED"
    assert publish_doc["version_no"] == 3
    assert publish_doc["published_at"] is not None

    detail_resp = await client.get(f"/api/v1/knowledge/documents/{document_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    version_actions = {item["action"] for item in detail_data["version_history"]}
    assert "CREATE" in version_actions
    assert "UPDATE" in version_actions
    assert "PUBLISH" in version_actions
    assert len(detail_data["comments"]) >= 1

    create_version = next(item for item in detail_data["version_history"] if item["action"] == "CREATE")
    restore_resp = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/versions/{create_version['id']}/restore",
        json={"change_note": "roll back to initial"},
        headers=headers,
    )
    assert restore_resp.status_code == 200
    restored_doc = restore_resp.json()["data"]["document"]
    assert restored_doc["version_no"] == 4
    assert "Event Overview" in restored_doc["content"]

    overview_resp = await client.get("/api/v1/knowledge/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert overview_data["summary"]["total_docs"] >= 1
    assert overview_data["summary"]["comments_7d"] >= 1
    assert len(overview_data["templates"]) >= 1

    audit_resp = await client.get("/api/v1/audit/logs", headers=headers)
    assert audit_resp.status_code == 200
    audit_actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "KNOWLEDGE_DOC_CREATE" in audit_actions
    assert "KNOWLEDGE_DOC_UPDATE" in audit_actions
    assert "KNOWLEDGE_DOC_COMMENT" in audit_actions
    assert "KNOWLEDGE_DOC_PUBLISH" in audit_actions
    assert "KNOWLEDGE_DOC_RESTORE" in audit_actions


@pytest.mark.asyncio
async def test_module15_knowledge_archive_and_related_visibility(client: AsyncClient):
    headers = await _register_user(client, "archive")
    suffix = _unique_suffix()

    event_resp = await client.post(
        "/api/v1/events/",
        json={
            "code": f"evt_mod15_archive_{suffix}",
            "name": f"Knowledge Archive Event {suffix}",
            "description": "module15 archive event",
            "domain": "knowledge",
            "properties": {"user_id": "string"},
        },
        headers=headers,
    )
    assert event_resp.status_code == 201
    event_id = event_resp.json()["data"]["id"]

    create_resp = await client.post(
        "/api/v1/knowledge/documents",
        json={
            "doc_type": "RUNBOOK",
            "module": "MONITORING",
            "title": f"Runbook Archive {suffix}",
            "summary": "Archive visibility test",
            "content": "# Archive test\n\nRunbook body.",
            "status": "PUBLISHED",
            "tags": ["module15", "archive"],
            "related_objects": [
                {"source_type": "TRACKING_EVENT", "source_id": str(event_id)},
            ],
        },
        headers=headers,
    )
    assert create_resp.status_code == 200
    document_id = create_resp.json()["data"]["document"]["id"]

    archive_resp = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/actions",
        json={"action": "ARCHIVE", "change_note": "stale doc"},
        headers=headers,
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["data"]["document"]["status"] == "ARCHIVED"

    archived_list_resp = await client.get(
        "/api/v1/knowledge/documents",
        params={"status": "ARCHIVED"},
        headers=headers,
    )
    assert archived_list_resp.status_code == 200
    assert any(item["id"] == document_id for item in archived_list_resp.json()["data"]["items"])

    related_default_resp = await client.get(
        "/api/v1/knowledge/documents/related",
        params={"source_type": "TRACKING_EVENT", "source_id": str(event_id)},
        headers=headers,
    )
    assert related_default_resp.status_code == 200
    assert all(item["id"] != document_id for item in related_default_resp.json()["data"]["items"])

    related_with_archived_resp = await client.get(
        "/api/v1/knowledge/documents/related",
        params={"source_type": "TRACKING_EVENT", "source_id": str(event_id), "include_archived": True},
        headers=headers,
    )
    assert related_with_archived_resp.status_code == 200
    assert any(item["id"] == document_id for item in related_with_archived_resp.json()["data"]["items"])

    unarchive_resp = await client.post(
        f"/api/v1/knowledge/documents/{document_id}/actions",
        json={"action": "UNARCHIVE", "change_note": "needs edits"},
        headers=headers,
    )
    assert unarchive_resp.status_code == 200
    assert unarchive_resp.json()["data"]["document"]["status"] == "DRAFT"
