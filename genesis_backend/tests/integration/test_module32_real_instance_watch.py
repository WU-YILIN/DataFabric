import sqlite3
import time
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.domain.source_intake_service import SourceIntakeService
from src.infrastructure.database.models.source_candidate import SourceCandidate
from src.infrastructure.database.models.source_change_event import SourceChangeEvent
from src.infrastructure.database.models.source_instance import SourceInstance
from src.infrastructure.database.session import async_session_factory


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
              created_at text not null
            )
            """
        )
        conn.execute("insert into customers (user_id, created_at) values ('u_001', '2026-03-22T10:00:00Z')")
        conn.commit()
    finally:
        conn.close()


def _mutate_sqlite_sample(path: Path) -> None:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            """
            create table orders (
              id integer primary key,
              customer_id integer not null,
              amount real not null
            )
            """
        )
        conn.execute("insert into orders (customer_id, amount) values (1, 108.5)")
        conn.commit()
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_real_instance_watch_scheduler_runs_due_instances(client: AsyncClient, tmp_path: Path):
    suffix = _unique_suffix()
    sqlite_path = tmp_path / f"watch_instance_{suffix}.db"
    _build_sqlite_sample(sqlite_path)

    register_resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_real_watch_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Real Watch {suffix}",
        },
    )
    assert register_resp.status_code == 200
    register_data = register_resp.json()["data"]
    headers = _context_headers(register_data["access_token"], register_data["default_context"])
    project_id = register_data["default_context"]["project_id"]

    create_resp = await client.post(
        "/api/v1/source-intake/instances",
        headers=headers,
        json={
            "instance_name": "real_watch_sqlite",
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

    discover_resp = await client.post(f"/api/v1/source-intake/instances/{instance_id}/discover", headers=headers)
    assert discover_resp.status_code == 200

    update_resp = await client.patch(
        f"/api/v1/source-intake/instances/{instance_id}",
        headers=headers,
        json={"watch_enabled": True, "watch_interval_seconds": 60},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["watch_enabled"] is True

    _mutate_sqlite_sample(sqlite_path)

    async with async_session_factory() as session:
        result = await session.execute(select(SourceInstance).where(SourceInstance.id == instance_id))
        instance = result.scalar_one()
        instance.watch_next_run_at = None
        await session.commit()

    async with async_session_factory() as session:
        service = SourceIntakeService(session)
        summary = await service.run_due_watches(limit=10)
        await session.commit()

    assert summary["processed"] >= 1
    assert summary["success"] >= 1

    instance_resp = await client.get(f"/api/v1/source-intake/instances/{instance_id}", headers=headers)
    assert instance_resp.status_code == 200
    instance = instance_resp.json()["data"]
    assert instance["last_watch_status"] == "SUCCESS"
    assert instance["watch_enabled"] is True
    assert instance["watch_last_started_at"]
    assert instance["watch_last_finished_at"]
    assert instance["watch_next_run_at"]
    assert instance["watch_failure_count"] == 0

    async with async_session_factory() as session:
        change_result = await session.execute(select(SourceChangeEvent).where(SourceChangeEvent.project_id == project_id))
        candidate_result = await session.execute(select(SourceCandidate).where(SourceCandidate.project_id == project_id))
        change_items = list(change_result.scalars().all())
        candidate_items = list(candidate_result.scalars().all())

    assert any(item.event_type in {"ASSET_DISCOVERED", "ASSET_CHANGED"} for item in change_items)
    assert any(item.candidate_type in {"NEW_ASSET", "ASSET_CHANGE"} for item in candidate_items)
