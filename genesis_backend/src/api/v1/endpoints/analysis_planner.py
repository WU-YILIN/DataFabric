from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.domain.analysis_planner import ConflictType, QuestionWeight, route_conflict
from src.infrastructure.database.models.analysis_plan import AnalysisPlan
from src.infrastructure.database.models.collaboration_task import CollaborationTask
from src.infrastructure.database.models.collaboration_workflow import CollaborationWorkflow
from src.infrastructure.database.repositories.analysis_plan_repo import AnalysisPlanRepository
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

PLAN_STATUSES = {"GENERATED", "REVIEW_REQUIRED", "REVIEW_CONFIRMED", "REJECTED"}
REVIEW_ACTIONS = {"CONFIRM", "REJECT"}
ROLE_REVIEW_PRIORITY = {
    "EDITOR": 1,
    "APPROVER": 2,
    "OWNER": 3,
    "ADMIN": 4,
}
CONFLICT_REVIEW_PRIORITY = {
    ConflictType.FIELD_FACT_MISMATCH: 1,
    ConflictType.HIGH_COST_REVIEW: 2,
    ConflictType.BUSINESS_DEFINITION_MISMATCH: 3,
    ConflictType.PERMISSION_BLOCKER: 4,
}


class MetricCandidateInput(BaseModel):
    metric_key: str = Field(..., min_length=1, max_length=255)
    label: str = Field(..., min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    is_core_metric: bool = False


class ConflictInput(BaseModel):
    conflict_type: ConflictType
    summary: str = Field(..., min_length=1, max_length=1000)
    metric_key: str | None = Field(default=None, max_length=255)
    is_core_metric: bool = False
    requires_cross_source_access: bool = False


class ReviewRequirementInput(BaseModel):
    code: str = Field(..., min_length=1, max_length=64)
    summary: str = Field(..., min_length=1, max_length=1000)


class ResultKind(StrEnum):
    TABLE = "TABLE"


class FreshnessMode(StrEnum):
    ON_DEMAND = "ON_DEMAND"


class RecommendedEngine(StrEnum):
    DUCKDB = "duckdb"


class OfficialEvidenceRowInput(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = Field(..., min_length=1, max_length=1000)
    content: str = Field(..., min_length=1)
    doc_type: str = Field(..., min_length=1, max_length=128)
    module: str = Field(..., min_length=1, max_length=255)
    tags: list[str] = Field(default_factory=list)
    meta_payload: dict[str, Any] = Field(default_factory=dict)


class HistoricalEvidenceRowInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    kind: str = Field(..., min_length=1, max_length=128)
    scenario: str = Field(..., min_length=1, max_length=255)
    status: str = Field(..., min_length=1, max_length=128)
    tags: list[str] = Field(default_factory=list)
    query_payload: dict[str, Any] = Field(default_factory=dict)
    cached_result_payload: dict[str, Any] = Field(default_factory=dict)


class FieldFactEvidenceRowInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    asset_type: str = Field(..., min_length=1, max_length=128)
    source_system: str = Field(..., min_length=1, max_length=255)
    database_name: str = Field(..., min_length=1, max_length=255)
    object_name: str = Field(..., min_length=1, max_length=255)
    domain: str = Field(..., min_length=1, max_length=255)
    description: str = Field(..., min_length=1, max_length=1000)
    schema_definition: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class EvidenceBundleInput(BaseModel):
    official: list[OfficialEvidenceRowInput] = Field(default_factory=list)
    historical: list[HistoricalEvidenceRowInput] = Field(default_factory=list)
    field_facts: list[FieldFactEvidenceRowInput] = Field(default_factory=list)


class ResultServicePlanInput(BaseModel):
    result_kind: ResultKind
    freshness_mode: FreshnessMode
    publishable: bool
    recommended_engine: RecommendedEngine
    reuse_key: str = Field(..., min_length=1, max_length=255)


class GeneratePlanRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    question_weight: QuestionWeight = QuestionWeight.LIGHT
    metric_candidates: list[MetricCandidateInput] = Field(default_factory=list)
    conflicts: list[ConflictInput] = Field(default_factory=list)
    review_requirements: list[ReviewRequirementInput] = Field(default_factory=list)
    evidence_bundle: EvidenceBundleInput = Field(default_factory=EvidenceBundleInput)
    result_service_plan: ResultServicePlanInput


class ReviewActionRequest(BaseModel):
    action: str = Field(..., min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=1000)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(mode="json")
    return model.dict()


def _require_bearer_user_context(context: RequestContext) -> None:
    if context.auth_mode != "bearer" or context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Analysis planner API requires bearer user context",
        )


def _route_payload(conflict: dict[str, Any]) -> dict[str, Any]:
    route = route_conflict(
        ConflictType(conflict["conflict_type"]),
        is_core_metric=bool(conflict.get("is_core_metric")),
        requires_cross_source_access=bool(conflict.get("requires_cross_source_access")),
    )
    return {
        "conflict_type": route.conflict_type.value,
        "owner_role": route.owner_role,
        "escalation_roles": list(route.escalation_roles),
        "review_required": route.review_required,
    }


def _derive_primary_review_route(conflicts: list[dict[str, Any]]) -> dict[str, Any]:
    routed_conflicts = [
        {
            **conflict,
            "route": _route_payload(conflict),
        }
        for conflict in conflicts
    ]
    routed_conflicts.sort(
        key=lambda item: (
            ROLE_REVIEW_PRIORITY[item["route"]["owner_role"]],
            CONFLICT_REVIEW_PRIORITY[ConflictType(item["conflict_type"])],
            len(item["route"]["escalation_roles"]),
        ),
        reverse=True,
    )
    return routed_conflicts[0]


def _plan_to_row(plan: AnalysisPlan) -> dict[str, Any]:
    return {
        "id": plan.id,
        "project_id": plan.project_id,
        "tenant_id": plan.tenant_id,
        "question": plan.question,
        "status": plan.status,
        "question_weight": plan.question_weight,
        "metric_candidates": plan.metric_candidates,
        "conflicts": plan.conflicts,
        "review_requirements": plan.review_requirements,
        "evidence_bundle": plan.evidence_bundle,
        "result_service_plan": plan.result_service_plan,
        "collaboration_workflow_id": plan.collaboration_workflow_id,
        "created_at": _to_iso(plan.created_at),
        "updated_at": _to_iso(plan.updated_at),
    }


def _context_roles(context: RequestContext) -> set[str]:
    roles = set()
    if context.project_role:
        roles.add(context.project_role.upper())
    if context.tenant_role:
        roles.add(context.tenant_role.upper())
    return roles


def _has_review_permission(context: RequestContext, primary_conflict: dict[str, Any]) -> bool:
    roles = _context_roles(context)
    if roles.intersection(TENANT_ELEVATED_ROLES):
        return True
    route = primary_conflict["route"] if "route" in primary_conflict else _route_payload(primary_conflict)
    allowed_roles = {route["owner_role"], *route["escalation_roles"]}
    return bool(roles.intersection(allowed_roles))


async def _complete_open_workflow_tasks(db: AsyncSession, workflow_id: int, actor_id: str) -> None:
    result = await db.execute(
        select(CollaborationTask).where(
            CollaborationTask.workflow_id == workflow_id,
            CollaborationTask.status == "OPEN",
        )
    )
    task_repo = BaseRepository(CollaborationTask, db)
    now = datetime.now(timezone.utc)
    for task in result.scalars().all():
        await task_repo.update(
            task,
            {
                "status": "DONE",
                "completed_at": now,
                "completed_by": actor_id,
            },
        )


async def _create_collaboration_review(
    db: AsyncSession,
    context: RequestContext,
    plan: AnalysisPlan,
    conflicts: list[dict[str, Any]],
) -> int:
    primary_conflict = _derive_primary_review_route(conflicts)
    primary_route = primary_conflict["route"]
    priority = "HIGH" if primary_conflict["conflict_type"] in {"PERMISSION_BLOCKER", "HIGH_COST_REVIEW"} else "MEDIUM"
    workflow = await BaseRepository(CollaborationWorkflow, db).create(
        {
            "project_id": context.project.id,
            "tenant_id": context.project.tenant_id,
            "workflow_type": "ANALYSIS_PLAN_REVIEW",
            "source_type": "ANALYSIS_PLAN",
            "source_id": str(plan.id),
            "title": f"Review analysis plan #{plan.id}",
            "description": primary_conflict["summary"],
            "status": "PENDING_APPROVAL",
            "priority": priority,
            "initiator_id": context.actor_id,
            "initiator_user_id": context.user.id,
            "current_assignee_user_id": None,
            "current_assignee_role": primary_route["owner_role"],
            "started_at": None,
            "completed_at": None,
            "context_payload": {
                "plan_id": plan.id,
                "question": plan.question,
                "primary_review_rule": "highest owner-role priority across conflicts; tie-break by conflict priority, then escalation breadth",
                "primary_conflict": primary_conflict,
                "conflicts": [
                    {
                        **conflict,
                        "route": _route_payload(conflict),
                    }
                    for conflict in conflicts
                ],
            },
            "outcome": {},
        }
    )
    await BaseRepository(CollaborationTask, db).create(
        {
            "workflow_id": workflow.id,
            "project_id": context.project.id,
            "title": f"Review analysis plan #{plan.id}",
            "description": primary_conflict["summary"],
            "action_type": "REVIEW",
            "status": "OPEN",
            "priority": priority,
            "assignee_user_id": None,
            "assignee_role": primary_route["owner_role"],
            "due_at": None,
            "completed_at": None,
            "completed_by": None,
        }
    )
    return workflow.id


@router.post("/plans/generate", status_code=status.HTTP_201_CREATED)
async def generate_plan(
    request: GeneratePlanRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_bearer_user_context(context)
    repo = AnalysisPlanRepository(db)
    conflicts = [_model_to_dict(item) for item in request.conflicts]
    status_value = "REVIEW_REQUIRED" if conflicts else "GENERATED"
    plan = await repo.create(
        {
            "project_id": context.project.id,
            "tenant_id": context.project.tenant_id,
            "question": request.question,
            "status": status_value,
            "question_weight": request.question_weight.value,
            "metric_candidates": [_model_to_dict(item) for item in request.metric_candidates],
            "conflicts": conflicts,
            "review_requirements": [_model_to_dict(item) for item in request.review_requirements],
            "evidence_bundle": _model_to_dict(request.evidence_bundle),
            "result_service_plan": _model_to_dict(request.result_service_plan),
            "collaboration_workflow_id": None,
        }
    )
    if conflicts:
        workflow_id = await _create_collaboration_review(db, context, plan, conflicts)
        plan = await repo.update(plan, {"collaboration_workflow_id": workflow_id, "status": "REVIEW_REQUIRED"})
    await db.commit()
    return success_response(_plan_to_row(plan), message="Plan generated", code="ANALYSIS_PLAN_GENERATED")


@router.get("/plans")
async def list_plans(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_bearer_user_context(context)
    repo = AnalysisPlanRepository(db)
    items = await repo.list_by_project(context.project.id)
    return success_response(
        {
            "items": [_plan_to_row(item) for item in items],
            "total": len(items),
        }
    )


@router.get("/plans/{plan_id}")
async def get_plan(
    plan_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_bearer_user_context(context)
    repo = AnalysisPlanRepository(db)
    plan = await repo.get_by_project(plan_id, context.project.id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    return success_response(_plan_to_row(plan))


@router.post("/plans/{plan_id}/review-actions")
async def review_plan_action(
    plan_id: int,
    request: ReviewActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_bearer_user_context(context)
    action = request.action.strip().upper()
    if action not in REVIEW_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action: {request.action}")

    repo = AnalysisPlanRepository(db)
    plan = await repo.get_by_project(plan_id, context.project.id)
    if not plan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    conflicts = plan.conflicts or []
    if conflicts:
        primary_conflict = _derive_primary_review_route(conflicts)
        if not _has_review_permission(context, primary_conflict):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role for plan review")

    next_status = "REVIEW_CONFIRMED" if action == "CONFIRM" else "REJECTED"
    transitioned = await repo.transition_status_if_current_in(
        plan_id=plan_id,
        project_id=context.project.id,
        allowed_current_statuses=("GENERATED", "REVIEW_REQUIRED"),
        next_status=next_status,
    )
    if not transitioned:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Plan is already finalized")
    plan = await repo.get_by_project(plan_id, context.project.id)
    if plan is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")

    if plan.collaboration_workflow_id is not None:
        workflow_result = await db.execute(
            select(CollaborationWorkflow).where(
                CollaborationWorkflow.id == plan.collaboration_workflow_id,
                CollaborationWorkflow.project_id == context.project.id,
            )
        )
        workflow = workflow_result.scalar_one_or_none()
        if workflow is not None:
            now = datetime.now(timezone.utc)
            workflow_status = "COMPLETED" if action == "CONFIRM" else "REJECTED"
            await BaseRepository(CollaborationWorkflow, db).update(
                workflow,
                {
                    "status": workflow_status,
                    "completed_at": now,
                    "outcome": {
                        "decision": next_status,
                        "note": request.note,
                        "actor": context.actor_id,
                        "at": now.isoformat(),
                    },
                },
            )
            await _complete_open_workflow_tasks(db, workflow.id, context.actor_id)

    await db.commit()
    return success_response(_plan_to_row(plan), message="Plan reviewed", code="ANALYSIS_PLAN_REVIEWED")
