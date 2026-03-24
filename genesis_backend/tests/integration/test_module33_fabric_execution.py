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
              region text,
              amount real
            )
            """
        )
        conn.execute(
            """
            insert into orders (user_id, created_at, updated_at, region, amount)
            values
              ('u_001', '2026-03-18T10:00:00Z', '2026-03-18T10:10:00Z', 'east', 129.8),
              ('u_002', '2026-03-19T11:00:00Z', '2026-03-19T11:05:00Z', 'west', 88.0)
            """
        )
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_fabric_execution_trace_and_chat_query_trace(client: AsyncClient, tmp_path: Path):
    suffix = _unique_suffix()
    email = f"it_execution_{suffix}@demo.local"
    password = "demo123456"
    sqlite_path = tmp_path / f"fabric_exec_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "name": f"Execution User {suffix}"},
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])

    create_resp = await client.post(
        "/api/v1/source-onboarding/sources",
        headers=headers,
        json={
            "source_name": "execution_sqlite_orders",
            "source_type": "SQLITE",
            "config": {
                "file_path": str(sqlite_path),
                "namespace": "exec-test",
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

    preview_resp = await client.post(
        "/api/v1/fabric/planner/plan",
        headers=headers,
        json={
            "question": "请规划一条围绕订单主题域的复杂多表 join 全量重算任务，并说明是否需要异步执行。",
            "latency_target_ms": 1500,
        },
    )
    assert preview_resp.status_code == 200
    preview_data = preview_resp.json()["data"]
    assert "context_refs" in preview_data
    assert isinstance(preview_data["context_refs"]["sources"], list)
    if preview_data["context_refs"]["sources"]:
        source_ref = preview_data["context_refs"]["sources"][0]
        assert {"id", "object_type", "reason", "evidence_mode", "priority"} <= set(source_ref.keys())

    submit_resp = await client.post(
        "/api/v1/fabric/planner/submit",
        headers=headers,
        json={
            "question": "请规划一条围绕订单主题域的复杂多表 join 全量重算任务，并说明是否需要异步执行。",
            "latency_target_ms": 1500,
        },
    )
    assert submit_resp.status_code == 200
    submit_data = submit_resp.json()["data"]
    assert submit_data["trace_id"].startswith("trace_")
    assert submit_data["intent"]["intent_type"] in {"HOT_ANALYTICS", "AD_HOC_ANALYTICS"}
    assert submit_data["run"]["execution_mode"] == "ASYNC"
    assert submit_data["run"]["status"] == "WAITING_CONFIRMATION"

    runs_resp = await client.get("/api/v1/fabric/planner/runs", headers=headers)
    assert runs_resp.status_code == 200
    runs_data = runs_resp.json()["data"]
    assert runs_data["total"] >= 1
    run_id = submit_data["run"]["id"]

    detail_resp = await client.get(f"/api/v1/fabric/planner/runs/{run_id}", headers=headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["run"]["id"] == run_id
    assert len(detail_data["stages"]) == 4
    assert len(detail_data["prepared_sql"]) >= 3
    assert len(detail_data["artifacts"]) >= 1

    artifacts_resp = await client.get("/api/v1/fabric/materialization-artifacts", headers=headers)
    assert artifacts_resp.status_code == 200
    artifacts_data = artifacts_resp.json()["data"]
    assert artifacts_data["total"] >= 1

    chat_resp = await client.post(
        "/api/v1/assistant/chat",
        headers=headers,
        json={
            "messages": [
                {"role": "user", "content": "请规划一条订单主题域的复杂多表 join 重算任务"}
            ],
            "include_knowledge": True,
            "include_sources": True,
        },
    )
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()["data"]
    assert "query_trace" in chat_data
    assert chat_data["query_trace"]["trace_id"].startswith("trace_")
    assert "规划上下文" in chat_data["answer"]
    assert chat_data["query_trace"]["plan"]["selected_path"] in chat_data["answer"]
    assert "context_refs" in chat_data["query_trace"]["plan"]["plan_payload"]
    source_refs = chat_data["query_trace"]["plan"]["plan_payload"]["context_refs"]["sources"]
    assert isinstance(source_refs, list)
    if source_refs:
        assert {"id", "object_type", "reason", "evidence_mode", "priority"} <= set(source_refs[0].keys())
