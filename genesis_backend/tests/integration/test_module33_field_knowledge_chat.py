import sqlite3
import time
from pathlib import Path

import pytest
from httpx import AsyncClient


def _unique_suffix() -> str:
    return str(int(time.time() * 1000))


def _context_headers(access_token: str, context: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


def _build_sqlite_sample(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            create table customers (
              id integer primary key,
              user_id text not null,
              created_at text not null,
              status text
            )
            """
        )
        conn.execute(
            """
            insert into customers (user_id, created_at, status)
            values
              ('u_001', '2026-03-18T10:00:00Z', 'ACTIVE'),
              ('u_002', '2026-03-18T11:00:00Z', 'INACTIVE')
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_field_level_facts_knowledge_refs_and_chat_citations(client: AsyncClient, tmp_path: Path):
    suffix = _unique_suffix()
    instance_name = f"field_sqlite_{suffix}"
    sqlite_path = tmp_path / f"field_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_field_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Field Test {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])

    create_resp = await client.post(
        "/api/v1/source-intake/instances",
        headers=headers,
        json={
            "instance_name": instance_name,
            "connector_key": "sqlite",
            "config": {
                "file_path": str(sqlite_path),
                "namespace": "main",
                "memory_scope_default": "PRIVATE",
            },
        },
    )
    assert create_resp.status_code == 200
    instance_id = create_resp.json()["data"]["id"]

    assert (await client.post(f"/api/v1/source-intake/instances/{instance_id}/test", headers=headers)).status_code == 200
    discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
    assert discover_resp.status_code == 200

    assets_resp = await client.get(
        "/api/v1/source-intake/assets",
        headers=headers,
        params={"page": 1, "page_size": 20},
    )
    assert assets_resp.status_code == 200
    customers_asset = next(
        item for item in assets_resp.json()["data"]["items"] if item["qualified_name"].endswith(".customers")
    )

    fields_resp = await client.get(
        f"/api/v1/source-intake/assets/{customers_asset['id']}/fields",
        headers=headers,
        params={"page": 1, "page_size": 20},
    )
    assert fields_resp.status_code == 200
    field_items = fields_resp.json()["data"]["items"]
    assert field_items
    user_id_field = next(item for item in field_items if item["field_name"] == "user_id")
    created_at_field = next(item for item in field_items if item["field_name"] == "created_at")
    assert user_id_field["candidates"]
    assert created_at_field["candidates"]

    field_detail_resp = await client.get(
        f"/api/v1/source-intake/fields/{user_id_field['id']}",
        headers=headers,
    )
    assert field_detail_resp.status_code == 200
    field_detail = field_detail_resp.json()["data"]
    assert field_detail["field_key"].endswith(":user_id")
    assert field_detail["profiles"]

    profiles_resp = await client.get(
        f"/api/v1/source-intake/fields/{user_id_field['id']}/profiles",
        headers=headers,
    )
    assert profiles_resp.status_code == 200
    profile_items = profiles_resp.json()["data"]
    assert profile_items

    candidates_resp = await client.get(
        f"/api/v1/source-intake/fields/{user_id_field['id']}/candidates",
        headers=headers,
    )
    assert candidates_resp.status_code == 200
    candidate_items = candidates_resp.json()["data"]
    assert candidate_items

    knowledge_create_resp = await client.post(
        "/api/v1/knowledge/documents",
        headers=headers,
        json={
            "doc_type": "FIELD_NOTE",
            "module": "KNOWLEDGE",
            "knowledge_level": "FIELD",
            "title": f"user_id 字段说明 {suffix}",
            "summary": "用户标识字段说明",
            "content": "该字段用于标识客户主键候选，当前为字段级知识对象。",
            "status": "PUBLISHED",
            "object_refs": [
                {
                    "object_type": "FIELD",
                    "object_id": user_id_field["id"],
                    "field_key": user_id_field["field_key"],
                }
            ],
            "fact_refs": [
                {
                    "fact_type": "SOURCE_FIELD",
                    "fact_id": user_id_field["id"],
                },
                {
                    "fact_type": "FIELD_PROFILE",
                    "fact_id": profile_items[0]["id"],
                },
                {
                    "fact_type": "SEMANTIC_CANDIDATE",
                    "fact_id": candidate_items[0]["id"],
                },
            ],
        },
    )
    assert knowledge_create_resp.status_code == 200

    knowledge_list_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"knowledge_level": "FIELD", "q": f"user_id 字段说明 {suffix}", "limit": 20, "offset": 0},
    )
    assert knowledge_list_resp.status_code == 200
    knowledge_items = knowledge_list_resp.json()["data"]["items"]
    assert knowledge_items
    knowledge_id = knowledge_items[0]["id"]
    assert knowledge_items[0]["knowledge_level"] == "FIELD"
    assert knowledge_items[0]["fact_ref_count"] >= 1
    assert knowledge_items[0]["has_fact_refs"] is True

    open_candidates_resp = await client.get(
        "/api/v1/source-intake/candidates",
        headers=headers,
        params={"status": "OPEN", "page": 1, "page_size": 50},
    )
    assert open_candidates_resp.status_code == 200
    open_candidates = open_candidates_resp.json()["data"]["items"]
    assert open_candidates

    promote_resp = await client.post(
        f"/api/v1/source-intake/candidates/{open_candidates[0]['id']}/promote",
        headers=headers,
    )
    assert promote_resp.status_code == 200
    assert promote_resp.json()["data"]["status"] == "PROMOTED"

    memory_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"module": "SOURCE_MEMORY", "limit": 20, "offset": 0},
    )
    assert memory_resp.status_code == 200
    memory_items = memory_resp.json()["data"]["items"]
    assert any(item["title"] == f"[Source Memory] {instance_name}" for item in memory_items)

    chat_resp = await client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={
            "messages": [
                {
                    "role": "user",
                    "content": "user_id 字段 类型 是什么",
                }
            ],
            "include_knowledge": True,
            "include_sources": True,
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()["data"]
    assert chat_data["citations"]
    assert any(item["type"] == "SOURCE_FIELD" and "user_id" in item["label"] for item in chat_data["citations"])
    assert chat_data["query_trace"]["trace_id"]
    assert "规划上下文" in chat_data["answer"]
    context_refs = chat_data["query_trace"]["plan"]["plan_payload"]["context_refs"]
    assert isinstance(context_refs["documents"], list)
    if context_refs["documents"]:
        assert {"id", "object_type", "reason", "evidence_mode", "priority"} <= set(context_refs["documents"][0].keys())
    assert any(
        item["id"] == user_id_field["id"]
        and item["object_type"] == "FIELD"
        and item["reason"] in {"matched_field", "knowledge_object_ref", "knowledge_fact_ref", "field_fact"}
        and "evidence_mode" in item
        and "priority" in item
        for item in context_refs["fields"]
    )
