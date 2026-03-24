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
              updated_at text not null,
              status text,
              amount real
            )
            """
        )
        conn.execute(
            """
            insert into orders (user_id, created_at, updated_at, status, amount)
            values
              ('u_001', '2026-03-18T10:00:00Z', '2026-03-18T10:10:00Z', 'PAID', 129.8),
              ('u_002', '2026-03-19T11:00:00Z', '2026-03-19T11:05:00Z', 'PAID', 88.0)
            """
        )
        conn.execute(
            """
            create table payments (
              id integer primary key,
              order_id integer not null,
              paid_at text not null,
              payment_status text
            )
            """
        )
        conn.execute(
            """
            insert into payments (order_id, paid_at, payment_status)
            values
              (1, '2026-03-18T10:11:00Z', 'SUCCESS'),
              (2, '2026-03-19T11:08:00Z', 'SUCCESS')
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_fabric_architecture_endpoints(client: AsyncClient, tmp_path: Path):
    suffix = _unique_suffix()
    email = f"it_fabric_{suffix}@demo.local"
    password = "demo123456"
    name = f"Fabric User {suffix}"
    sqlite_path = tmp_path / f"fabric_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": name},
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])

    create_resp = await client.post(
        "/api/v1/source-onboarding/sources",
        headers=headers,
        json={
            "source_name": "fabric_sqlite_orders",
            "source_type": "SQLITE",
            "config": {
                "file_path": str(sqlite_path),
                "namespace": "fabric-test",
                "memory_scope": "PRIVATE",
            },
        },
    )
    assert create_resp.status_code == 200
    source_id = create_resp.json()["data"]["id"]

    test_resp = await client.post(f"/api/v1/source-onboarding/sources/{source_id}/test", headers=headers)
    assert test_resp.status_code == 200

    scan_resp = await client.post(f"/api/v1/source-onboarding/sources/{source_id}/scan", headers=headers)
    assert scan_resp.status_code == 200
    assert len(scan_resp.json()["data"]["discovery"]["objects"]) == 2

    profiles_resp = await client.get("/api/v1/fabric/source-profiles", headers=headers)
    assert profiles_resp.status_code == 200
    profiles_data = profiles_resp.json()["data"]
    assert profiles_data["total"] >= 1
    assert any(item["source_name"] == "fabric_sqlite_orders" for item in profiles_data["items"])

    semantics_resp = await client.get("/api/v1/fabric/update-semantics", headers=headers)
    assert semantics_resp.status_code == 200
    semantics_data = semantics_resp.json()["data"]
    assert semantics_data["total"] >= 1
    assert semantics_data["items"][0]["update_mode"] in {
        "UPSERT",
        "APPEND",
        "FULL_SNAPSHOT",
        "PERIODIC_FULL",
        "CDC_LIKE",
    }

    domains_resp = await client.get("/api/v1/fabric/semantic-domains", headers=headers)
    assert domains_resp.status_code == 200
    domains_data = domains_resp.json()["data"]
    assert domains_data["summary"]["domain_count"] >= 1
    assert any(
        item["label"] in {"订单与交易", "支付与结算", "用户与客户"} for item in domains_data["items"]
    )

    planner_resp = await client.post(
        "/api/v1/fabric/planner/plan",
        headers=headers,
        json={"question": "订单支付月报应该优先走什么路径？", "latency_target_ms": 500},
    )
    assert planner_resp.status_code == 200
    planner_data = planner_resp.json()["data"]
    assert planner_data["strategy"] in {
        "MEMORY_ONLY",
        "CONTRACT_FIRST",
        "HOT_MATERIALIZATION",
        "ON_DEMAND_COMPUTE",
    }
    assert planner_data["domain"]["label"] in {"订单与交易", "支付与结算", "通用基础"}
    assert planner_data["steps"]

    materializations_resp = await client.get("/api/v1/fabric/materializations", headers=headers)
    assert materializations_resp.status_code == 200
    materializations_data = materializations_resp.json()["data"]
    assert materializations_data["total"] >= 1
    assert materializations_data["items"][0]["artifact_name"]

    telemetry_resp = await client.get("/api/v1/fabric/telemetry/overview", headers=headers)
    assert telemetry_resp.status_code == 200
    telemetry_data = telemetry_resp.json()["data"]
    assert telemetry_data["summary"]["source_count"] >= 1
    assert telemetry_data["cluster_nodes"]
