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
            "email": f"it_mod23_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module23 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module23_custom_reports_dashboard_builder_full_flow(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    suffix = _unique_suffix()

    overview_resp = await client.get("/api/v1/reports/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    assert "summary" in overview_resp.json()["data"]

    templates_resp = await client.get("/api/v1/reports/templates", headers=admin_headers)
    assert templates_resp.status_code == 200
    templates_data = templates_resp.json()["data"]
    assert templates_data["total"] >= 1
    assert any(item["key"] == "OPS_MONITORING" for item in templates_data["items"])

    create_resp = await client.post(
        "/api/v1/reports/items",
        json={
            "template_key": "OPS_MONITORING",
            "name": f"ops dashboard {suffix}",
            "status": "DRAFT",
            "tags": ["ops", "module23"],
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 200
    item = create_resp.json()["data"]
    item_id = item["id"]
    assert item["kind"] == "DASHBOARD"
    assert item["status"] == "DRAFT"

    list_resp = await client.get(
        "/api/v1/reports/items",
        params={"kind": "DASHBOARD", "q": "module23"},
        headers=admin_headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(row["id"] == item_id for row in list_data["items"])

    detail_resp = await client.get(
        f"/api/v1/reports/items/{item_id}",
        params={"include_data": True, "time_window_days": 30},
        headers=admin_headers,
    )
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["item"]["id"] == item_id
    assert len(detail_data["versions"]) >= 1
    assert detail_data["data_payload"] is not None
    assert "widgets" in detail_data["data_payload"]

    update_resp = await client.patch(
        f"/api/v1/reports/items/{item_id}",
        json={
            "name": f"ops dashboard updated {suffix}",
            "scenario": "OPERATIONS_RUNTIME",
            "tags": ["ops", "runtime", "module23"],
            "change_note": "update metadata for module23 test",
        },
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["data"]["name"].endswith(suffix)

    publish_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={"action": "PUBLISH", "note": "publish for project members"},
        headers=admin_headers,
    )
    assert publish_resp.status_code == 200
    assert publish_resp.json()["data"]["item"]["status"] == "PUBLISHED"

    refresh_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={
            "action": "REFRESH_CACHE",
            "time_window_days": 14,
            "view_filter_payload": {"domain": "core"},
        },
        headers=admin_headers,
    )
    assert refresh_resp.status_code == 200
    assert "data_payload" in refresh_resp.json()["data"]

    save_view_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={
            "action": "SAVE_VIEW",
            "view_name": f"my view {suffix}",
            "view_filter_payload": {"domain": "core"},
            "is_default_view": True,
        },
        headers=admin_headers,
    )
    assert save_view_resp.status_code == 200
    assert "saved_view" in save_view_resp.json()["data"]

    export_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={
            "action": "EXPORT",
            "export_format": "LINK",
            "view_name": f"share view {suffix}",
            "link_expires_hours": 24,
        },
        headers=admin_headers,
    )
    assert export_resp.status_code == 200
    export_data = export_resp.json()["data"]["export"]
    assert export_data["format"] == "LINK"
    assert export_data["url"].startswith("/reports/shared/")

    clone_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={"action": "CLONE", "clone_name": f"ops clone {suffix}"},
        headers=admin_headers,
    )
    assert clone_resp.status_code == 200
    clone_data = clone_resp.json()["data"]["cloned_item"]
    assert clone_data["status"] == "DRAFT"

    share_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={
            "action": "SHARE",
            "share_payload": {
                "visibility": "ROLE_BASED",
                "viewer_roles": ["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"],
                "editor_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"],
                "clone_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"],
            },
        },
        headers=admin_headers,
    )
    assert share_resp.status_code == 200
    assert share_resp.json()["data"]["item"]["permission_payload"]["visibility"] == "ROLE_BASED"

    archive_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={"action": "ARCHIVE"},
        headers=admin_headers,
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["data"]["item"]["status"] == "ARCHIVED"

    unarchive_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={"action": "UNARCHIVE"},
        headers=admin_headers,
    )
    assert unarchive_resp.status_code == 200
    assert unarchive_resp.json()["data"]["item"]["status"] == "DRAFT"

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {row["action"] for row in audit_resp.json()["data"]}
    assert "REPORT_DASHBOARD_CREATE" in actions
    assert "REPORT_DASHBOARD_UPDATE" in actions
    assert "REPORT_DASHBOARD_PUBLISH" in actions
    assert "REPORT_DASHBOARD_EXPORT" in actions


@pytest.mark.asyncio
async def test_module23_custom_reports_dashboard_builder_permission_guard(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/reports/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/reports/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_create_resp = await client.post(
        "/api/v1/reports/items",
        json={
            "template_key": "OPS_MONITORING",
            "name": f"forbidden create {_unique_suffix()}",
        },
        headers=viewer_headers,
    )
    assert viewer_create_resp.status_code == 403

    create_target_resp = await client.post(
        "/api/v1/reports/items",
        json={
            "template_key": "QUALITY_MONITORING",
            "name": f"permission target {_unique_suffix()}",
        },
        headers=admin_headers,
    )
    assert create_target_resp.status_code == 200
    item_id = create_target_resp.json()["data"]["id"]

    viewer_publish_resp = await client.post(
        f"/api/v1/reports/items/{item_id}/actions",
        json={"action": "PUBLISH"},
        headers=viewer_headers,
    )
    assert viewer_publish_resp.status_code == 403
