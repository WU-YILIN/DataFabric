import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import parse_actor
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.collaboration_action_history import CollaborationActionHistory
from src.infrastructure.database.models.collaboration_comment import CollaborationComment
from src.infrastructure.database.models.collaboration_task import CollaborationTask
from src.infrastructure.database.models.collaboration_workflow import CollaborationWorkflow
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.user import User, UserProjectRole
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

WORKFLOW_STATUSES = {
    "PENDING_APPROVAL",
    "IN_PROGRESS",
    "REVISION_REQUIRED",
    "COMPLETED",
    "REJECTED",
}
TASK_STATUSES = {"OPEN", "DONE"}
ALLOWED_PRIORITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
ALLOWED_ACTIONS = {"APPROVE", "REJECT", "REQUEST_REVISION", "START", "COMPLETE", "ASSIGN"}


class WorkflowCreateRequest(BaseModel):
    workflow_type: str = Field(..., min_length=2, max_length=64)
    source_type: str = Field(..., min_length=2, max_length=64)
    source_id: str = Field(..., min_length=1, max_length=128)
    title: str = Field(..., min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)
    priority: str = Field(default="MEDIUM", min_length=3, max_length=16)
    assignee_user_id: int | None = None
    assignee_role: str | None = Field(default=None, max_length=64)
    due_in_hours: int | None = Field(default=None, ge=1, le=720)
    context_payload: dict[str, Any] = Field(default_factory=dict)
    initial_task_title: str | None = Field(default=None, max_length=255)
    initial_task_description: str | None = Field(default=None, max_length=2000)


class WorkflowCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class WorkflowActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=32)
    note: str | None = Field(default=None, max_length=1000)
    assignee_user_id: int | None = None
    assignee_role: str | None = Field(default=None, max_length=64)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _to_iso(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in value]
    return value


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Collaboration API requires bearer user context",
        )


def _normalize_priority(priority: str) -> str:
    normalized = priority.strip().upper()
    if normalized not in ALLOWED_PRIORITIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported priority: {priority}")
    return normalized


def _normalize_status(status_value: str | None) -> str | None:
    if not status_value:
        return None
    normalized = status_value.strip().upper()
    if normalized not in WORKFLOW_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported status: {status_value}")
    return normalized


def _normalize_role(role_value: str | None) -> str | None:
    if role_value is None:
        return None
    normalized = role_value.strip().upper()
    if not normalized:
        return None
    return normalized


def _mentions_from_text(content: str) -> list[str]:
    matches = re.findall(r"@([A-Za-z0-9_.+\-]+)", content)
    unique_values: list[str] = []
    for item in matches:
        if item not in unique_values:
            unique_values.append(item)
    return unique_values


def _workflow_to_row(workflow: CollaborationWorkflow) -> dict[str, Any]:
    return {
        "id": workflow.id,
        "project_id": workflow.project_id,
        "tenant_id": workflow.tenant_id,
        "workflow_type": workflow.workflow_type,
        "source_type": workflow.source_type,
        "source_id": workflow.source_id,
        "title": workflow.title,
        "description": workflow.description,
        "status": workflow.status,
        "priority": workflow.priority,
        "initiator": parse_actor(workflow.initiator_id),
        "initiator_id": workflow.initiator_id,
        "initiator_user_id": workflow.initiator_user_id,
        "current_assignee_user_id": workflow.current_assignee_user_id,
        "current_assignee_role": workflow.current_assignee_role,
        "started_at": _to_iso(workflow.started_at),
        "completed_at": _to_iso(workflow.completed_at),
        "context_payload": workflow.context_payload,
        "outcome": workflow.outcome,
        "created_at": _to_iso(workflow.created_at),
        "updated_at": _to_iso(workflow.updated_at),
    }


def _task_to_row(task: CollaborationTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "workflow_id": task.workflow_id,
        "title": task.title,
        "description": task.description,
        "action_type": task.action_type,
        "status": task.status,
        "priority": task.priority,
        "assignee_user_id": task.assignee_user_id,
        "assignee_role": task.assignee_role,
        "due_at": _to_iso(task.due_at),
        "completed_at": _to_iso(task.completed_at),
        "completed_by": task.completed_by,
        "created_at": _to_iso(task.created_at),
        "updated_at": _to_iso(task.updated_at),
    }


def _comment_to_row(comment: CollaborationComment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "author": parse_actor(comment.author_id),
        "author_id": comment.author_id,
        "content": comment.content,
        "mentions": comment.mentions,
        "created_at": _to_iso(comment.created_at),
    }


def _action_history_to_row(item: CollaborationActionHistory) -> dict[str, Any]:
    return {
        "id": item.id,
        "action": item.action,
        "actor": parse_actor(item.actor_id),
        "actor_id": item.actor_id,
        "note": item.note,
        "payload": item.payload,
        "created_at": _to_iso(item.created_at),
    }


def _is_task_visible(task: CollaborationTask, context: RequestContext) -> bool:
    if task.status != "OPEN":
        return False
    if context.user and task.assignee_user_id is not None:
        return task.assignee_user_id == context.user.id
    if task.assignee_role:
        role = task.assignee_role.upper()
        project_role = (context.project_role or "").upper()
        tenant_role = (context.tenant_role or "").upper()
        if project_role == role:
            return True
        if tenant_role == role:
            return True
        if role in {"OWNER", "ADMIN"} and tenant_role in TENANT_ELEVATED_ROLES:
            return True
        return False
    return True


async def _complete_open_tasks(
    db: AsyncSession,
    workflow_id: int,
    actor_id: str,
) -> None:
    task_result = await db.execute(
        select(CollaborationTask).where(
            CollaborationTask.workflow_id == workflow_id,
            CollaborationTask.status == "OPEN",
        )
    )
    task_repo = BaseRepository(CollaborationTask, db)
    now = datetime.now(timezone.utc)
    for task in task_result.scalars().all():
        await task_repo.update(
            task,
            {
                "status": "DONE",
                "completed_at": now,
                "completed_by": actor_id,
            },
        )


async def _load_workflow_detail(
    db: AsyncSession,
    workflow: CollaborationWorkflow,
) -> dict[str, Any]:
    task_result = await db.execute(
        select(CollaborationTask)
        .where(CollaborationTask.workflow_id == workflow.id)
        .order_by(CollaborationTask.created_at.asc())
    )
    comment_result = await db.execute(
        select(CollaborationComment)
        .where(CollaborationComment.workflow_id == workflow.id)
        .order_by(CollaborationComment.created_at.asc())
    )
    history_result = await db.execute(
        select(CollaborationActionHistory)
        .where(CollaborationActionHistory.workflow_id == workflow.id)
        .order_by(CollaborationActionHistory.created_at.desc())
    )

    linked_object = {
        "source_type": workflow.source_type,
        "source_id": workflow.source_id,
        "route": "/logs",
    }
    source = workflow.source_type.upper()
    if source == "TRACKING_EVENT":
        linked_object["route"] = "/events"
    elif source == "DATA_QUALITY_RULE":
        linked_object["route"] = "/data-quality"
    elif source == "PIPELINE":
        linked_object["route"] = "/pipelines"
    elif source == "ALERT":
        linked_object["route"] = "/monitoring"

    return {
        "workflow": _workflow_to_row(workflow),
        "tasks": [_task_to_row(item) for item in task_result.scalars().all()],
        "comments": [_comment_to_row(item) for item in comment_result.scalars().all()],
        "action_history": [_action_history_to_row(item) for item in history_result.scalars().all()],
        "linked_object": linked_object,
    }


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    workflow: CollaborationWorkflow,
    details: dict[str, Any],
) -> None:
    serialized_details = _json_safe(details)
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "COLLAB_WORKFLOW",
            "entity_id": str(workflow.id),
            "user_id": context.actor_id,
            "details": json.dumps(serialized_details, ensure_ascii=True),
        }
    )


async def _backwrite_business_object(
    db: AsyncSession,
    workflow: CollaborationWorkflow,
    action: str,
    note: str | None,
) -> dict[str, Any]:
    source = workflow.source_type.upper()
    source_id = workflow.source_id
    if not source_id.isdigit():
        return {"updated": False, "reason": "source_id_not_numeric"}
    entity_id = int(source_id)

    if source == "TRACKING_EVENT":
        result = await db.execute(
            select(TrackingEvent).where(
                TrackingEvent.id == entity_id,
                TrackingEvent.project_id == workflow.project_id,
            )
        )
        event = result.scalar_one_or_none()
        if not event:
            return {"updated": False, "reason": "event_not_found"}
        target_status = None
        if action == "APPROVE":
            target_status = "APPROVED"
        elif action == "REQUEST_REVISION":
            target_status = "NEEDS_REVISION"
        elif action == "REJECT":
            target_status = "REJECTED"
        if target_status:
            await BaseRepository(TrackingEvent, db).update(event, {"governance_status": target_status})
            return {"updated": True, "entity": "TRACKING_EVENT", "entity_id": entity_id, "status": target_status}
        return {"updated": False, "reason": "action_noop_for_event"}

    if source == "DATA_QUALITY_RULE":
        result = await db.execute(
            select(DataQualityRule).where(
                DataQualityRule.id == entity_id,
                DataQualityRule.project_id == workflow.project_id,
            )
        )
        rule = result.scalar_one_or_none()
        if not rule:
            return {"updated": False, "reason": "rule_not_found"}
        target_status = None
        if action == "APPROVE":
            target_status = "ACTIVE"
        elif action == "REQUEST_REVISION":
            target_status = "DRAFT"
        elif action == "REJECT":
            target_status = "DEPRECATED"
        if target_status:
            await BaseRepository(DataQualityRule, db).update(rule, {"status": target_status})
            return {"updated": True, "entity": "DATA_QUALITY_RULE", "entity_id": entity_id, "status": target_status}
        return {"updated": False, "reason": "action_noop_for_rule"}

    if source == "PIPELINE":
        result = await db.execute(
            select(Pipeline).where(
                Pipeline.id == entity_id,
                Pipeline.project_id == workflow.project_id,
            )
        )
        pipeline = result.scalar_one_or_none()
        if not pipeline:
            return {"updated": False, "reason": "pipeline_not_found"}
        config = pipeline.config if isinstance(pipeline.config, dict) else {}
        config = {
            **config,
            "collaboration_workflow_id": workflow.id,
            "collaboration_last_action": action,
            "collaboration_last_note": note,
        }
        await BaseRepository(Pipeline, db).update(pipeline, {"config": config})
        return {"updated": True, "entity": "PIPELINE", "entity_id": entity_id, "config_updated": True}

    return {"updated": False, "reason": "unsupported_source_type"}


@router.get("/overview")
async def get_collaboration_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    workflow_result = await db.execute(
        select(CollaborationWorkflow).where(CollaborationWorkflow.project_id == context.project.id)
    )
    workflows = list(workflow_result.scalars().all())
    task_result = await db.execute(
        select(CollaborationTask).where(
            CollaborationTask.project_id == context.project.id,
            CollaborationTask.status == "OPEN",
        )
    )
    tasks = list(task_result.scalars().all())

    my_todos = [task for task in tasks if _is_task_visible(task, context)]
    initiated = [
        item
        for item in workflows
        if item.initiator_id == context.actor_id or (context.user and item.initiator_user_id == context.user.id)
    ]
    status_counts: dict[str, int] = {}
    for item in workflows:
        status_counts[item.status] = status_counts.get(item.status, 0) + 1

    recent_workflows = sorted(workflows, key=lambda item: item.updated_at, reverse=True)[:20]
    data = {
        "summary": {
            "total_workflows": len(workflows),
            "open_todos": len(my_todos),
            "initiated_count": len(initiated),
            "status_counts": status_counts,
        },
        "my_todos": [_task_to_row(item) for item in sorted(my_todos, key=lambda row: row.created_at, reverse=True)[:50]],
        "initiated_workflows": [_workflow_to_row(item) for item in sorted(initiated, key=lambda row: row.created_at, reverse=True)[:50]],
        "recent_workflows": [_workflow_to_row(item) for item in recent_workflows],
    }
    return success_response(data)


@router.get("/workflows")
async def list_workflows(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    workflow_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    initiated_by_me: bool = Query(default=False),
    my_todos_only: bool = Query(default=False),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    query = select(CollaborationWorkflow).where(CollaborationWorkflow.project_id == context.project.id)
    filters = []
    normalized_status = _normalize_status(status_filter)
    if normalized_status:
        filters.append(CollaborationWorkflow.status == normalized_status)
    if workflow_type:
        filters.append(CollaborationWorkflow.workflow_type == workflow_type.strip().upper())
    if source_type:
        filters.append(CollaborationWorkflow.source_type == source_type.strip().upper())
    if q:
        keyword = f"%{q.strip()}%"
        filters.append(
            or_(
                CollaborationWorkflow.title.ilike(keyword),
                CollaborationWorkflow.description.ilike(keyword),
                CollaborationWorkflow.source_id.ilike(keyword),
                CollaborationWorkflow.source_type.ilike(keyword),
            )
        )
    if filters:
        query = query.where(and_(*filters))
    result = await db.execute(query.order_by(CollaborationWorkflow.updated_at.desc()))
    workflows = list(result.scalars().all())

    if initiated_by_me:
        workflows = [
            item
            for item in workflows
            if item.initiator_id == context.actor_id or (context.user and item.initiator_user_id == context.user.id)
        ]

    open_task_result = await db.execute(
        select(CollaborationTask).where(
            CollaborationTask.project_id == context.project.id,
            CollaborationTask.status == "OPEN",
        )
    )
    open_tasks = list(open_task_result.scalars().all())
    visible_todo_workflow_ids = {
        task.workflow_id
        for task in open_tasks
        if _is_task_visible(task, context)
    }
    if my_todos_only:
        workflows = [item for item in workflows if item.id in visible_todo_workflow_ids]

    total = len(workflows)
    rows = workflows[offset: offset + limit]
    data = {
        "items": [
            {
                **_workflow_to_row(item),
                "open_task_count": len([task for task in open_tasks if task.workflow_id == item.id and task.status == "OPEN"]),
                "is_my_todo": item.id in visible_todo_workflow_ids,
            }
            for item in rows
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }
    return success_response(data)


@router.post("/workflows", status_code=status.HTTP_201_CREATED)
async def create_workflow(
    request: WorkflowCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    priority = _normalize_priority(request.priority)
    assignee_role = _normalize_role(request.assignee_role)

    if request.assignee_user_id is not None:
        user_result = await db.execute(select(User).where(User.id == request.assignee_user_id))
        assignee_user = user_result.scalar_one_or_none()
        if not assignee_user:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignee_user_id is invalid")
        role_result = await db.execute(
            select(UserProjectRole).where(
                UserProjectRole.user_id == request.assignee_user_id,
                UserProjectRole.project_id == context.project.id,
            )
        )
        if role_result.scalar_one_or_none() is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignee user has no project access")

    now = datetime.now(timezone.utc)
    workflow_status = "PENDING_APPROVAL" if (request.assignee_user_id or assignee_role) else "IN_PROGRESS"
    workflow_repo = BaseRepository(CollaborationWorkflow, db)
    workflow = await workflow_repo.create(
        {
            "project_id": context.project.id,
            "tenant_id": context.project.tenant_id,
            "workflow_type": request.workflow_type.strip().upper(),
            "source_type": request.source_type.strip().upper(),
            "source_id": request.source_id.strip(),
            "title": request.title.strip(),
            "description": request.description.strip() if request.description else None,
            "status": workflow_status,
            "priority": priority,
            "initiator_id": context.actor_id,
            "initiator_user_id": context.user.id,
            "current_assignee_user_id": request.assignee_user_id,
            "current_assignee_role": assignee_role,
            "started_at": now if workflow_status == "IN_PROGRESS" else None,
            "context_payload": request.context_payload,
            "outcome": {},
        }
    )

    due_at = now + timedelta(hours=request.due_in_hours) if request.due_in_hours else None
    task_title = request.initial_task_title or f"Review workflow #{workflow.id}"
    task_description = request.initial_task_description or request.description
    task_repo = BaseRepository(CollaborationTask, db)
    await task_repo.create(
        {
            "workflow_id": workflow.id,
            "project_id": context.project.id,
            "title": task_title[:255],
            "description": task_description,
            "action_type": "REVIEW",
            "status": "OPEN",
            "priority": priority,
            "assignee_user_id": request.assignee_user_id,
            "assignee_role": assignee_role,
            "due_at": due_at,
        }
    )

    action_repo = BaseRepository(CollaborationActionHistory, db)
    await action_repo.create(
        {
            "workflow_id": workflow.id,
            "project_id": context.project.id,
            "action": "CREATE",
            "actor_id": context.actor_id,
            "note": None,
            "payload": {
                "workflow_status": workflow_status,
                "priority": priority,
                "assignee_user_id": request.assignee_user_id,
                "assignee_role": assignee_role,
            },
        }
    )
    await _write_audit(
        db,
        context,
        "COLLAB_WORKFLOW_CREATE",
        workflow,
        {
            "workflow_type": workflow.workflow_type,
            "source_type": workflow.source_type,
            "source_id": workflow.source_id,
            "status": workflow.status,
        },
    )

    detail = await _load_workflow_detail(db, workflow)
    return success_response(detail, message="Workflow created", code="COLLAB_WORKFLOW_CREATED")


@router.get("/workflows/{workflow_id}")
async def get_workflow_detail(
    workflow_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    workflow_result = await db.execute(
        select(CollaborationWorkflow).where(
            CollaborationWorkflow.id == workflow_id,
            CollaborationWorkflow.project_id == context.project.id,
        )
    )
    workflow = workflow_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    detail = await _load_workflow_detail(db, workflow)
    return success_response(detail)


@router.post("/workflows/{workflow_id}/comments")
async def add_workflow_comment(
    workflow_id: int,
    request: WorkflowCommentRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    workflow_result = await db.execute(
        select(CollaborationWorkflow).where(
            CollaborationWorkflow.id == workflow_id,
            CollaborationWorkflow.project_id == context.project.id,
        )
    )
    workflow = workflow_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    mentions = _mentions_from_text(request.content)
    comment = await BaseRepository(CollaborationComment, db).create(
        {
            "workflow_id": workflow.id,
            "project_id": context.project.id,
            "author_id": context.actor_id,
            "content": request.content,
            "mentions": mentions,
        }
    )
    await BaseRepository(CollaborationActionHistory, db).create(
        {
            "workflow_id": workflow.id,
            "project_id": context.project.id,
            "action": "COMMENT",
            "actor_id": context.actor_id,
            "note": request.content[:300],
            "payload": {"mentions": mentions},
        }
    )
    await _write_audit(
        db,
        context,
        "COLLAB_WORKFLOW_COMMENT",
        workflow,
        {"comment_id": comment.id, "mentions": mentions},
    )
    return success_response(_comment_to_row(comment), message="Comment added", code="COLLAB_COMMENT_ADDED")


@router.post("/workflows/{workflow_id}/actions")
async def operate_workflow(
    workflow_id: int,
    request: WorkflowActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    action = request.action.strip().upper()
    if action not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action: {request.action}")

    workflow_result = await db.execute(
        select(CollaborationWorkflow).where(
            CollaborationWorkflow.id == workflow_id,
            CollaborationWorkflow.project_id == context.project.id,
        )
    )
    workflow = workflow_result.scalar_one_or_none()
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    now = datetime.now(timezone.utc)
    note = request.note.strip() if request.note else None
    patch: dict[str, Any] = {}
    payload: dict[str, Any] = {}

    if action in {"APPROVE", "REJECT", "REQUEST_REVISION"}:
        await _complete_open_tasks(db, workflow.id, context.actor_id)

    if action == "APPROVE":
        patch = {
            "status": "COMPLETED",
            "completed_at": now,
            "outcome": {
                "decision": "APPROVED",
                "note": note,
                "actor": context.actor_id,
                "at": now.isoformat(),
            },
        }
    elif action == "REJECT":
        patch = {
            "status": "REJECTED",
            "completed_at": now,
            "outcome": {
                "decision": "REJECTED",
                "note": note,
                "actor": context.actor_id,
                "at": now.isoformat(),
            },
        }
    elif action == "REQUEST_REVISION":
        patch = {
            "status": "REVISION_REQUIRED",
            "outcome": {
                "decision": "REVISION_REQUIRED",
                "note": note,
                "actor": context.actor_id,
                "at": now.isoformat(),
            },
        }
        await BaseRepository(CollaborationTask, db).create(
            {
                "workflow_id": workflow.id,
                "project_id": context.project.id,
                "title": f"Revise workflow #{workflow.id}",
                "description": note or "Approver requested revisions.",
                "action_type": "REVISE",
                "status": "OPEN",
                "priority": workflow.priority,
                "assignee_user_id": workflow.initiator_user_id,
                "assignee_role": None,
            }
        )
    elif action == "START":
        patch = {"status": "IN_PROGRESS"}
        if workflow.started_at is None:
            patch["started_at"] = now
    elif action == "COMPLETE":
        patch = {
            "status": "COMPLETED",
            "completed_at": now,
            "outcome": {
                "decision": "COMPLETED",
                "note": note,
                "actor": context.actor_id,
                "at": now.isoformat(),
            },
        }
        await _complete_open_tasks(db, workflow.id, context.actor_id)
    elif action == "ASSIGN":
        assignee_role = _normalize_role(request.assignee_role)
        if request.assignee_user_id is None and assignee_role is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="ASSIGN action requires assignee_user_id or assignee_role",
            )
        if request.assignee_user_id is not None:
            user_result = await db.execute(select(User).where(User.id == request.assignee_user_id))
            if user_result.scalar_one_or_none() is None:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="assignee_user_id is invalid")
        patch = {
            "current_assignee_user_id": request.assignee_user_id,
            "current_assignee_role": assignee_role,
        }
        payload = {
            "assignee_user_id": request.assignee_user_id,
            "assignee_role": assignee_role,
        }
        await BaseRepository(CollaborationTask, db).create(
            {
                "workflow_id": workflow.id,
                "project_id": context.project.id,
                "title": f"Assigned task for workflow #{workflow.id}",
                "description": note or "Workflow reassigned",
                "action_type": "REVIEW",
                "status": "OPEN",
                "priority": workflow.priority,
                "assignee_user_id": request.assignee_user_id,
                "assignee_role": assignee_role,
            }
        )

    workflow = await BaseRepository(CollaborationWorkflow, db).update(workflow, patch)

    backwrite_result = {}
    if action in {"APPROVE", "REJECT", "REQUEST_REVISION"}:
        backwrite_result = await _backwrite_business_object(db, workflow, action, note)

    action_log = await BaseRepository(CollaborationActionHistory, db).create(
        {
            "workflow_id": workflow.id,
            "project_id": context.project.id,
            "action": action,
            "actor_id": context.actor_id,
            "note": note,
            "payload": _json_safe(
                {
                    "patch": patch,
                    "extra": payload,
                    "backwrite": backwrite_result,
                }
            ),
        }
    )

    await _write_audit(
        db,
        context,
        "COLLAB_WORKFLOW_ACTION",
        workflow,
        {
            "action": action,
            "patch": patch,
            "backwrite": backwrite_result,
        },
    )

    detail = await _load_workflow_detail(db, workflow)
    detail["latest_action"] = _action_history_to_row(action_log)
    detail["backwrite"] = backwrite_result
    return success_response(detail, message="Workflow updated", code="COLLAB_WORKFLOW_UPDATED")
