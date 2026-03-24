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
            create table orders (
              id integer primary key,
              customer_id integer not null,
              amount real not null,
              created_at text not null
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
        conn.execute(
            """
            insert into orders (customer_id, amount, created_at)
            values
              (1, 108.5, '2026-03-18T12:00:00Z'),
              (2, 256.0, '2026-03-18T13:00:00Z')
            """
        )
        conn.commit()
    finally:
        conn.close()


def _mutate_sqlite_sample(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("alter table customers add column city text")
        conn.execute(
            """
            create table inventory (
              id integer primary key,
              sku text not null,
              stock integer not null
            )
            """
        )
        conn.execute("insert into inventory (sku, stock) values ('sku_001', 12)")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_source_intake_sqlite_instance_discover_watch_memory_and_telemetry(
    client: AsyncClient, tmp_path: Path
):
    suffix = _unique_suffix()
    instance_name = f"local_sqlite_instance_{suffix}"
    sqlite_path = tmp_path / f"source_intake_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_source_intake_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Source Intake {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])

    connectors_resp = await client.get("/api/v1/source-intake/connectors", headers=headers)
    assert connectors_resp.status_code == 200
    connectors = connectors_resp.json()["data"]["items"]
    assert any(item["connector_key"] == "sqlite" for item in connectors)
    assert any(item["connector_key"] == "mysql" for item in connectors)

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
    instance = create_resp.json()["data"]
    instance_id = instance["id"]

    knowledge_create_resp = await client.post(
        "/api/v1/knowledge/documents",
        headers=headers,
        json={
            "doc_type": "NOTE",
            "module": "KNOWLEDGE",
            "title": f"linked-doc-{suffix}",
            "content": "instance linked document",
            "status": "DRAFT",
            "related_objects": [
                {
                    "source_type": "SOURCE_INSTANCE",
                    "source_id": str(instance_id),
                    "label": instance_name,
                    "module": "SOURCE_INTAKE",
                }
            ],
        },
    )
    assert knowledge_create_resp.status_code == 200

    test_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/test", headers=headers)
    assert test_resp.status_code == 200
    assert test_resp.json()["data"]["status"] == "SUCCESS"
    brief_after_test_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"q": f"[Source Brief] {instance_name}", "limit": 20, "offset": 0},
    )
    assert brief_after_test_resp.status_code == 200
    brief_after_test_items = brief_after_test_resp.json()["data"]["items"]
    assert any(item["title"] == f"[Source Brief] {instance_name}" for item in brief_after_test_items)

    discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
    assert discover_resp.status_code == 200
    discover_data = discover_resp.json()["data"]
    assert discover_data["brief"]["metrics"]["asset_count"] >= 3
    assert len(discover_data["changes"]) >= 1
    assert len(discover_data["candidates"]) >= 1
    brief_after_discover_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"q": f"[Source Brief] {instance_name}", "limit": 20, "offset": 0},
    )
    assert brief_after_discover_resp.status_code == 200
    brief_after_discover_items = brief_after_discover_resp.json()["data"]["items"]
    assert any(item["title"] == f"[Source Brief] {instance_name}" and item["status"] == "PUBLISHED" for item in brief_after_discover_items)

    assets_resp = await client.get(
        "/api/v1/source-intake/assets",
        headers=headers,
        params={"page": 1, "page_size": 20},
    )
    assert assets_resp.status_code == 200
    assets = assets_resp.json()["data"]["items"]
    assert any(item["qualified_name"].endswith(".customers") for item in assets)
    assert any(item["qualified_name"].endswith(".orders") for item in assets)

    _mutate_sqlite_sample(sqlite_path)

    watch_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/watch/run", headers=headers)
    assert watch_resp.status_code == 200
    watch_data = watch_resp.json()["data"]
    assert watch_data["brief"]["metrics"]["change_count"] >= 1

    changes_resp = await client.get(
        "/api/v1/source-intake/change-events",
        headers=headers,
        params={"status": "OPEN", "page": 1, "page_size": 50},
    )
    assert changes_resp.status_code == 200
    change_items = changes_resp.json()["data"]["items"]
    assert any(item["event_type"] in {"ASSET_DISCOVERED", "ASSET_CHANGED"} for item in change_items)

    candidates_resp = await client.get(
        "/api/v1/source-intake/candidates",
        headers=headers,
        params={"status": "OPEN", "page": 1, "page_size": 50},
    )
    assert candidates_resp.status_code == 200
    candidate_items = candidates_resp.json()["data"]["items"]
    assert candidate_items

    share_resp = await client.post(
        f"/api/v1/source-intake/candidates/{candidate_items[0]['id']}/share",
        headers=headers,
    )
    assert share_resp.status_code == 200
    assert share_resp.json()["data"]["status"] == "SHARED"

    memory_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0},
    )
    assert memory_resp.status_code == 200
    memory_items = memory_resp.json()["data"]["items"]
    assert any(item["title"] == f"[Source Memory] {instance_name}" for item in memory_items)
    assert any("shared-memory" in item["tags"] for item in memory_items)

    overview_resp = await client.get("/api/v1/source-intake/telemetry/overview", headers=headers)
    assert overview_resp.status_code == 200
    overview_data = overview_resp.json()["data"]
    assert overview_data["summary"]["instance_count"] >= 1
    assert overview_data["source_load"]
    assert overview_data["nodes"]

    source_series_resp = await client.get(
        "/api/v1/source-intake/telemetry/source-series",
        headers=headers,
        params={"window": "24h"},
    )
    assert source_series_resp.status_code == 200
    assert source_series_resp.json()["data"]["series"]

    node_series_resp = await client.get(
        "/api/v1/source-intake/telemetry/node-series",
        headers=headers,
        params={"window": "24h"},
    )
    assert node_series_resp.status_code == 200
    assert node_series_resp.json()["data"]["series"]

    delete_resp = await client.delete(f"/api/v1/source-intake/instances/{instance_id}", headers=headers)
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    deleted_instance_resp = await client.get(f"/api/v1/source-intake/instances/{instance_id}", headers=headers)
    assert deleted_instance_resp.status_code == 404

    memory_after_delete_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0},
    )
    assert memory_after_delete_resp.status_code == 200
    memory_after_delete = memory_after_delete_resp.json()["data"]["items"]
    assert all(item["title"] != f"[Source Memory] {instance_name}" for item in memory_after_delete)

    knowledge_after_delete_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"q": f"linked-doc-{suffix}", "limit": 20, "offset": 0},
    )
    assert knowledge_after_delete_resp.status_code == 200
    assert knowledge_after_delete_resp.json()["data"]["total"] == 0
    source_brief_after_delete_resp = await client.get(
        "/api/v1/knowledge/documents",
        headers=headers,
        params={"q": f"[Source Brief] {instance_name}", "limit": 20, "offset": 0},
    )
    assert source_brief_after_delete_resp.status_code == 200
    assert source_brief_after_delete_resp.json()["data"]["total"] == 0

    source_profiles_resp = await client.get(
        "/api/v1/fabric/source-profiles",
        headers=headers,
        params={"q": instance_name, "limit": 20, "offset": 0},
    )
    assert source_profiles_resp.status_code == 200
    assert source_profiles_resp.json()["data"]["total"] == 0
