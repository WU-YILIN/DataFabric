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
            create table orders (
              id integer primary key,
              user_id text not null,
              created_at text not null,
              amount real
            )
            """
        )
        conn.execute(
            """
            insert into orders (user_id, created_at, amount)
            values
              ('u_001', '2026-03-18T10:00:00Z', 128.0),
              ('u_002', '2026-03-19T10:00:00Z', 256.0)
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_audit_logs_support_trace_filter_and_return_trace_id(client: AsyncClient, tmp_path: Path):
    suffix = _unique_suffix()
    sqlite_path = tmp_path / f"audit_trace_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"audit_trace_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Audit Trace {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])

    create_resp = await client.post(
        "/api/v1/source-intake/instances",
        headers=headers,
        json={
            "instance_name": f"audit_trace_sqlite_{suffix}",
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
    assert (await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)).status_code == 200

    submit_resp = await client.post(
        "/api/v1/fabric/planner/submit",
        headers=headers,
        json={"question": "最近30天订单金额趋势应该如何规划？", "latency_target_ms": 600},
    )
    assert submit_resp.status_code == 200
    trace_id = submit_resp.json()["data"]["trace_id"]
    assert trace_id

    logs_resp = await client.get(
        "/api/v1/audit/logs",
        headers=headers,
        params={"trace_id": trace_id, "limit": 50, "offset": 0, "include_meta": True},
    )
    assert logs_resp.status_code == 200
    data = logs_resp.json()["data"]
    assert data["items"]
    assert any(item["trace_id"] == trace_id for item in data["items"])
    assert trace_id in data["facets"]["trace_ids"]

    detail_resp = await client.get(f"/api/v1/audit/logs/{data['items'][0]['id']}", headers=headers)
    assert detail_resp.status_code == 200
    detail = detail_resp.json()["data"]
    assert "trace_id" in detail
