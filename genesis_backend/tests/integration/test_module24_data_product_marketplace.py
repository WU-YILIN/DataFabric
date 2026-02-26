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
            "email": f"it_mod24_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module24 {tag} {suffix}",
        },
    )
    assert register_resp.status_code == 200
    data = register_resp.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"])


@pytest.mark.asyncio
async def test_module24_data_product_marketplace_full_flow(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    suffix = _unique_suffix()

    overview_resp = await client.get("/api/v1/marketplace/overview", headers=admin_headers)
    assert overview_resp.status_code == 200
    assert "summary" in overview_resp.json()["data"]

    create_resp = await client.post(
        "/api/v1/marketplace/products",
        json={
            "name": f"orders mart {suffix}",
            "description": "Shared order mart for analytics",
            "domain": "commerce",
            "category": "analytics",
            "status": "DRAFT",
            "visibility": "PROJECT",
            "schema_payload": {"columns": ["order_id", "user_id", "amount"]},
            "tags": ["mart", "orders", "module24"],
            "sla_payload": {"freshness_minutes": 30, "availability_sla": 0.995},
            "access_policy_payload": {
                "viewer_roles": ["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"],
                "editor_roles": ["EDITOR", "APPROVER", "ADMIN", "OWNER"],
            },
        },
        headers=admin_headers,
    )
    assert create_resp.status_code == 200
    product = create_resp.json()["data"]
    product_id = product["id"]
    assert product["status"] == "DRAFT"
    assert product["owner"] == "admin@demo.local"

    list_resp = await client.get(
        "/api/v1/marketplace/products",
        params={"q": "module24", "status": "DRAFT"},
        headers=admin_headers,
    )
    assert list_resp.status_code == 200
    list_data = list_resp.json()["data"]
    assert list_data["total"] >= 1
    assert any(item["id"] == product_id for item in list_data["items"])

    detail_resp = await client.get(f"/api/v1/marketplace/products/{product_id}", headers=admin_headers)
    assert detail_resp.status_code == 200
    detail_data = detail_resp.json()["data"]
    assert detail_data["product"]["id"] == product_id
    assert len(detail_data["versions"]) >= 1

    update_resp = await client.patch(
        f"/api/v1/marketplace/products/{product_id}",
        json={
            "description": "Updated product description",
            "category": "bi",
            "tags": ["mart", "orders", "updated", "module24"],
            "change_note": "metadata update for module24",
        },
        headers=admin_headers,
    )
    assert update_resp.status_code == 200
    assert "updated" in update_resp.json()["data"]["tags"]

    publish_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "PUBLISH", "note": "publish for subscription"},
        headers=admin_headers,
    )
    assert publish_resp.status_code == 200
    assert publish_resp.json()["data"]["product"]["status"] == "PUBLISHED"

    request_sub_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={
            "action": "REQUEST_SUBSCRIPTION",
            "request_reason": "Need this product for growth dashboard",
            "usage_quota_payload": {"daily_calls": 2000},
        },
        headers=admin_headers,
    )
    assert request_sub_resp.status_code == 200
    sub_data = request_sub_resp.json()["data"]["subscription"]
    sub_id = sub_data["id"]
    assert sub_data["status"] == "PENDING"

    approve_sub_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={
            "action": "APPROVE_SUBSCRIPTION",
            "subscription_id": sub_id,
            "expires_hours": 96,
            "usage_quota_payload": {"daily_calls": 5000},
            "note": "approved for BI team",
        },
        headers=admin_headers,
    )
    assert approve_sub_resp.status_code == 200
    approved_sub = approve_sub_resp.json()["data"]["subscription"]
    assert approved_sub["status"] == "APPROVED"
    assert approved_sub["access_token"] is not None

    rotate_token_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "ROTATE_TOKEN", "subscription_id": sub_id, "expires_hours": 48},
        headers=admin_headers,
    )
    assert rotate_token_resp.status_code == 200
    rotated_sub = rotate_token_resp.json()["data"]["subscription"]
    assert rotated_sub["status"] == "APPROVED"
    assert rotated_sub["access_token"] is not None

    revoke_sub_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "REVOKE_SUBSCRIPTION", "subscription_id": sub_id, "note": "security review"},
        headers=admin_headers,
    )
    assert revoke_sub_resp.status_code == 200
    assert revoke_sub_resp.json()["data"]["subscription"]["status"] == "REVOKED"

    archive_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "ARCHIVE"},
        headers=admin_headers,
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["data"]["product"]["status"] == "ARCHIVED"

    unarchive_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "UNARCHIVE"},
        headers=admin_headers,
    )
    assert unarchive_resp.status_code == 200
    assert unarchive_resp.json()["data"]["product"]["status"] == "DRAFT"

    audit_resp = await client.get("/api/v1/audit/logs", headers=admin_headers)
    assert audit_resp.status_code == 200
    actions = {item["action"] for item in audit_resp.json()["data"]}
    assert "DATA_PRODUCT_CREATE" in actions
    assert "DATA_PRODUCT_UPDATE" in actions
    assert "DATA_PRODUCT_PUBLISH" in actions
    assert "DATA_PRODUCT_SUB_APPROVE" in actions
    assert "DATA_PRODUCT_SUB_REVOKE" in actions


@pytest.mark.asyncio
async def test_module24_data_product_marketplace_permission_guard(client: AsyncClient):
    admin_headers, _ = await _login_admin(client)
    viewer_headers = await _register_viewer(client, "viewer")

    api_key_resp = await client.get(
        "/api/v1/marketplace/overview",
        headers={"X-API-KEY": "demo-key-001"},
    )
    assert api_key_resp.status_code == 403

    viewer_overview_resp = await client.get("/api/v1/marketplace/overview", headers=viewer_headers)
    assert viewer_overview_resp.status_code == 200

    viewer_create_resp = await client.post(
        "/api/v1/marketplace/products",
        json={"name": f"forbidden {_unique_suffix()}"},
        headers=viewer_headers,
    )
    assert viewer_create_resp.status_code == 403

    create_target_resp = await client.post(
        "/api/v1/marketplace/products",
        json={"name": f"target {_unique_suffix()}"},
        headers=admin_headers,
    )
    assert create_target_resp.status_code == 200
    product_id = create_target_resp.json()["data"]["id"]

    publish_target_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "PUBLISH"},
        headers=admin_headers,
    )
    assert publish_target_resp.status_code == 200

    req_by_viewer_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "REQUEST_SUBSCRIPTION", "request_reason": "viewer request"},
        headers=viewer_headers,
    )
    assert req_by_viewer_resp.status_code == 200
    sub_id = req_by_viewer_resp.json()["data"]["subscription"]["id"]

    approve_by_viewer_resp = await client.post(
        f"/api/v1/marketplace/products/{product_id}/actions",
        json={"action": "APPROVE_SUBSCRIPTION", "subscription_id": sub_id},
        headers=viewer_headers,
    )
    assert approve_by_viewer_resp.status_code == 403
