import subprocess
import time
from pathlib import Path

import pytest
import pymysql
from httpx import AsyncClient


MYSQL_CONTAINER = "datafabric_mysql_mock"
MYSQL_PORT = "3307"


def _context_headers(access_token: str, context: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *args],
        check=check,
        capture_output=True,
        text=True,
    )


def _ensure_mysql_mock(fixture_path: Path) -> None:
    _docker("rm", "-f", MYSQL_CONTAINER, check=False)
    mount_spec = f"{fixture_path.resolve().as_posix()}:/docker-entrypoint-initdb.d/init.sql:ro"
    _docker(
        "run",
        "-d",
        "--name",
        MYSQL_CONTAINER,
        "-e",
        "MYSQL_ROOT_PASSWORD=root",
        "-e",
        "MYSQL_DATABASE=fabric_mock",
        "-e",
        "MYSQL_USER=fabric",
        "-e",
        "MYSQL_PASSWORD=fabric",
        "-p",
        f"{MYSQL_PORT}:3306",
        "-v",
        mount_spec,
        "mysql:5.7",
    )
    deadline = time.time() + 90
    while time.time() < deadline:
        container_ready = _docker(
            "exec",
            MYSQL_CONTAINER,
            "mysql",
            "-ufabric",
            "-pfabric",
            "-D",
            "fabric_mock",
            "-e",
            "select count(*) from orders_snapshot;",
            check=False,
        )
        if container_ready.returncode == 0:
            try:
                conn = pymysql.connect(
                    host="127.0.0.1",
                    port=int(MYSQL_PORT),
                    user="fabric",
                    password="fabric",
                    database="fabric_mock",
                    connect_timeout=3,
                )
                try:
                    with conn.cursor() as cursor:
                        cursor.execute("select count(*) from orders_snapshot")
                        cursor.fetchone()
                    return
                finally:
                    conn.close()
            except Exception:
                pass
        time.sleep(2)
    raise RuntimeError("MySQL mock container did not become ready in time")


def _cleanup_mysql_mock() -> None:
    _docker("rm", "-f", MYSQL_CONTAINER, check=False)


@pytest.mark.asyncio
async def test_mysql_mock_source_onboarding_and_fabric_endpoints(client: AsyncClient):
    fixture_path = Path(__file__).resolve().parents[1] / "fixtures" / "mysql_mock" / "init.sql"
    _ensure_mysql_mock(fixture_path)
    try:
        suffix = str(int(time.time() * 1000))
        register_resp = await client.post(
            "/api/v1/auth/register",
            json={
                "email": f"it_mysql_{suffix}@demo.local",
                "password": "demo123456",
                "name": f"MySQL Fabric {suffix}",
            },
        )
        assert register_resp.status_code == 200
        register_data = register_resp.json()["data"]
        headers = _context_headers(register_data["access_token"], register_data["default_context"])

        create_resp = await client.post(
            "/api/v1/source-onboarding/sources",
            headers=headers,
            json={
                "source_name": "mysql_mock_orders",
                "source_type": "MYSQL",
                "config": {
                    "host": "127.0.0.1",
                    "port": int(MYSQL_PORT),
                    "database": "fabric_mock",
                    "schema": "",
                    "username": "fabric",
                    "password": "fabric",
                    "memory_scope": "TENANT",
                },
            },
        )
        assert create_resp.status_code == 200
        source_id = create_resp.json()["data"]["id"]

        test_resp = await client.post(f"/api/v1/source-onboarding/sources/{source_id}/test", headers=headers)
        assert test_resp.status_code == 200

        scan_resp = await client.post(f"/api/v1/source-onboarding/sources/{source_id}/scan", headers=headers)
        assert scan_resp.status_code == 200
        discovery = scan_resp.json()["data"]["discovery"]
        assert len(discovery["objects"]) == 2
        assert {obj["table_name"] for obj in discovery["objects"]} == {"orders_snapshot", "payment_snapshot"}

        memory_resp = await client.get(
            "/api/v1/knowledge/documents",
            headers=headers,
            params={"module": "SOURCE_MEMORY", "include_shared": True, "limit": 20, "offset": 0},
        )
        assert memory_resp.status_code == 200
        memory_items = memory_resp.json()["data"]["items"]
        assert any("mysql_mock_orders" in item["title"] for item in memory_items)

        planner_resp = await client.post(
            "/api/v1/fabric/planner/plan",
            headers=headers,
            json={"question": "订单支付主题域应该如何规划？", "latency_target_ms": 500},
        )
        assert planner_resp.status_code == 200
        assert planner_resp.json()["data"]["matched_sources"]

        telemetry_resp = await client.get("/api/v1/fabric/telemetry/overview", headers=headers)
        assert telemetry_resp.status_code == 200
        telemetry_data = telemetry_resp.json()["data"]
        assert telemetry_data["summary"]["source_count"] >= 1
        assert telemetry_data["source_load"]
    finally:
        _cleanup_mysql_mock()
