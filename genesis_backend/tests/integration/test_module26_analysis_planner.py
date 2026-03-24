import time

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from src.infrastructure.database.models.analysis_plan import AnalysisPlan
from src.infrastructure.database.models.collaboration_task import CollaborationTask
from src.infrastructure.database.models.collaboration_workflow import CollaborationWorkflow
from src.infrastructure.database.models.user import User, UserProjectRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import async_session_factory


def _unique_suffix() -> str:
    return str(time.time_ns())


def _context_headers(access_token: str, context: dict) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-TENANT-ID": str(context["tenant_id"]),
        "X-PROJECT-ID": str(context["project_id"]),
    }


async def _register_user(client: AsyncClient, tag: str) -> tuple[dict[str, str], dict]:
    suffix = _unique_suffix()
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"it_mod26_{tag}_{suffix}@demo.local",
            "password": "demo123456",
            "name": f"Module26 {tag} {suffix}",
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["default_context"] is not None
    return _context_headers(data["access_token"], data["default_context"]), data


async def _admin_headers(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@demo.local", "password": "demo123456"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    return _context_headers(data["access_token"], data["default_context"])


async def _assign_project_role(email: str, project_id: int, role: str) -> None:
    async with async_session_factory() as session:
        user_result = await session.execute(select(User).where(User.email == email))
        user = user_result.scalar_one()
        role_result = await session.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == user.id,
                UserProjectRole.project_id == project_id,
            )
        )
        role_row = role_result.scalar_one_or_none()
        role_repo = BaseRepository(UserProjectRole, session)
        if role_row is None:
            await role_repo.create(
                {
                    "user_id": user.id,
                    "project_id": project_id,
                    "role": role,
                }
            )
        else:
            await role_repo.update(role_row, {"role": role})
        await session.commit()


def _base_generate_payload() -> dict:
    suffix = _unique_suffix()
    return {
        "question": f"Why did weekly revenue change? {suffix}",
        "question_weight": "HEAVY",
        "metric_candidates": [
            {
                "metric_key": f"revenue_{suffix}",
                "label": "Revenue",
                "domain": "finance",
                "is_core_metric": False,
            }
        ],
        "conflicts": [],
        "review_requirements": [
            {
                "code": "VALIDATE_SCOPE",
                "summary": "Make sure the result stays planning-only.",
            }
        ],
        "evidence_bundle": {
            "official": [
                {
                    "title": "Revenue definition",
                    "summary": "Authoritative metric definition",
                    "content": "Revenue is recognized net of refunds.",
                    "doc_type": "METRIC_DEFINITION",
                    "module": "finance",
                    "tags": ["revenue"],
                    "meta_payload": {"document_id": f"doc-{suffix}"},
                }
            ],
            "historical": [],
            "field_facts": [],
        },
        "result_service_plan": {
            "result_kind": "TABLE",
            "freshness_mode": "ON_DEMAND",
            "publishable": True,
            "recommended_engine": "duckdb",
            "reuse_key": f"reuse:{suffix}",
        },
    }


async def _fetch_plan(plan_id: int) -> AnalysisPlan:
    async with async_session_factory() as session:
        result = await session.execute(select(AnalysisPlan).where(AnalysisPlan.id == plan_id))
        return result.scalar_one()


async def _fetch_workflow_and_task(workflow_id: int) -> tuple[CollaborationWorkflow, CollaborationTask]:
    async with async_session_factory() as session:
        workflow_result = await session.execute(
            select(CollaborationWorkflow).where(CollaborationWorkflow.id == workflow_id)
        )
        task_result = await session.execute(
            select(CollaborationTask).where(CollaborationTask.workflow_id == workflow_id)
        )
        return workflow_result.scalar_one(), task_result.scalar_one()


@pytest.mark.asyncio
async def test_module26_generate_plan_persists_reviewable_payloads(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "persist")
    payload = _base_generate_payload()

    generate_resp = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert generate_resp.status_code == 201
    plan = generate_resp.json()["data"]
    assert plan["status"] == "GENERATED"
    assert plan["metric_candidates"] == payload["metric_candidates"]
    assert plan["conflicts"] == []
    assert plan["result_service_plan"] == payload["result_service_plan"]

    persisted = await _fetch_plan(plan["id"])
    assert persisted.metric_candidates == payload["metric_candidates"]
    assert persisted.conflicts == []
    assert persisted.result_service_plan == payload["result_service_plan"]

    list_resp = await client.get("/api/v1/analysis-planner/plans", headers=viewer_headers)
    assert list_resp.status_code == 200
    assert any(item["id"] == plan["id"] for item in list_resp.json()["data"]["items"])

    detail_resp = await client.get(
        f"/api/v1/analysis-planner/plans/{plan['id']}",
        headers=viewer_headers,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["result_service_plan"]["reuse_key"] == payload["result_service_plan"]["reuse_key"]

    confirm_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan['id']}/review-actions",
        json={"action": "CONFIRM", "note": "Looks review-ready."},
        headers=viewer_headers,
    )
    assert confirm_resp.status_code == 200
    assert confirm_resp.json()["data"]["status"] == "REVIEW_CONFIRMED"


@pytest.mark.asyncio
async def test_module26_business_conflict_creates_collaboration_workflow(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "business_conflict")
    payload = _base_generate_payload()
    payload["metric_candidates"][0]["is_core_metric"] = True
    payload["conflicts"] = [
        {
            "conflict_type": "BUSINESS_DEFINITION_MISMATCH",
            "summary": "Revenue definition differs between finance and growth docs.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": True,
            "requires_cross_source_access": False,
        }
    ]

    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert response.status_code == 201
    plan = response.json()["data"]
    assert plan["status"] == "REVIEW_REQUIRED"
    assert plan["collaboration_workflow_id"] is not None

    workflow, task = await _fetch_workflow_and_task(plan["collaboration_workflow_id"])
    assert workflow.source_type == "ANALYSIS_PLAN"
    assert workflow.status == "PENDING_APPROVAL"
    assert workflow.current_assignee_role == "APPROVER"
    assert task.assignee_role == "APPROVER"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("conflict_type", "requires_cross_source_access", "expected_role"),
    [
        ("FIELD_FACT_MISMATCH", False, "EDITOR"),
        ("PERMISSION_BLOCKER", False, "ADMIN"),
        ("HIGH_COST_REVIEW", False, "APPROVER"),
    ],
)
async def test_module26_conflict_routes_map_to_expected_assignee_roles(
    client: AsyncClient,
    conflict_type: str,
    requires_cross_source_access: bool,
    expected_role: str,
):
    viewer_headers, _ = await _register_user(client, f"route_{conflict_type.lower()}")
    payload = _base_generate_payload()
    payload["conflicts"] = [
        {
            "conflict_type": conflict_type,
            "summary": f"Route {conflict_type} for review.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": False,
            "requires_cross_source_access": requires_cross_source_access,
        }
    ]

    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert response.status_code == 201
    workflow_id = response.json()["data"]["collaboration_workflow_id"]
    _, task = await _fetch_workflow_and_task(workflow_id)
    assert task.assignee_role == expected_role


@pytest.mark.asyncio
async def test_module26_invalid_conflict_type_is_rejected_cleanly(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "invalid_conflict")
    payload = _base_generate_payload()
    payload["conflicts"] = [
        {
            "conflict_type": "NOT_A_REAL_CONFLICT",
            "summary": "This should fail validation.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": False,
            "requires_cross_source_access": False,
        }
    ]

    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_module26_invalid_question_weight_is_rejected_cleanly(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "invalid_weight")
    payload = _base_generate_payload()
    payload["question_weight"] = "MEGA_HEAVY"

    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_module26_multi_conflict_uses_single_primary_review_owner_consistently(client: AsyncClient):
    initiator_headers, initiator_data = await _register_user(client, "multi_primary")
    editor_headers, editor_data = await _register_user(client, "multi_editor")
    await _assign_project_role(
        editor_data["user"]["email"],
        initiator_data["default_context"]["project_id"],
        "EDITOR",
    )
    payload = _base_generate_payload()
    payload["conflicts"] = [
        {
            "conflict_type": "FIELD_FACT_MISMATCH",
            "summary": "Field fact mismatch needs editor review.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": False,
            "requires_cross_source_access": False,
        },
        {
            "conflict_type": "PERMISSION_BLOCKER",
            "summary": "Cross-source access is blocked pending admin approval.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": False,
            "requires_cross_source_access": True,
        },
    ]

    create_resp = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=initiator_headers,
    )

    assert create_resp.status_code == 201
    plan = create_resp.json()["data"]
    workflow, task = await _fetch_workflow_and_task(plan["collaboration_workflow_id"])
    assert workflow.current_assignee_role == "ADMIN"
    assert task.assignee_role == "ADMIN"

    editor_project_headers = {
        **editor_headers,
        "X-TENANT-ID": str(initiator_data["default_context"]["tenant_id"]),
        "X-PROJECT-ID": str(initiator_data["default_context"]["project_id"]),
    }
    editor_confirm_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan['id']}/review-actions",
        json={"action": "CONFIRM", "note": "Editor trying to confirm."},
        headers=editor_project_headers,
    )
    assert editor_confirm_resp.status_code == 403

    admin_headers = await _admin_headers(client)
    admin_confirm_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan['id']}/review-actions",
        json={"action": "CONFIRM", "note": "Admin resolves primary review."},
        headers=admin_headers,
    )
    assert admin_confirm_resp.status_code == 200
    assert admin_confirm_resp.json()["data"]["status"] == "REVIEW_CONFIRMED"


@pytest.mark.asyncio
async def test_module26_api_key_callers_are_forbidden(client: AsyncClient):
    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=_base_generate_payload(),
        headers={"X-API-KEY": "demo-key-001"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_module26_viewer_cannot_confirm_blocked_high_cost_plan(client: AsyncClient):
    viewer_headers, viewer_data = await _register_user(client, "viewer_confirm")
    await _assign_project_role(
        viewer_data["user"]["email"],
        viewer_data["default_context"]["project_id"],
        "VIEWER",
    )
    payload = _base_generate_payload()
    payload["conflicts"] = [
        {
            "conflict_type": "HIGH_COST_REVIEW",
            "summary": "Estimated execution cost is above the safe threshold.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": False,
            "requires_cross_source_access": False,
        }
    ]

    create_resp = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["data"]["id"]

    confirm_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan_id}/review-actions",
        json={"action": "CONFIRM", "note": "I want to force this through."},
        headers=viewer_headers,
    )

    assert confirm_resp.status_code == 403


@pytest.mark.asyncio
async def test_module26_core_metric_conflict_cannot_skip_review(client: AsyncClient):
    approver_headers, _ = await _register_user(client, "core_metric_review")
    payload = _base_generate_payload()
    payload["metric_candidates"][0]["is_core_metric"] = True
    payload["conflicts"] = [
        {
            "conflict_type": "BUSINESS_DEFINITION_MISMATCH",
            "summary": "Core metric definitions disagree across official sources.",
            "metric_key": payload["metric_candidates"][0]["metric_key"],
            "is_core_metric": True,
            "requires_cross_source_access": False,
        }
    ]

    create_resp = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=approver_headers,
    )

    assert create_resp.status_code == 201
    plan = create_resp.json()["data"]
    assert plan["status"] == "REVIEW_REQUIRED"
    assert plan["collaboration_workflow_id"] is not None

    list_resp = await client.get("/api/v1/analysis-planner/plans", headers=approver_headers)
    assert list_resp.status_code == 200
    list_item = next(item for item in list_resp.json()["data"]["items"] if item["id"] == plan["id"])
    assert list_item["status"] == "REVIEW_REQUIRED"

    detail_resp = await client.get(
        f"/api/v1/analysis-planner/plans/{plan['id']}",
        headers=approver_headers,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["status"] == "REVIEW_REQUIRED"


@pytest.mark.asyncio
async def test_module26_v1_exposes_no_execution_transition(client: AsyncClient):
    admin_headers = await _admin_headers(client)
    create_resp = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=_base_generate_payload(),
        headers=admin_headers,
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["data"]["id"]

    execute_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan_id}/execute",
        headers=admin_headers,
    )

    assert execute_resp.status_code == 404


@pytest.mark.asyncio
async def test_module26_second_finalize_attempt_gets_409_after_first_review_finalizes(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "double_finalize")
    create_resp = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=_base_generate_payload(),
        headers=viewer_headers,
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["data"]["id"]

    first_confirm_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan_id}/review-actions",
        json={"action": "CONFIRM", "note": "First finalize wins."},
        headers=viewer_headers,
    )

    assert first_confirm_resp.status_code == 200
    assert first_confirm_resp.json()["data"]["status"] == "REVIEW_CONFIRMED"

    second_reject_resp = await client.post(
        f"/api/v1/analysis-planner/plans/{plan_id}/review-actions",
        json={"action": "REJECT", "note": "Should conflict after finalize."},
        headers=viewer_headers,
    )

    assert second_reject_resp.status_code == 409
    payload = second_reject_resp.json()
    assert payload["message"] == "Plan is already finalized"


@pytest.mark.asyncio
async def test_module26_invalid_result_service_plan_enum_is_rejected_cleanly(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "invalid_service_plan")
    payload = _base_generate_payload()
    payload["result_service_plan"]["freshness_mode"] = "REALTIME_FOREVER"

    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_module26_malformed_evidence_bundle_is_rejected_cleanly(client: AsyncClient):
    viewer_headers, _ = await _register_user(client, "malformed_evidence")
    payload = _base_generate_payload()
    payload["evidence_bundle"]["official"] = [
        {
            "title": "Revenue definition",
            "summary": "Missing official content should fail.",
            "doc_type": "METRIC_DEFINITION",
            "module": "finance",
            "tags": ["revenue"],
            "meta_payload": {"document_id": "bad-doc"},
        }
    ]

    response = await client.post(
        "/api/v1/analysis-planner/plans/generate",
        json=payload,
        headers=viewer_headers,
    )

    assert response.status_code == 422
