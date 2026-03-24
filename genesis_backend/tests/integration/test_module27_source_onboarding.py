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
async def test_source_onboarding_create_test_and_scan_sqlite(client: AsyncClient, tmp_path: Path):
    suffix = _unique_suffix()
    email = f"it_source_{suffix}@demo.local"
    password = "demo123456"
    name = f"Source User {suffix}"
    sqlite_path = tmp_path / f"source_onboarding_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

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

    create_resp = await client.post(
        "/api/v1/source-onboarding/sources",
        headers=headers,
        json={
            "source_name": "local_sqlite_source",
            "source_type": "SQLITE",
            "config": {
                "file_path": str(sqlite_path),
                "namespace": "integration-test",
            },
        },
    )
    assert create_resp.status_code == 200
    source = create_resp.json()["data"]
    source_id = source["id"]

    test_resp = await client.post(f"/api/v1/source-onboarding/sources/{source_id}/test", headers=headers)
    assert test_resp.status_code == 200
    assert test_resp.json()["data"]["status"] == "SUCCESS"

    scan_resp = await client.post(f"/api/v1/source-onboarding/sources/{source_id}/scan", headers=headers)
    assert scan_resp.status_code == 200
    discovery = scan_resp.json()["data"]["discovery"]
    assert discovery["source_type"] == "SQLITE"
    assert len(discovery["objects"]) == 1
    assert discovery["objects"][0]["table_name"] == "customers"
    assert discovery["objects"][0]["inference_candidates"]

    list_resp = await client.get("/api/v1/source-onboarding/sources", headers=headers)
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]["items"]
    assert any(item["id"] == source_id and item["status"] == "OBSERVED" for item in items)

    observation_resp = await client.get("/api/v1/p0/source-profiles", headers=headers, params={"limit": 20})
    assert observation_resp.status_code == 200
    observation_items = observation_resp.json()["data"]["items"]
    assert any(item["event_name"] == "main.customers" for item in observation_items)

    inference_resp = await client.get("/api/v1/p0/inference-candidates", headers=headers, params={"limit": 20})
    assert inference_resp.status_code == 200
    inference_items = inference_resp.json()["data"]["items"]
    assert any(item["proposed_by"] == "source_onboarding" for item in inference_items)
