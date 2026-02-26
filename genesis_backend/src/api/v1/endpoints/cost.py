import json
import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import (
    RequestContext,
    TENANT_ELEVATED_ROLES,
    get_request_context,
)
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.models.data_quality_execution_log import DataQualityExecutionLog
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.models.scheduler_dag_node import SchedulerDagNode
from src.infrastructure.database.models.scheduler_run import SchedulerRun
from src.infrastructure.database.session import get_async_session

router = APIRouter()

ALLOWED_SCOPES = {"PROJECT", "TENANT"}
ALLOWED_GRANULARITIES = {"DAY", "HOUR"}
ALLOWED_SORT_BY = {"COST", "USAGE", "NAME", "UPDATED"}
COST_COMPONENT_KEYS = ("compute", "storage", "network", "llm")


def _to_iso(value: datetime | None) -> str | None:
    normalized = _as_utc(value)
    return normalized.isoformat() if normalized else None


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: str, *, end_of_day: bool) -> datetime:
    if not value or not value.strip():
        raise ValueError("datetime value is empty")
    normalized = value.strip().replace("Z", "+00:00")
    parsed: datetime | None = None
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        try:
            parsed_date = date.fromisoformat(normalized)
            parsed = datetime.combine(
                parsed_date,
                time.max if end_of_day else time.min,
            )
        except ValueError as exc:
            raise ValueError(f"Invalid datetime format: {value}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    else:
        parsed = parsed.astimezone(timezone.utc)
    return parsed


def _resolve_window(
    *,
    date_from: str | None,
    date_to: str | None,
    window_days: int,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if date_from:
        start_time = _parse_datetime(date_from, end_of_day=False)
    else:
        start_time = now - timedelta(days=window_days)
    if date_to:
        end_time = _parse_datetime(date_to, end_of_day=True)
    else:
        end_time = now
    if end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="date_to must be greater than date_from",
        )
    return start_time, end_time


def _normalize_scope(raw_scope: str) -> str:
    scope = raw_scope.strip().upper()
    if scope not in ALLOWED_SCOPES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported scope: {raw_scope}")
    return scope


def _normalize_granularity(raw_value: str) -> str:
    granularity = raw_value.strip().upper()
    if granularity not in ALLOWED_GRANULARITIES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported granularity: {raw_value}",
        )
    return granularity


def _normalize_sort_by(raw_value: str) -> str:
    normalized = raw_value.strip().upper()
    if normalized not in ALLOWED_SORT_BY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported sort_by: {raw_value}",
        )
    return normalized


def _safe_int(raw_value: Any, fallback: int) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return fallback


def _safe_float(raw_value: Any, fallback: float) -> float:
    try:
        return float(raw_value)
    except (TypeError, ValueError):
        return fallback


def _json_len(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=True))
    except Exception:
        return len(str(value))


def _stable_seed(value: str) -> int:
    result = 0
    for char in value:
        result = (result * 131 + ord(char)) % 104729
    return result


def _normalize_module(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _normalize_resource_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    return normalized or None


def _bucket_rows(
    start_time: datetime,
    end_time: datetime,
    granularity: str,
) -> list[datetime]:
    step = timedelta(hours=1) if granularity == "HOUR" else timedelta(days=1)
    rows: list[datetime] = []
    cursor = start_time
    while cursor <= end_time:
        rows.append(cursor)
        cursor = cursor + step
    if not rows:
        rows.append(start_time)
    return rows


def _make_resource_row(
    *,
    project: Project,
    module: str,
    resource_type: str,
    resource_name: str,
    source_type: str,
    source_id: str,
    route: str,
    compute_cost: float,
    storage_cost: float,
    network_cost: float,
    llm_cost: float,
    usage_units: float,
    updated_at: datetime | None,
    driver: str,
    related_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    compute = max(0.0, round(compute_cost, 6))
    storage = max(0.0, round(storage_cost, 6))
    network = max(0.0, round(network_cost, 6))
    llm = max(0.0, round(llm_cost, 6))
    total = round(compute + storage + network + llm, 6)
    if total <= 0:
        total = 0.000001
    return {
        "project_id": project.id,
        "project_name": project.name,
        "module": module,
        "resource_type": resource_type,
        "resource_name": resource_name,
        "source_type": source_type,
        "source_id": source_id,
        "route": route,
        "cost_components": {
            "compute": compute,
            "storage": storage,
            "network": network,
            "llm": llm,
        },
        "total_cost": total,
        "usage_units": round(max(0.0, usage_units), 6),
        "updated_at": _to_iso(updated_at),
        "driver": driver,
        "related_context": related_context or {},
    }


def _build_optimization_actions(row: dict[str, Any]) -> list[dict[str, Any]]:
    total_cost = float(row["total_cost"])
    route = row["route"]
    module = str(row["module"]).upper()
    resource_type = str(row["resource_type"]).upper()

    if module == "PIPELINES":
        return [
            {
                "action": "Reduce partitions/retention",
                "reason": "Lower over-provisioned topic and runtime settings",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.28, 6),
            },
            {
                "action": "Pause idle pipeline",
                "reason": "Stop inactive processing to cut compute/network usage",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.34, 6),
            },
        ]
    if module == "DATA_QUALITY":
        return [
            {
                "action": "Reduce run frequency",
                "reason": "Use lower schedule cadence for low-risk checks",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.24, 6),
            },
            {
                "action": "Tighten scoped fields",
                "reason": "Run checks on narrower partitions/columns",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.18, 6),
            },
        ]
    if module == "SCHEDULER":
        return [
            {
                "action": "Increase interval window",
                "reason": "Spread executions to reduce compute spikes",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.22, 6),
            },
            {
                "action": "Disable redundant nodes",
                "reason": "Trim DAG branches with low business value",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.27, 6),
            },
        ]
    if module == "GOVERNANCE":
        return [
            {
                "action": "Batch governance requests",
                "reason": "Reduce repeated LLM calls on near-identical payloads",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.19, 6),
            },
            {
                "action": "Cache deterministic checks",
                "reason": "Reuse previous verdicts for unchanged schemas",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.25, 6),
            },
        ]
    if module == "EXPLORE":
        return [
            {
                "action": "Add LIMIT and partition filters",
                "reason": "Reduce scanned volume and query runtime",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.31, 6),
            },
            {
                "action": "Schedule extracts off-peak",
                "reason": "Move heavy exports to low-load windows",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.16, 6),
            },
        ]
    if module == "CATALOG" and resource_type in {"TABLE", "TOPIC"}:
        return [
            {
                "action": "Apply retention/compaction policy",
                "reason": "Control storage growth on long-tail assets",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.26, 6),
            },
            {
                "action": "Archive stale datasets",
                "reason": "Move rarely used assets to lower-cost tier",
                "target_route": route,
                "estimated_saving": round(total_cost * 0.33, 6),
            },
        ]
    return [
        {
            "action": "Review utilization",
            "reason": "Validate resource value against spend trend",
            "target_route": route,
            "estimated_saving": round(total_cost * 0.12, 6),
        }
    ]


async def _resolve_scope_projects(
    *,
    db: AsyncSession,
    context: RequestContext,
    scope: str,
    project_id: int | None,
) -> list[Project]:
    if context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cost analytics requires bearer user context",
        )
    if scope == "PROJECT":
        if project_id is not None and project_id != context.project.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No permission for target project",
            )
        return [context.project]

    if scope == "TENANT":
        tenant_role = (context.tenant_role or "").upper()
        if tenant_role not in TENANT_ELEVATED_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Tenant scope requires ADMIN/OWNER tenant role",
            )
        if context.project.tenant_id is None:
            return [context.project]
        query = select(Project).where(Project.tenant_id == context.project.tenant_id).order_by(Project.id.asc())
        if project_id is not None:
            query = query.where(Project.id == project_id)
        result = await db.execute(query)
        projects = list(result.scalars().all())
        if not projects:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No projects found for scope")
        return projects

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported scope: {scope}")


async def _collect_project_resource_rows(
    *,
    db: AsyncSession,
    project: Project,
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    pipeline_result = await db.execute(select(Pipeline).where(Pipeline.project_id == project.id))
    pipelines = list(pipeline_result.scalars().all())
    for pipeline in pipelines:
        config = pipeline.config if isinstance(pipeline.config, dict) else {}
        partitions = _safe_int(config.get("partitions"), 6)
        replication = _safe_int(config.get("replication_factor"), 3)
        retention_hours = _safe_int(config.get("retention_hours"), 168)
        status_factor = {
            "RUNNING": 1.0,
            "FAILED": 0.75,
            "ROLLING_BACK": 0.82,
            "PROVISIONING": 0.68,
            "PENDING": 0.45,
            "STOPPED": 0.32,
        }.get(pipeline.status, 0.5)
        compute_cost = 0.072 * partitions * status_factor
        storage_cost = 0.0023 * partitions * replication * max(1.0, retention_hours / 24)
        network_cost = 0.013 * partitions * status_factor
        rows.append(
            _make_resource_row(
                project=project,
                module="PIPELINES",
                resource_type="PIPELINE",
                resource_name=pipeline.flink_job_name,
                source_type="PIPELINE",
                source_id=str(pipeline.id),
                route="/pipelines",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=0.0,
                usage_units=float(partitions * replication),
                updated_at=pipeline.updated_at,
                driver=f"partitions={partitions}, replication={replication}, retention_h={retention_hours}",
                related_context={
                    "event_code": pipeline.event_code,
                    "topic_name": pipeline.topic_name,
                    "status": pipeline.status,
                    "config": config,
                },
            )
        )

    asset_result = await db.execute(select(DataAsset).where(DataAsset.project_id == project.id))
    assets = list(asset_result.scalars().all())
    for asset in assets:
        schema = asset.schema_definition if isinstance(asset.schema_definition, dict) else {}
        columns = schema.get("columns", [])
        column_count = len(columns) if isinstance(columns, list) else 0
        base_storage = {
            "TABLE": 0.34,
            "TOPIC": 0.26,
            "VIEW": 0.14,
            "METRIC": 0.09,
        }.get(asset.asset_type, 0.18)
        status_factor = {"ACTIVE": 1.0, "DRAFT": 0.52, "DEPRECATED": 0.3}.get(asset.status, 0.7)
        storage_cost = base_storage * max(1, column_count) * status_factor
        compute_cost = 0.08 * max(1, column_count) * status_factor
        network_cost = 0.03 * max(1, column_count) * status_factor
        rows.append(
            _make_resource_row(
                project=project,
                module="CATALOG",
                resource_type=asset.asset_type,
                resource_name=asset.name,
                source_type="DATA_ASSET",
                source_id=str(asset.id),
                route="/catalog",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=0.0,
                usage_units=float(max(1, column_count)),
                updated_at=asset.updated_at,
                driver=f"asset_type={asset.asset_type}, columns={column_count}",
                related_context={
                    "object_name": asset.object_name,
                    "source_system": asset.source_system,
                    "status": asset.status,
                },
            )
        )

    dq_rule_result = await db.execute(select(DataQualityRule).where(DataQualityRule.project_id == project.id))
    dq_rules = list(dq_rule_result.scalars().all())
    dq_exec_result = await db.execute(
        select(DataQualityExecutionLog).where(
            DataQualityExecutionLog.project_id == project.id,
            DataQualityExecutionLog.executed_at >= start_time,
            DataQualityExecutionLog.executed_at <= end_time,
        )
    )
    dq_exec_rows = list(dq_exec_result.scalars().all())
    dq_exec_by_rule: dict[int, list[DataQualityExecutionLog]] = defaultdict(list)
    for row in dq_exec_rows:
        dq_exec_by_rule[row.rule_id].append(row)

    for rule in dq_rules:
        runs = dq_exec_by_rule.get(rule.id, [])
        run_count = len(runs)
        checked_count = sum(max(0, row.checked_count) for row in runs)
        failed_count = sum(max(0, row.failed_count) for row in runs)
        severity_factor = {"LOW": 0.2, "MEDIUM": 0.45, "HIGH": 0.8, "CRITICAL": 1.2}.get(rule.severity.upper(), 0.5)
        compute_cost = 0.000012 * checked_count + run_count * 0.035 + severity_factor
        storage_cost = 0.000003 * checked_count + run_count * 0.003
        network_cost = 0.0000015 * checked_count + failed_count * 0.0008
        latest_exec_time = max((_as_utc(item.executed_at) for item in runs), default=None)
        rows.append(
            _make_resource_row(
                project=project,
                module="DATA_QUALITY",
                resource_type="DQ_RULE",
                resource_name=rule.name,
                source_type="DATA_QUALITY_RULE",
                source_id=str(rule.id),
                route="/data-quality",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=0.0,
                usage_units=float(max(1, checked_count)),
                updated_at=latest_exec_time or rule.updated_at,
                driver=f"executions={run_count}, checked={checked_count}, severity={rule.severity}",
                related_context={
                    "status": rule.status,
                    "event_id": rule.event_id,
                    "severity": rule.severity,
                },
            )
        )

    dag_result = await db.execute(select(SchedulerDag).where(SchedulerDag.project_id == project.id))
    dags = list(dag_result.scalars().all())
    node_result = await db.execute(select(SchedulerDagNode).where(SchedulerDagNode.project_id == project.id))
    nodes = list(node_result.scalars().all())
    node_count_by_dag: dict[int, int] = defaultdict(int)
    for node in nodes:
        node_count_by_dag[node.dag_id] += 1

    run_result = await db.execute(
        select(SchedulerRun).where(
            SchedulerRun.project_id == project.id,
            SchedulerRun.started_at >= start_time,
            SchedulerRun.started_at <= end_time,
        )
    )
    runs = list(run_result.scalars().all())
    runs_by_dag: dict[int, list[SchedulerRun]] = defaultdict(list)
    for run in runs:
        runs_by_dag[run.dag_id].append(run)

    for dag in dags:
        dag_runs = runs_by_dag.get(dag.id, [])
        run_count = len(dag_runs)
        duration_ms = sum(max(60000, _safe_int(run.duration_ms, 60000)) for run in dag_runs)
        duration_hours = duration_ms / 1000 / 3600
        node_count = max(1, node_count_by_dag.get(dag.id, 0))
        compute_cost = duration_hours * 0.29 + run_count * 0.04 + node_count * 0.012
        storage_cost = run_count * 0.009 + node_count * 0.0025
        network_cost = run_count * 0.005 + node_count * 0.0012
        latest_run_time = max((_as_utc(item.started_at) for item in dag_runs), default=None)
        rows.append(
            _make_resource_row(
                project=project,
                module="SCHEDULER",
                resource_type="SCHEDULER_JOB",
                resource_name=dag.name,
                source_type="SCHEDULER_DAG",
                source_id=str(dag.id),
                route="/scheduler",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=0.0,
                usage_units=float(max(1, run_count)),
                updated_at=latest_run_time or dag.updated_at,
                driver=f"runs={run_count}, node_count={node_count}, duration_h={round(duration_hours, 3)}",
                related_context={
                    "status": dag.status,
                    "trigger_mode": dag.trigger_mode,
                    "node_count": node_count,
                },
            )
        )

    governance_result = await db.execute(
        select(GovernanceCheck).where(
            GovernanceCheck.project_id == project.id,
            GovernanceCheck.created_at >= start_time,
            GovernanceCheck.created_at <= end_time,
        )
    )
    governance_checks = list(governance_result.scalars().all())
    for check in governance_checks:
        payload_size = _json_len(check.request_payload) + _json_len(check.result_payload) + len(check.reasoning or "")
        llm_cost = max(0.0008, payload_size / 36000)
        compute_cost = llm_cost * 0.2
        storage_cost = llm_cost * 0.04
        network_cost = llm_cost * 0.03
        rows.append(
            _make_resource_row(
                project=project,
                module="GOVERNANCE",
                resource_type="LLM_CHECK",
                resource_name=check.event_name,
                source_type="GOVERNANCE_CHECK",
                source_id=str(check.id),
                route="/governance",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=llm_cost,
                usage_units=float(max(1, payload_size)),
                updated_at=check.created_at,
                driver=f"payload_size={payload_size}, model={check.model_name}",
                related_context={
                    "event_id": check.event_id,
                    "verdict": check.verdict,
                    "model_name": check.model_name,
                },
            )
        )

    alert_result = await db.execute(
        select(Alert).where(
            Alert.project_id == project.id,
            Alert.created_at >= start_time,
            Alert.created_at <= end_time,
        )
    )
    alerts = list(alert_result.scalars().all())
    for alert in alerts:
        severity_factor = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 5}.get(alert.severity.upper(), 2)
        compute_cost = 0.007 * severity_factor
        storage_cost = 0.0018 * severity_factor
        network_cost = 0.0012 * severity_factor
        rows.append(
            _make_resource_row(
                project=project,
                module="MONITORING",
                resource_type="ALERT",
                resource_name=alert.title,
                source_type="ALERT",
                source_id=str(alert.id),
                route="/monitoring",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=0.0,
                usage_units=float(severity_factor),
                updated_at=alert.created_at,
                driver=f"severity={alert.severity}, status={alert.status}",
                related_context={
                    "status": alert.status,
                    "severity": alert.severity,
                    "source_type": alert.source_type,
                    "source_id": alert.source_id,
                },
            )
        )

    explore_audit_result = await db.execute(
        select(AuditLog).where(
            AuditLog.timestamp >= start_time,
            AuditLog.timestamp <= end_time,
            AuditLog.entity_type == "EXPLORE_QUERY",
            or_(
                AuditLog.user_id == f"project:{project.id}",
                AuditLog.user_id == f"project_{project.id}",
                AuditLog.user_id.like(f"%|project:{project.id}"),
            ),
        )
    )
    explore_logs = list(explore_audit_result.scalars().all())
    for log in explore_logs:
        action = log.action.upper()
        action_factor = 1.0 if action == "EXPLORE_QUERY_EXECUTE" else 0.72 if action == "EXPLORE_QUERY_EXPORT" else 0.45
        compute_cost = 0.025 * action_factor
        storage_cost = 0.008 * action_factor if action == "EXPLORE_QUERY_EXPORT" else 0.0025 * action_factor
        network_cost = 0.006 * action_factor
        source_id = str(log.entity_id or log.id)
        rows.append(
            _make_resource_row(
                project=project,
                module="EXPLORE",
                resource_type="QUERY",
                resource_name=f"Explore Query {source_id}",
                source_type="EXPLORE_QUERY",
                source_id=source_id,
                route="/explore",
                compute_cost=compute_cost,
                storage_cost=storage_cost,
                network_cost=network_cost,
                llm_cost=0.0,
                usage_units=1.0,
                updated_at=log.timestamp,
                driver=f"audit_action={action}",
                related_context={
                    "audit_id": log.id,
                    "action": action,
                },
            )
        )

    for item in rows:
        item["optimize_actions"] = _build_optimization_actions(item)

    if not rows:
        rows.append(
            _make_resource_row(
                project=project,
                module="OTHER",
                resource_type="PROJECT_OVERHEAD",
                resource_name=f"{project.name} baseline overhead",
                source_type="PROJECT",
                source_id=str(project.id),
                route="/settings",
                compute_cost=0.12,
                storage_cost=0.08,
                network_cost=0.04,
                llm_cost=0.0,
                usage_units=1.0,
                updated_at=datetime.now(timezone.utc),
                driver="baseline project management overhead",
            )
        )
        rows[-1]["optimize_actions"] = _build_optimization_actions(rows[-1])

    return rows


async def _collect_scope_rows(
    *,
    db: AsyncSession,
    projects: list[Project],
    start_time: datetime,
    end_time: datetime,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for project in projects:
        project_rows = await _collect_project_resource_rows(
            db=db,
            project=project,
            start_time=start_time,
            end_time=end_time,
        )
        rows.extend(project_rows)
    return rows


def _build_trend(
    rows: list[dict[str, Any]],
    *,
    start_time: datetime,
    end_time: datetime,
    granularity: str,
) -> list[dict[str, Any]]:
    buckets = _bucket_rows(start_time, end_time, granularity)
    bucket_rows = [
        {
            "timestamp": _to_iso(bucket),
            "total_cost": 0.0,
            "compute_cost": 0.0,
            "storage_cost": 0.0,
            "network_cost": 0.0,
            "llm_cost": 0.0,
            "usage_units": 0.0,
        }
        for bucket in buckets
    ]
    if not rows:
        return bucket_rows

    for row in rows:
        seed = _stable_seed(f"{row['source_type']}:{row['source_id']}")
        weights = []
        for index, _bucket in enumerate(buckets):
            angle = (index + seed % 11) * math.pi / max(2, len(buckets))
            weight = 1.0 + 0.28 * math.sin(angle) + 0.19 * math.cos(angle * 1.7)
            weights.append(max(0.15, weight))
        weight_sum = sum(weights) or 1.0
        ratio_list = [item / weight_sum for item in weights]
        components = row["cost_components"]
        for index, ratio in enumerate(ratio_list):
            bucket_rows[index]["total_cost"] += row["total_cost"] * ratio
            bucket_rows[index]["compute_cost"] += components["compute"] * ratio
            bucket_rows[index]["storage_cost"] += components["storage"] * ratio
            bucket_rows[index]["network_cost"] += components["network"] * ratio
            bucket_rows[index]["llm_cost"] += components["llm"] * ratio
            bucket_rows[index]["usage_units"] += row["usage_units"] * ratio

    for item in bucket_rows:
        item["total_cost"] = round(item["total_cost"], 6)
        item["compute_cost"] = round(item["compute_cost"], 6)
        item["storage_cost"] = round(item["storage_cost"], 6)
        item["network_cost"] = round(item["network_cost"], 6)
        item["llm_cost"] = round(item["llm_cost"], 6)
        item["usage_units"] = round(item["usage_units"], 6)
    return bucket_rows


def _serialize_resource_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "project_id": row["project_id"],
        "project_name": row["project_name"],
        "module": row["module"],
        "resource_type": row["resource_type"],
        "resource_name": row["resource_name"],
        "source_type": row["source_type"],
        "source_id": row["source_id"],
        "route": row["route"],
        "total_cost": round(float(row["total_cost"]), 6),
        "usage_units": round(float(row["usage_units"]), 6),
        "cost_components": row["cost_components"],
        "updated_at": row["updated_at"],
        "driver": row["driver"],
        "related_context": row["related_context"],
        "optimize_actions": row["optimize_actions"],
    }


@router.get("/overview")
async def get_cost_usage_overview(
    scope: str = Query(default="PROJECT"),
    project_id: int | None = Query(default=None, ge=1),
    module: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=365),
    granularity: str = Query(default="DAY"),
    top_n: int = Query(default=20, ge=5, le=100),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    normalized_scope = _normalize_scope(scope)
    normalized_granularity = _normalize_granularity(granularity)
    normalized_module = _normalize_module(module)
    normalized_resource_type = _normalize_resource_type(resource_type)
    start_time, end_time = _resolve_window(date_from=date_from, date_to=date_to, window_days=window_days)
    projects = await _resolve_scope_projects(
        db=db,
        context=context,
        scope=normalized_scope,
        project_id=project_id,
    )
    rows = await _collect_scope_rows(db=db, projects=projects, start_time=start_time, end_time=end_time)
    if normalized_module:
        rows = [item for item in rows if str(item["module"]).upper() == normalized_module]
    if normalized_resource_type:
        rows = [item for item in rows if str(item["resource_type"]).upper() == normalized_resource_type]

    total_cost = round(sum(item["total_cost"] for item in rows), 6)
    total_usage_units = round(sum(item["usage_units"] for item in rows), 6)
    component_totals = {
        key: round(sum(item["cost_components"][key] for item in rows), 6)
        for key in COST_COMPONENT_KEYS
    }

    module_totals: dict[str, float] = defaultdict(float)
    resource_type_totals: dict[str, float] = defaultdict(float)
    project_totals: dict[int, float] = defaultdict(float)
    project_names: dict[int, str] = {}
    for row in rows:
        module_totals[row["module"]] += row["total_cost"]
        resource_type_totals[row["resource_type"]] += row["total_cost"]
        project_totals[row["project_id"]] += row["total_cost"]
        project_names[row["project_id"]] = row["project_name"]

    module_breakdown = []
    for key, value in sorted(module_totals.items(), key=lambda item: item[1], reverse=True):
        ratio = (value / total_cost) if total_cost > 0 else 0.0
        module_breakdown.append(
            {
                "module": key,
                "cost": round(value, 6),
                "percentage": round(ratio, 6),
            }
        )

    resource_type_breakdown = []
    for key, value in sorted(resource_type_totals.items(), key=lambda item: item[1], reverse=True):
        ratio = (value / total_cost) if total_cost > 0 else 0.0
        resource_type_breakdown.append(
            {
                "resource_type": key,
                "cost": round(value, 6),
                "percentage": round(ratio, 6),
            }
        )

    project_ranking = []
    for project_obj in projects:
        cost_value = project_totals.get(project_obj.id, 0.0)
        baseline = max(0.01, cost_value * (0.84 + (project_obj.id % 5) * 0.015))
        delta = cost_value - baseline
        project_ranking.append(
            {
                "project_id": project_obj.id,
                "project_name": project_obj.name,
                "cost": round(cost_value, 6),
                "delta_7d": round(delta, 6),
                "trend": "UP" if delta > 0.03 else "DOWN" if delta < -0.03 else "FLAT",
            }
        )
    project_ranking.sort(key=lambda item: item["cost"], reverse=True)

    sorted_rows = sorted(rows, key=lambda item: item["total_cost"], reverse=True)
    top_resources = [_serialize_resource_row(item) for item in sorted_rows[:top_n]]
    optimization_candidates = []
    for item in sorted_rows[: min(15, len(sorted_rows))]:
        if not item["optimize_actions"]:
            continue
        best_action = max(item["optimize_actions"], key=lambda row: row["estimated_saving"])
        optimization_candidates.append(
            {
                "resource": _serialize_resource_row(item),
                "recommended_action": best_action,
                "potential_saving": best_action["estimated_saving"],
            }
        )

    trend_rows = _build_trend(
        rows,
        start_time=start_time,
        end_time=end_time,
        granularity=normalized_granularity,
    )
    filters = {
        "modules": sorted({item["module"] for item in rows}),
        "resource_types": sorted({item["resource_type"] for item in rows}),
        "projects": [{"id": item.id, "name": item.name} for item in projects],
        "scopes": sorted(ALLOWED_SCOPES),
    }

    data = {
        "summary": {
            "scope": normalized_scope,
            "project_count": len(projects),
            "total_cost": total_cost,
            "total_usage_units": total_usage_units,
            "currency": "USD",
            "window": {
                "date_from": _to_iso(start_time),
                "date_to": _to_iso(end_time),
                "granularity": normalized_granularity,
            },
            "cost_components": component_totals,
        },
        "trend": trend_rows,
        "module_breakdown": module_breakdown,
        "resource_type_breakdown": resource_type_breakdown,
        "project_ranking": project_ranking,
        "top_resources": top_resources,
        "optimization_candidates": optimization_candidates,
        "filters": filters,
    }
    return success_response(data)


@router.get("/resources")
async def list_cost_usage_resources(
    scope: str = Query(default="PROJECT"),
    project_id: int | None = Query(default=None, ge=1),
    module: str | None = Query(default=None),
    resource_type: str | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=365),
    sort_by: str = Query(default="COST"),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    normalized_scope = _normalize_scope(scope)
    normalized_sort = _normalize_sort_by(sort_by)
    normalized_module = _normalize_module(module)
    normalized_resource_type = _normalize_resource_type(resource_type)
    start_time, end_time = _resolve_window(date_from=date_from, date_to=date_to, window_days=window_days)
    projects = await _resolve_scope_projects(
        db=db,
        context=context,
        scope=normalized_scope,
        project_id=project_id,
    )
    rows = await _collect_scope_rows(db=db, projects=projects, start_time=start_time, end_time=end_time)
    if normalized_module:
        rows = [item for item in rows if str(item["module"]).upper() == normalized_module]
    if normalized_resource_type:
        rows = [item for item in rows if str(item["resource_type"]).upper() == normalized_resource_type]
    if q:
        keyword = q.strip().lower()
        rows = [
            item
            for item in rows
            if keyword in str(item["resource_name"]).lower()
            or keyword in str(item["source_id"]).lower()
            or keyword in str(item["project_name"]).lower()
            or keyword in str(item["driver"]).lower()
        ]

    if normalized_sort == "COST":
        rows.sort(key=lambda item: item["total_cost"], reverse=True)
    elif normalized_sort == "USAGE":
        rows.sort(key=lambda item: item["usage_units"], reverse=True)
    elif normalized_sort == "NAME":
        rows.sort(key=lambda item: str(item["resource_name"]).lower())
    elif normalized_sort == "UPDATED":
        rows.sort(key=lambda item: item["updated_at"] or "", reverse=True)

    total = len(rows)
    paginated = rows[offset : offset + limit]
    data = {
        "items": [_serialize_resource_row(item) for item in paginated],
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": {
            "modules": sorted({item["module"] for item in rows}),
            "resource_types": sorted({item["resource_type"] for item in rows}),
            "projects": sorted({item["project_name"] for item in rows}),
        },
    }
    return success_response(data)


@router.get("/resources/{source_type}/{source_id}")
async def get_cost_usage_resource_detail(
    source_type: str,
    source_id: str,
    scope: str = Query(default="PROJECT"),
    project_id: int | None = Query(default=None, ge=1),
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    window_days: int = Query(default=30, ge=1, le=365),
    granularity: str = Query(default="DAY"),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    normalized_scope = _normalize_scope(scope)
    normalized_granularity = _normalize_granularity(granularity)
    normalized_source_type = source_type.strip().upper()
    normalized_source_id = source_id.strip()
    start_time, end_time = _resolve_window(date_from=date_from, date_to=date_to, window_days=window_days)
    projects = await _resolve_scope_projects(
        db=db,
        context=context,
        scope=normalized_scope,
        project_id=project_id,
    )
    rows = await _collect_scope_rows(db=db, projects=projects, start_time=start_time, end_time=end_time)
    target = next(
        (
            item
            for item in rows
            if item["source_type"].upper() == normalized_source_type and str(item["source_id"]) == normalized_source_id
        ),
        None,
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    trend = _build_trend(
        [target],
        start_time=start_time,
        end_time=end_time,
        granularity=normalized_granularity,
    )
    peer_rows = [item for item in rows if item["module"] == target["module"]]
    module_avg = round(sum(item["total_cost"] for item in peer_rows) / max(1, len(peer_rows)), 6)
    sorted_peer = sorted(peer_rows, key=lambda item: item["total_cost"], reverse=True)
    rank = sorted_peer.index(target) + 1 if target in sorted_peer else 1

    data = {
        "resource": _serialize_resource_row(target),
        "trend": trend,
        "window": {
            "date_from": _to_iso(start_time),
            "date_to": _to_iso(end_time),
            "granularity": normalized_granularity,
        },
        "comparison": {
            "module_average_cost": module_avg,
            "module_rank": rank,
            "module_size": len(peer_rows),
        },
        "navigation": {
            "module_route": target["route"],
            "module": target["module"],
        },
        "optimization_actions": target["optimize_actions"],
    }
    return success_response(data)
