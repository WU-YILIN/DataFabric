import json
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.models.scheduler_dag_edge import SchedulerDagEdge
from src.infrastructure.database.models.scheduler_dag_node import SchedulerDagNode
from src.infrastructure.database.models.scheduler_node_run import SchedulerNodeRun
from src.infrastructure.database.models.scheduler_run import SchedulerRun
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.data_asset_repo import DataAssetRepository
from src.infrastructure.database.repositories.scheduler_dag_edge_repo import (
    SchedulerDagEdgeRepository,
)
from src.infrastructure.database.repositories.scheduler_dag_node_repo import (
    SchedulerDagNodeRepository,
)
from src.infrastructure.database.repositories.scheduler_dag_repo import SchedulerDagRepository
from src.infrastructure.database.repositories.scheduler_node_run_repo import (
    SchedulerNodeRunRepository,
)
from src.infrastructure.database.repositories.scheduler_run_repo import SchedulerRunRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ALLOWED_DAG_STATUS = {"ACTIVE", "PAUSED", "DRAFT", "DEPRECATED"}
ALLOWED_TRIGGER_MODES = {"MANUAL", "CRON", "DEPENDENCY"}
ALLOWED_TASK_TYPES = {"BATCH", "VALIDATION", "SYNC", "CUSTOM"}
ALLOWED_NODE_STATUS = {"PENDING", "RUNNING", "SUCCESS", "FAILED", "SKIPPED"}
ALLOWED_RUN_STATUS = {"PENDING", "RUNNING", "SUCCESS", "FAILED", "PARTIAL", "SKIPPED"}
ALLOWED_ACTIONS = {"RETRY", "SKIP", "MARK_SUCCESS"}


class SchedulerDagNodeInput(BaseModel):
    node_key: str = Field(..., min_length=2, max_length=100)
    name: str = Field(..., min_length=2, max_length=255)
    task_type: str = Field(..., min_length=2, max_length=64)
    input_assets: list[str] = Field(default_factory=list)
    output_assets: list[str] = Field(default_factory=list)
    logic_description: str | None = None
    config: dict = Field(default_factory=dict)
    position: dict = Field(default_factory=dict)


class SchedulerDagEdgeInput(BaseModel):
    from_node_key: str = Field(..., min_length=2, max_length=100)
    to_node_key: str = Field(..., min_length=2, max_length=100)
    condition: dict = Field(default_factory=dict)


class SchedulerDagCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    description: str | None = None
    status: str = "ACTIVE"
    trigger_mode: str = "MANUAL"
    cron_expr: str | None = None
    timezone: str = "UTC"
    dependency_mode: str = "ALL_SUCCESS"
    retry_policy: dict = Field(default_factory=lambda: {"max_retries": 1, "backoff_seconds": 30})
    schedule_config: dict = Field(default_factory=dict)
    nodes: list[SchedulerDagNodeInput] = Field(default_factory=list)
    edges: list[SchedulerDagEdgeInput] = Field(default_factory=list)


class SchedulerDagUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    status: str | None = None
    trigger_mode: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    dependency_mode: str | None = None
    retry_policy: dict | None = None
    schedule_config: dict | None = None
    nodes: list[SchedulerDagNodeInput] | None = None
    edges: list[SchedulerDagEdgeInput] | None = None


class SchedulerRunRequest(BaseModel):
    trigger_source: str = Field(default="MANUAL", min_length=2, max_length=32)
    run_context: dict = Field(default_factory=dict)
    forced_node_results: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None


class SchedulerRunActionRequest(BaseModel):
    action: str = Field(..., min_length=2, max_length=32)
    node_run_id: int | None = None
    reason: str | None = None


class SchedulerEngineTickRequest(BaseModel):
    run_immediately: bool = False
    limit: int = Field(default=50, ge=1, le=500)


def _normalize_dag_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_DAG_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported dag status: {value}",
        )
    return normalized


def _normalize_trigger_mode(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_TRIGGER_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported trigger_mode: {value}",
        )
    return normalized


def _normalize_task_type(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_TASK_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported task_type: {value}",
        )
    return normalized


def _normalize_node_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_NODE_STATUS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported node status: {value}",
        )
    return normalized


def _normalize_action(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in ALLOWED_ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported run action: {value}",
        )
    return normalized


def _bump_patch_version(version: str) -> str:
    try:
        major, minor, patch = [int(item) for item in version.split(".")]
    except Exception:
        major, minor, patch = 1, 0, 0
    patch += 1
    return f"{major}.{minor}.{patch}"


def _parse_field_token(token: str, min_value: int, max_value: int) -> None:
    if token == "*":
        return
    if token.startswith("*/"):
        step_raw = token[2:]
        if not step_raw.isdigit():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cron token: {token}")
        step = int(step_raw)
        if step <= 0 or step > max_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cron step: {token}")
        return
    if not token.isdigit():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid cron token: {token}")
    number = int(token)
    if number < min_value or number > max_value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Cron token out of range: {token}")


def _match_cron_token(value: int, token: str) -> bool:
    if token == "*":
        return True
    if token.startswith("*/"):
        step = int(token[2:])
        return value % step == 0
    return value == int(token)


def _validate_and_normalize_cron_expr(cron_expr: str) -> str:
    parts = cron_expr.strip().split()
    if len(parts) != 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="cron_expr must contain 5 fields: minute hour day month weekday",
        )
    minute, hour, day, month, weekday = parts
    _parse_field_token(minute, 0, 59)
    _parse_field_token(hour, 0, 23)
    if day != "*" or month != "*" or weekday != "*":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current scheduler supports cron day/month/weekday as '*' only",
        )
    return " ".join([minute, hour, day, month, weekday])


def _next_cron_time(cron_expr: str, base: datetime) -> datetime:
    minute, hour, _, _, _ = cron_expr.split()
    cursor = base.astimezone(timezone.utc).replace(second=0, microsecond=0)
    for _ in range(24 * 60 * 14):
        cursor = cursor + timedelta(minutes=1)
        if _match_cron_token(cursor.minute, minute) and _match_cron_token(cursor.hour, hour):
            return cursor
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to compute next run for cron_expr")


def _dag_to_dict(
    dag: SchedulerDag,
    node_count: int = 0,
    edge_count: int = 0,
    latest_run: SchedulerRun | None = None,
) -> dict[str, Any]:
    return {
        "id": dag.id,
        "project_id": dag.project_id,
        "name": dag.name,
        "description": dag.description,
        "status": dag.status,
        "trigger_mode": dag.trigger_mode,
        "cron_expr": dag.cron_expr,
        "timezone": dag.timezone,
        "dependency_mode": dag.dependency_mode,
        "retry_policy": dag.retry_policy,
        "schedule_config": dag.schedule_config,
        "version": dag.version,
        "node_count": node_count,
        "edge_count": edge_count,
        "last_scheduled_at": dag.last_scheduled_at.isoformat() if dag.last_scheduled_at else None,
        "next_scheduled_at": dag.next_scheduled_at.isoformat() if dag.next_scheduled_at else None,
        "latest_run": _run_to_dict(latest_run) if latest_run else None,
        "created_at": dag.created_at.isoformat(),
        "updated_at": dag.updated_at.isoformat(),
    }


def _node_to_dict(node: SchedulerDagNode, latest_status: str | None = None) -> dict[str, Any]:
    return {
        "id": node.id,
        "dag_id": node.dag_id,
        "project_id": node.project_id,
        "node_key": node.node_key,
        "name": node.name,
        "task_type": node.task_type,
        "input_assets": node.input_assets,
        "output_assets": node.output_assets,
        "logic_description": node.logic_description,
        "config": node.config,
        "position": node.position,
        "is_active": node.is_active,
        "latest_status": latest_status,
        "created_at": node.created_at.isoformat(),
        "updated_at": node.updated_at.isoformat(),
    }


def _edge_to_dict(edge: SchedulerDagEdge, node_key_by_id: dict[int, str]) -> dict[str, Any]:
    return {
        "id": edge.id,
        "dag_id": edge.dag_id,
        "from_node_id": edge.from_node_id,
        "to_node_id": edge.to_node_id,
        "from_node_key": node_key_by_id.get(edge.from_node_id),
        "to_node_key": node_key_by_id.get(edge.to_node_id),
        "condition": edge.condition,
        "created_at": edge.created_at.isoformat(),
        "updated_at": edge.updated_at.isoformat(),
    }


def _run_to_dict(run: SchedulerRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "project_id": run.project_id,
        "dag_id": run.dag_id,
        "status": run.status,
        "trigger_source": run.trigger_source,
        "triggered_by": run.triggered_by,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "duration_ms": run.duration_ms,
        "error_message": run.error_message,
        "summary": run.summary,
        "run_context": run.run_context,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


def _node_run_to_dict(node_run: SchedulerNodeRun, node: SchedulerDagNode | None = None) -> dict[str, Any]:
    return {
        "id": node_run.id,
        "run_id": node_run.run_id,
        "dag_id": node_run.dag_id,
        "node_id": node_run.node_id,
        "node_key": node.node_key if node else None,
        "node_name": node.name if node else None,
        "status": node_run.status,
        "attempt": node_run.attempt,
        "started_at": node_run.started_at.isoformat() if node_run.started_at else None,
        "finished_at": node_run.finished_at.isoformat() if node_run.finished_at else None,
        "duration_ms": node_run.duration_ms,
        "log_summary": node_run.log_summary,
        "error_message": node_run.error_message,
        "upstream_snapshot": node_run.upstream_snapshot,
        "metrics": node_run.metrics,
        "created_at": node_run.created_at.isoformat(),
        "updated_at": node_run.updated_at.isoformat(),
    }


def _build_topological_order(
    nodes: list[SchedulerDagNode],
    edges: list[SchedulerDagEdge],
) -> list[SchedulerDagNode]:
    node_by_id = {node.id: node for node in nodes}
    indegree: dict[int, int] = {node.id: 0 for node in nodes}
    graph: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        if edge.from_node_id not in node_by_id or edge.to_node_id not in node_by_id:
            continue
        graph[edge.from_node_id].append(edge.to_node_id)
        indegree[edge.to_node_id] += 1

    queue = deque(sorted([node_id for node_id, degree in indegree.items() if degree == 0]))
    result_ids: list[int] = []
    while queue:
        node_id = queue.popleft()
        result_ids.append(node_id)
        for target_id in graph[node_id]:
            indegree[target_id] -= 1
            if indegree[target_id] == 0:
                queue.append(target_id)

    if len(result_ids) != len(nodes):
        return sorted(nodes, key=lambda item: item.id)
    return [node_by_id[item] for item in result_ids]


def _build_upstream_node_map(edges: list[SchedulerDagEdge]) -> dict[int, list[int]]:
    upstream: dict[int, list[int]] = defaultdict(list)
    for edge in edges:
        upstream[edge.to_node_id].append(edge.from_node_id)
    return upstream


def _latest_node_runs(node_runs: list[SchedulerNodeRun]) -> dict[int, SchedulerNodeRun]:
    latest: dict[int, SchedulerNodeRun] = {}
    for node_run in node_runs:
        current = latest.get(node_run.node_id)
        if current is None:
            latest[node_run.node_id] = node_run
            continue
        if (node_run.attempt, node_run.id) > (current.attempt, current.id):
            latest[node_run.node_id] = node_run
    return latest


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def _open_or_update_scheduler_alert(
    alert_repo: BaseRepository[Alert],
    dag: SchedulerDag,
    title: str,
    description: str,
) -> None:
    result = await alert_repo.session.execute(
        select(Alert).where(
            and_(
                Alert.project_id == dag.project_id,
                Alert.source_type == "SCHEDULER_DAG",
                Alert.source_id == str(dag.id),
                Alert.status == "OPEN",
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await alert_repo.update(
            existing,
            {
                "severity": "HIGH",
                "title": title,
                "description": description[:1000],
            },
        )
        return
    await alert_repo.create(
        {
            "project_id": dag.project_id,
            "source_type": "SCHEDULER_DAG",
            "source_id": str(dag.id),
            "severity": "HIGH",
            "title": title,
            "description": description[:1000],
            "status": "OPEN",
        }
    )


async def _resolve_scheduler_alert(alert_repo: BaseRepository[Alert], dag: SchedulerDag) -> None:
    result = await alert_repo.session.execute(
        select(Alert).where(
            and_(
                Alert.project_id == dag.project_id,
                Alert.source_type == "SCHEDULER_DAG",
                Alert.source_id == str(dag.id),
                Alert.status == "OPEN",
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        await alert_repo.update(
            existing,
            {"status": "RESOLVED", "resolved_at": datetime.now(timezone.utc)},
        )


def _summarize_from_latest_runs(latest_runs: dict[int, SchedulerNodeRun]) -> tuple[str, dict[str, int]]:
    counts = {"success": 0, "failed": 0, "skipped": 0, "pending": 0, "running": 0, "total": 0}
    for item in latest_runs.values():
        counts["total"] += 1
        if item.status == "SUCCESS":
            counts["success"] += 1
        elif item.status == "FAILED":
            counts["failed"] += 1
        elif item.status == "SKIPPED":
            counts["skipped"] += 1
        elif item.status == "RUNNING":
            counts["running"] += 1
        else:
            counts["pending"] += 1

    if counts["failed"] > 0:
        run_status = "FAILED"
    elif counts["running"] > 0:
        run_status = "RUNNING"
    elif counts["pending"] > 0:
        run_status = "PENDING"
    elif counts["success"] > 0 and counts["skipped"] > 0:
        run_status = "PARTIAL"
    elif counts["success"] > 0:
        run_status = "SUCCESS"
    else:
        run_status = "SKIPPED"
    return run_status, counts


async def _refresh_run_summary(
    run_repo: SchedulerRunRepository,
    node_run_repo: SchedulerNodeRunRepository,
    run: SchedulerRun,
) -> SchedulerRun:
    node_runs = await node_run_repo.get_by_run(run.id)
    latest_runs = _latest_node_runs(node_runs)
    run_status, counts = _summarize_from_latest_runs(latest_runs)

    finished_at = run.finished_at
    duration_ms = run.duration_ms
    if run_status in {"FAILED", "SUCCESS", "PARTIAL", "SKIPPED"}:
        finished_at = datetime.now(timezone.utc)
        if run.started_at:
            duration_ms = int((_as_utc(finished_at) - _as_utc(run.started_at)).total_seconds() * 1000)

    run = await run_repo.update(
        run,
        {
            "status": run_status,
            "finished_at": finished_at,
            "duration_ms": duration_ms,
            "summary": counts,
            "error_message": "One or more task nodes failed" if run_status == "FAILED" else None,
        },
    )
    return run


async def _create_topology(
    dag_id: int,
    project_id: int,
    nodes_input: list[SchedulerDagNodeInput],
    edges_input: list[SchedulerDagEdgeInput],
    node_repo: SchedulerDagNodeRepository,
    edge_repo: SchedulerDagEdgeRepository,
) -> tuple[list[SchedulerDagNode], list[SchedulerDagEdge]]:
    if not nodes_input:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="At least one DAG node is required")

    seen_node_keys: set[str] = set()
    created_nodes: list[SchedulerDagNode] = []
    node_by_key: dict[str, SchedulerDagNode] = {}
    for node in nodes_input:
        normalized_key = node.node_key.strip()
        if normalized_key in seen_node_keys:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Duplicate node_key: {normalized_key}",
            )
        seen_node_keys.add(normalized_key)
        created = await node_repo.create(
            {
                "dag_id": dag_id,
                "project_id": project_id,
                "node_key": normalized_key,
                "name": node.name,
                "task_type": _normalize_task_type(node.task_type),
                "input_assets": node.input_assets,
                "output_assets": node.output_assets,
                "logic_description": node.logic_description,
                "config": node.config,
                "position": node.position,
            }
        )
        created_nodes.append(created)
        node_by_key[normalized_key] = created

    created_edges: list[SchedulerDagEdge] = []
    for edge in edges_input:
        from_node = node_by_key.get(edge.from_node_key.strip())
        to_node = node_by_key.get(edge.to_node_key.strip())
        if not from_node or not to_node:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Edge references unknown node keys: {edge.from_node_key} -> {edge.to_node_key}",
            )
        if from_node.id == to_node.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Self-loop edge is not allowed: {edge.from_node_key}",
            )
        created_edges.append(
            await edge_repo.create(
                {
                    "dag_id": dag_id,
                    "from_node_id": from_node.id,
                    "to_node_id": to_node.id,
                    "condition": edge.condition,
                }
            )
        )
    return created_nodes, created_edges


async def _execute_dag_run(
    *,
    dag: SchedulerDag,
    nodes: list[SchedulerDagNode],
    edges: list[SchedulerDagEdge],
    trigger_source: str,
    triggered_by: str,
    run_context: dict[str, Any],
    forced_node_results: dict[str, str],
    notes: str | None,
    run_repo: SchedulerRunRepository,
    node_run_repo: SchedulerNodeRunRepository,
) -> tuple[SchedulerRun, list[SchedulerNodeRun]]:
    now = datetime.now(timezone.utc)
    run = await run_repo.create(
        {
            "project_id": dag.project_id,
            "dag_id": dag.id,
            "status": "RUNNING",
            "trigger_source": trigger_source.upper(),
            "triggered_by": triggered_by,
            "started_at": now,
            "summary": {"total": len(nodes)},
            "run_context": {"notes": notes, **run_context},
        }
    )

    ordered_nodes = _build_topological_order(nodes, edges)
    upstream_map = _build_upstream_node_map(edges)
    node_by_id = {item.id: item for item in nodes}
    forced_map = {k.strip(): _normalize_node_status(v) for k, v in forced_node_results.items()}
    latest_status_by_node: dict[int, str] = {}

    for index, node in enumerate(ordered_nodes):
        upstream_ids = upstream_map.get(node.id, [])
        upstream_snapshot = {
            node_by_id[item].node_key: latest_status_by_node.get(item, "PENDING")
            for item in upstream_ids
            if item in node_by_id
        }
        should_skip = dag.dependency_mode == "ALL_SUCCESS" and any(
            value == "FAILED" for value in upstream_snapshot.values()
        )

        if should_skip:
            node_status = "SKIPPED"
            error_message = None
            log_summary = "Skipped because upstream dependency failed"
        else:
            forced_status = forced_map.get(node.node_key) or forced_map.get(node.node_key.upper())
            if forced_status:
                node_status = forced_status
            else:
                signal = (run.id * 31 + node.id * 17 + index * 13) % 100
                node_status = "FAILED" if signal < 12 else "SUCCESS"
            error_message = "Task execution failed in scheduler simulation" if node_status == "FAILED" else None
            log_summary = (
                "Task node execution failed under simulation"
                if node_status == "FAILED"
                else "Task node executed successfully"
            )

        started_at = datetime.now(timezone.utc)
        duration_ms = 120 + ((run.id + node.id * 29 + index * 7) % 900)
        finished_at = started_at + timedelta(milliseconds=duration_ms)
        node_run = await node_run_repo.create(
            {
                "run_id": run.id,
                "dag_id": dag.id,
                "node_id": node.id,
                "status": node_status,
                "attempt": 1,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "log_summary": log_summary,
                "error_message": error_message,
                "upstream_snapshot": upstream_snapshot,
                "metrics": {
                    "records": 1000 + ((run.id + node.id * 5) % 3000),
                    "cost_ms": duration_ms,
                },
            }
        )
        latest_status_by_node[node.id] = node_run.status

    run = await _refresh_run_summary(run_repo, node_run_repo, run)
    node_runs = await node_run_repo.get_by_run(run.id)
    return run, node_runs

@router.get("/options")
async def get_scheduler_options(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    assets = await DataAssetRepository(db).get_by_project_filtered(project_id=context.project.id, limit=1000)
    return success_response(
        {
            "task_types": sorted(ALLOWED_TASK_TYPES),
            "assets": [
                {
                    "id": item.id,
                    "name": item.name,
                    "asset_type": item.asset_type,
                    "object_name": item.object_name,
                    "domain": item.domain,
                    "status": item.status,
                }
                for item in assets
            ],
        }
    )


@router.get("/dags")
async def list_dags(
    q: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    trigger_mode: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    edge_repo = SchedulerDagEdgeRepository(db)
    run_repo = SchedulerRunRepository(db)

    rows = await dag_repo.list_by_project_filtered(
        project_id=context.project.id,
        q=q,
        status=_normalize_dag_status(status_filter) if status_filter else None,
        trigger_mode=_normalize_trigger_mode(trigger_mode) if trigger_mode else None,
        limit=limit,
    )

    data = []
    for dag in rows:
        nodes = await node_repo.get_by_dag(dag.id)
        edges = await edge_repo.get_by_dag(dag.id)
        latest_run = await run_repo.get_last_by_dag(dag.id)
        data.append(_dag_to_dict(dag, node_count=len(nodes), edge_count=len(edges), latest_run=latest_run))
    return success_response(data)


@router.post("/dags", status_code=status.HTTP_201_CREATED)
async def create_dag(
    request: SchedulerDagCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    edge_repo = SchedulerDagEdgeRepository(db)
    audit_repo = BaseRepository(AuditLog, db)

    dag_status = _normalize_dag_status(request.status)
    normalized_trigger_mode = _normalize_trigger_mode(request.trigger_mode)
    cron_expr = request.cron_expr
    next_scheduled_at = None
    if normalized_trigger_mode == "CRON":
        if not cron_expr:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cron_expr is required for CRON trigger")
        cron_expr = _validate_and_normalize_cron_expr(cron_expr)
        next_scheduled_at = _next_cron_time(cron_expr, datetime.now(timezone.utc))
    else:
        cron_expr = None

    dag = await dag_repo.create(
        {
            "project_id": context.project.id,
            "name": request.name,
            "description": request.description,
            "status": dag_status,
            "trigger_mode": normalized_trigger_mode,
            "cron_expr": cron_expr,
            "timezone": request.timezone or "UTC",
            "dependency_mode": request.dependency_mode or "ALL_SUCCESS",
            "retry_policy": request.retry_policy,
            "schedule_config": request.schedule_config,
            "next_scheduled_at": next_scheduled_at,
        }
    )
    nodes, edges = await _create_topology(
        dag_id=dag.id,
        project_id=context.project.id,
        nodes_input=request.nodes,
        edges_input=request.edges,
        node_repo=node_repo,
        edge_repo=edge_repo,
    )

    await audit_repo.create(
        {
            "action": "SCHEDULER_DAG_CREATE",
            "entity_type": "SCHEDULER_DAG",
            "entity_id": str(dag.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "name": dag.name,
                    "trigger_mode": dag.trigger_mode,
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(
        _dag_to_dict(dag, node_count=len(nodes), edge_count=len(edges)),
        message="Scheduler DAG created",
        code="SCHEDULER_DAG_CREATED",
    )


@router.patch("/dags/{dag_id}")
async def update_dag(
    dag_id: int,
    request: SchedulerDagUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    edge_repo = SchedulerDagEdgeRepository(db)
    run_repo = SchedulerRunRepository(db)
    audit_repo = BaseRepository(AuditLog, db)

    dag = await dag_repo.get(dag_id)
    if not dag or dag.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler DAG not found")

    patch_data = {key: value for key, value in request.model_dump().items() if value is not None}
    replace_nodes = patch_data.pop("nodes", None)
    replace_edges = patch_data.pop("edges", None)

    if "status" in patch_data:
        patch_data["status"] = _normalize_dag_status(patch_data["status"])
    if "trigger_mode" in patch_data:
        patch_data["trigger_mode"] = _normalize_trigger_mode(patch_data["trigger_mode"])

    trigger_mode_value = patch_data.get("trigger_mode", dag.trigger_mode)
    cron_expr_value = patch_data.get("cron_expr", dag.cron_expr)
    if trigger_mode_value == "CRON":
        if not cron_expr_value:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="cron_expr is required for CRON trigger")
        patch_data["cron_expr"] = _validate_and_normalize_cron_expr(cron_expr_value)
        patch_data["next_scheduled_at"] = _next_cron_time(patch_data["cron_expr"], datetime.now(timezone.utc))
    elif "trigger_mode" in patch_data and patch_data["trigger_mode"] != "CRON":
        patch_data["cron_expr"] = None
        patch_data["next_scheduled_at"] = None

    before_version = dag.version
    metadata_changed = bool(patch_data)
    topology_changed = replace_nodes is not None or replace_edges is not None
    if not metadata_changed and not topology_changed:
        nodes = await node_repo.get_by_dag(dag.id)
        edges = await edge_repo.get_by_dag(dag.id)
        latest_run = await run_repo.get_last_by_dag(dag.id)
        return success_response(
            _dag_to_dict(dag, node_count=len(nodes), edge_count=len(edges), latest_run=latest_run),
            message="No changes detected",
            code="SCHEDULER_DAG_NO_CHANGES",
        )

    if topology_changed:
        existing_runs = await run_repo.get_by_dag(dag.id, limit=1)
        if existing_runs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Topology cannot be replaced after DAG has execution history",
            )

        current_edges = await edge_repo.get_by_dag(dag.id)
        for edge in current_edges:
            await edge_repo.remove(edge.id)
        current_nodes = await node_repo.get_by_dag(dag.id)
        for node in current_nodes:
            await node_repo.remove(node.id)

        new_nodes = replace_nodes if replace_nodes is not None else []
        new_edges = replace_edges if replace_edges is not None else []
        await _create_topology(
            dag_id=dag.id,
            project_id=context.project.id,
            nodes_input=new_nodes,
            edges_input=new_edges,
            node_repo=node_repo,
            edge_repo=edge_repo,
        )

    if metadata_changed or topology_changed:
        patch_data["version"] = _bump_patch_version(dag.version)
        dag = await dag_repo.update(dag, patch_data)

    nodes = await node_repo.get_by_dag(dag.id)
    edges = await edge_repo.get_by_dag(dag.id)
    latest_run = await run_repo.get_last_by_dag(dag.id)
    await audit_repo.create(
        {
            "action": "SCHEDULER_DAG_UPDATE",
            "entity_type": "SCHEDULER_DAG",
            "entity_id": str(dag.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "from_version": before_version,
                    "to_version": dag.version,
                    "metadata_changed": metadata_changed,
                    "topology_changed": topology_changed,
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                },
                ensure_ascii=True,
            ),
        }
    )
    return success_response(
        _dag_to_dict(dag, node_count=len(nodes), edge_count=len(edges), latest_run=latest_run),
        message="Scheduler DAG updated",
        code="SCHEDULER_DAG_UPDATED",
    )


@router.get("/dags/{dag_id}/detail")
async def get_dag_detail(
    dag_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    edge_repo = SchedulerDagEdgeRepository(db)
    run_repo = SchedulerRunRepository(db)
    node_run_repo = SchedulerNodeRunRepository(db)

    dag = await dag_repo.get(dag_id)
    if not dag or dag.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler DAG not found")

    nodes = await node_repo.get_by_dag(dag.id)
    edges = await edge_repo.get_by_dag(dag.id)
    runs = await run_repo.get_by_dag(dag.id, limit=30)
    latest_node_status: dict[int, str] = {}
    if runs:
        latest_node_runs = await node_run_repo.get_by_run(runs[0].id)
        latest_map = _latest_node_runs(latest_node_runs)
        latest_node_status = {node_id: row.status for node_id, row in latest_map.items()}

    node_key_by_id = {item.id: item.node_key for item in nodes}
    return success_response(
        {
            "dag": _dag_to_dict(
                dag,
                node_count=len(nodes),
                edge_count=len(edges),
                latest_run=runs[0] if runs else None,
            ),
            "topology": {
                "nodes": [_node_to_dict(item, latest_status=latest_node_status.get(item.id)) for item in nodes],
                "edges": [_edge_to_dict(item, node_key_by_id=node_key_by_id) for item in edges],
            },
            "schedule": {
                "trigger_mode": dag.trigger_mode,
                "cron_expr": dag.cron_expr,
                "timezone": dag.timezone,
                "dependency_mode": dag.dependency_mode,
                "retry_policy": dag.retry_policy,
                "schedule_config": dag.schedule_config,
                "last_scheduled_at": dag.last_scheduled_at.isoformat() if dag.last_scheduled_at else None,
                "next_scheduled_at": dag.next_scheduled_at.isoformat() if dag.next_scheduled_at else None,
            },
            "recent_runs": [_run_to_dict(item) for item in runs],
        }
    )


@router.get("/dags/{dag_id}/runs")
async def get_dag_runs(
    dag_id: int,
    limit: int = Query(default=50, ge=1, le=500),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    run_repo = SchedulerRunRepository(db)
    dag = await dag_repo.get(dag_id)
    if not dag or dag.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler DAG not found")
    rows = await run_repo.get_by_dag(dag_id, limit=limit)
    return success_response([_run_to_dict(item) for item in rows])

@router.post("/dags/{dag_id}/run")
async def run_dag(
    dag_id: int,
    request: SchedulerRunRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    edge_repo = SchedulerDagEdgeRepository(db)
    run_repo = SchedulerRunRepository(db)
    node_run_repo = SchedulerNodeRunRepository(db)
    alert_repo = BaseRepository(Alert, db)
    audit_repo = BaseRepository(AuditLog, db)

    dag = await dag_repo.get(dag_id)
    if not dag or dag.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler DAG not found")
    if dag.status not in {"ACTIVE", "PAUSED"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"DAG status {dag.status} does not allow execution",
        )

    nodes = await node_repo.get_by_dag(dag.id)
    edges = await edge_repo.get_by_dag(dag.id)
    run, node_runs = await _execute_dag_run(
        dag=dag,
        nodes=nodes,
        edges=edges,
        trigger_source=request.trigger_source,
        triggered_by=context.actor_id,
        run_context=request.run_context,
        forced_node_results=request.forced_node_results,
        notes=request.notes,
        run_repo=run_repo,
        node_run_repo=node_run_repo,
    )

    if run.status == "FAILED":
        await _open_or_update_scheduler_alert(
            alert_repo,
            dag,
            title=f"Scheduler DAG failed: {dag.name}",
            description=f"DAG run {run.id} failed with {run.summary.get('failed', 0)} failed nodes.",
        )
    elif run.status in {"SUCCESS", "PARTIAL", "SKIPPED"}:
        await _resolve_scheduler_alert(alert_repo, dag)

    await audit_repo.create(
        {
            "action": "SCHEDULER_RUN_TRIGGER",
            "entity_type": "SCHEDULER_RUN",
            "entity_id": str(run.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "dag_id": dag.id,
                    "status": run.status,
                    "trigger_source": request.trigger_source.upper(),
                    "summary": run.summary,
                },
                ensure_ascii=True,
            ),
        }
    )

    node_by_id = {item.id: item for item in nodes}
    return success_response(
        {
            "run": _run_to_dict(run),
            "node_runs": [_node_run_to_dict(item, node=node_by_id.get(item.node_id)) for item in node_runs],
        },
        message="Scheduler DAG executed",
        code="SCHEDULER_RUN_EXECUTED",
    )


@router.get("/runs/{run_id}/detail")
async def get_run_detail(
    run_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    run_repo = SchedulerRunRepository(db)
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    node_run_repo = SchedulerNodeRunRepository(db)

    run = await run_repo.get(run_id)
    if not run or run.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler run not found")

    dag = await dag_repo.get(run.dag_id)
    if not dag or dag.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler DAG not found")

    nodes = await node_repo.get_by_dag(dag.id)
    node_by_id = {item.id: item for item in nodes}
    node_runs = await node_run_repo.get_by_run(run.id)
    latest_map = _latest_node_runs(node_runs)
    latest_by_node_key = {
        node_by_id[node_id].node_key: row.status
        for node_id, row in latest_map.items()
        if node_id in node_by_id
    }
    return success_response(
        {
            "dag": _dag_to_dict(dag, node_count=len(nodes), edge_count=0),
            "run": _run_to_dict(run),
            "latest_node_status": latest_by_node_key,
            "node_runs": [_node_run_to_dict(item, node=node_by_id.get(item.node_id)) for item in node_runs],
        }
    )


@router.post("/runs/{run_id}/actions")
async def run_action(
    run_id: int,
    request: SchedulerRunActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    action = _normalize_action(request.action)

    run_repo = SchedulerRunRepository(db)
    node_run_repo = SchedulerNodeRunRepository(db)
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    alert_repo = BaseRepository(Alert, db)
    audit_repo = BaseRepository(AuditLog, db)

    run = await run_repo.get(run_id)
    if not run or run.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler run not found")
    dag = await dag_repo.get(run.dag_id)
    if not dag or dag.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler DAG not found")

    if request.node_run_id is None:
        if action != "RETRY":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="node_run_id is required for SKIP and MARK_SUCCESS actions",
            )
        nodes = await node_repo.get_by_dag(dag.id)
        edges = await SchedulerDagEdgeRepository(db).get_by_dag(dag.id)
        retried_run, retried_node_runs = await _execute_dag_run(
            dag=dag,
            nodes=nodes,
            edges=edges,
            trigger_source="RETRY",
            triggered_by=context.actor_id,
            run_context={"retry_of_run_id": run.id},
            forced_node_results={},
            notes=request.reason,
            run_repo=run_repo,
            node_run_repo=node_run_repo,
        )
        if retried_run.status == "FAILED":
            await _open_or_update_scheduler_alert(
                alert_repo,
                dag,
                title=f"Scheduler DAG failed: {dag.name}",
                description=f"Retried run {retried_run.id} failed",
            )
        else:
            await _resolve_scheduler_alert(alert_repo, dag)
        await audit_repo.create(
            {
                "action": "SCHEDULER_RUN_ACTION",
                "entity_type": "SCHEDULER_RUN",
                "entity_id": str(retried_run.id),
                "user_id": context.actor_id,
                "details": json.dumps(
                    {
                        "action": "RETRY_RUN",
                        "retry_of_run_id": run.id,
                        "status": retried_run.status,
                    },
                    ensure_ascii=True,
                ),
            }
        )
        node_by_id = {item.id: item for item in nodes}
        return success_response(
            {
                "run": _run_to_dict(retried_run),
                "node_runs": [
                    _node_run_to_dict(item, node=node_by_id.get(item.node_id))
                    for item in retried_node_runs
                ],
            },
            message="Scheduler run retried",
            code="SCHEDULER_RUN_RETRIED",
        )

    target_node_run = await node_run_repo.get(request.node_run_id)
    if not target_node_run or target_node_run.run_id != run.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler node run not found")

    target_node = await SchedulerDagNodeRepository(db).get(target_node_run.node_id)
    if not target_node or target_node.dag_id != dag.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scheduler node not found")

    if action == "RETRY":
        next_attempt = target_node_run.attempt + 1
        started_at = datetime.now(timezone.utc)
        duration_ms = 120 + ((run.id + target_node.id * 11 + next_attempt * 7) % 400)
        finished_at = started_at + timedelta(milliseconds=duration_ms)
        await node_run_repo.create(
            {
                "run_id": run.id,
                "dag_id": dag.id,
                "node_id": target_node.id,
                "status": "SUCCESS",
                "attempt": next_attempt,
                "started_at": started_at,
                "finished_at": finished_at,
                "duration_ms": duration_ms,
                "log_summary": f"Manual retry succeeded. {request.reason or ''}".strip(),
                "error_message": None,
                "upstream_snapshot": target_node_run.upstream_snapshot,
                "metrics": {"records": 1000 + ((run.id + target_node.id * 3) % 2500), "cost_ms": duration_ms},
            }
        )
    elif action == "SKIP":
        await node_run_repo.update(
            target_node_run,
            {
                "status": "SKIPPED",
                "finished_at": datetime.now(timezone.utc),
                "error_message": None,
                "log_summary": f"Marked as skipped. {request.reason or ''}".strip(),
            },
        )
    elif action == "MARK_SUCCESS":
        await node_run_repo.update(
            target_node_run,
            {
                "status": "SUCCESS",
                "finished_at": datetime.now(timezone.utc),
                "error_message": None,
                "log_summary": f"Marked as success. {request.reason or ''}".strip(),
            },
        )

    run = await _refresh_run_summary(run_repo, node_run_repo, run)
    if run.status == "FAILED":
        await _open_or_update_scheduler_alert(
            alert_repo,
            dag,
            title=f"Scheduler DAG failed: {dag.name}",
            description=f"Run {run.id} remains failed after manual action.",
        )
    else:
        await _resolve_scheduler_alert(alert_repo, dag)

    await audit_repo.create(
        {
            "action": "SCHEDULER_RUN_ACTION",
            "entity_type": "SCHEDULER_RUN",
            "entity_id": str(run.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "action": action,
                    "node_run_id": target_node_run.id,
                    "reason": request.reason,
                    "run_status": run.status,
                },
                ensure_ascii=True,
            ),
        }
    )

    nodes = await node_repo.get_by_dag(dag.id)
    node_by_id = {item.id: item for item in nodes}
    node_runs = await node_run_repo.get_by_run(run.id)
    return success_response(
        {
            "run": _run_to_dict(run),
            "node_runs": [_node_run_to_dict(item, node=node_by_id.get(item.node_id)) for item in node_runs],
        },
        message="Scheduler run action applied",
        code="SCHEDULER_RUN_ACTION_APPLIED",
    )


@router.post("/engine/tick")
async def scheduler_engine_tick(
    request: SchedulerEngineTickRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    dag_repo = SchedulerDagRepository(db)
    node_repo = SchedulerDagNodeRepository(db)
    edge_repo = SchedulerDagEdgeRepository(db)
    run_repo = SchedulerRunRepository(db)
    node_run_repo = SchedulerNodeRunRepository(db)
    alert_repo = BaseRepository(Alert, db)
    audit_repo = BaseRepository(AuditLog, db)

    dags = await dag_repo.list_by_project_filtered(
        project_id=context.project.id,
        status="ACTIVE",
        trigger_mode="CRON",
        limit=request.limit,
    )
    now = datetime.now(timezone.utc)
    executed: list[dict[str, Any]] = []

    for dag in dags:
        if not dag.cron_expr:
            continue
        due = request.run_immediately
        if not due:
            if dag.next_scheduled_at is None:
                due = True
            elif dag.next_scheduled_at <= now:
                due = True
        if not due:
            continue

        nodes = await node_repo.get_by_dag(dag.id)
        edges = await edge_repo.get_by_dag(dag.id)
        run, _ = await _execute_dag_run(
            dag=dag,
            nodes=nodes,
            edges=edges,
            trigger_source="SCHEDULER",
            triggered_by=context.actor_id,
            run_context={"engine_tick": True},
            forced_node_results={},
            notes="Triggered by scheduler engine tick",
            run_repo=run_repo,
            node_run_repo=node_run_repo,
        )
        dag = await dag_repo.update(
            dag,
            {
                "last_scheduled_at": now,
                "next_scheduled_at": _next_cron_time(dag.cron_expr, now),
            },
        )
        if run.status == "FAILED":
            await _open_or_update_scheduler_alert(
                alert_repo,
                dag,
                title=f"Scheduler DAG failed: {dag.name}",
                description=f"Engine tick run {run.id} failed",
            )
        else:
            await _resolve_scheduler_alert(alert_repo, dag)
        executed.append(
            {
                "dag_id": dag.id,
                "run_id": run.id,
                "status": run.status,
                "next_scheduled_at": dag.next_scheduled_at.isoformat() if dag.next_scheduled_at else None,
            }
        )

    await audit_repo.create(
        {
            "action": "SCHEDULER_ENGINE_TICK",
            "entity_type": "SCHEDULER_ENGINE",
            "entity_id": str(context.project.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "executed_count": len(executed),
                    "run_immediately": request.run_immediately,
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(
        {
            "executed_count": len(executed),
            "executed_runs": executed,
        },
        message="Scheduler engine tick completed",
        code="SCHEDULER_ENGINE_TICK_OK",
    )
