from collections import defaultdict
from datetime import datetime, timezone
from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.config import settings
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.models.scheduler_dag_node import SchedulerDagNode
from src.infrastructure.database.models.scheduler_run import SchedulerRun
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _normalize_environment(raw_value: str | None) -> str:
    normalized = (raw_value or "").strip().lower()
    alias_map = {
        "development": "dev",
        "develop": "dev",
        "dev": "dev",
        "staging": "staging",
        "stage": "staging",
        "prod": "prod",
        "production": "prod",
        "test": "test",
        "testing": "test",
    }
    if normalized in alias_map:
        return alias_map[normalized]
    return normalized or "dev"


def _project_default_environment(context: RequestContext) -> str:
    tech_stack = context.project.tech_stack if isinstance(context.project.tech_stack, dict) else {}
    return _normalize_environment(
        str(tech_stack.get("environment") or tech_stack.get("env") or settings.ENVIRONMENT.value)
    )


def _pipeline_environment(pipeline: Pipeline, default_environment: str) -> str:
    config = pipeline.config if isinstance(pipeline.config, dict) else {}
    for key in ["environment", "env", "deploy_env", "runtime_environment"]:
        value = config.get(key)
        if value:
            return _normalize_environment(str(value))
    return default_environment


def _pipeline_cluster(pipeline: Pipeline, plane: str, environment: str) -> str:
    config = pipeline.config if isinstance(pipeline.config, dict) else {}
    if plane == "kafka":
        candidates = ["kafka_cluster", "kafka_cluster_id", "cluster", "cluster_id"]
        fallback = f"kafka-{environment}"
    else:
        candidates = ["flink_cluster", "flink_cluster_id", "cluster", "cluster_id"]
        fallback = f"flink-{environment}"
    for key in candidates:
        value = config.get(key)
        if value:
            return str(value)
    return fallback


def _storage_cluster(asset: DataAsset, environment: str) -> str:
    schema_definition = asset.schema_definition if isinstance(asset.schema_definition, dict) else {}
    for key in ["cluster", "cluster_id", "storage_cluster"]:
        value = schema_definition.get(key)
        if value:
            return str(value)
    return f"{(asset.source_system or 'storage').lower()}-{environment}"


def _asset_environment(asset: DataAsset, default_environment: str) -> str:
    schema_definition = asset.schema_definition if isinstance(asset.schema_definition, dict) else {}
    for key in ["environment", "env"]:
        value = schema_definition.get(key)
        if value:
            return _normalize_environment(str(value))
    for tag in asset.tags or []:
        normalized_tag = _normalize_environment(str(tag))
        if normalized_tag in {"dev", "staging", "prod", "test"}:
            return normalized_tag
    return default_environment


def _safe_int(raw_value: Any, fallback: int) -> int:
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return fallback


def _pipeline_flink_state(pipeline: Pipeline) -> str:
    config = pipeline.config if isinstance(pipeline.config, dict) else {}
    raw_state = str(config.get("flink_state") or "").strip().upper()
    if raw_state:
        return raw_state
    status_to_flink_state = {
        "RUNNING": "RUNNING",
        "FAILED": "FAILED",
        "ROLLING_BACK": "FAILING",
        "STOPPED": "CANCELED",
        "PROVISIONING": "CREATED",
        "PENDING": "CREATED",
    }
    return status_to_flink_state.get(pipeline.status, "UNKNOWN")


def _asset_estimated_used_gb(asset: DataAsset) -> float:
    schema = asset.schema_definition if isinstance(asset.schema_definition, dict) else {}
    columns = schema.get("columns", [])
    column_count = len(columns) if isinstance(columns, list) else 0
    base_by_type = {
        "TABLE": 12.0,
        "TOPIC": 6.0,
        "VIEW": 3.0,
        "METRIC": 1.5,
    }
    base = base_by_type.get(asset.asset_type, 4.0)
    column_factor = max(1.0, column_count * 0.9)
    status_factor = {
        "ACTIVE": 1.0,
        "DRAFT": 0.55,
        "DEPRECATED": 0.35,
    }.get(asset.status, 0.8)
    return round(base * column_factor * status_factor, 2)


def _matches_filter(
    *,
    target_environment: str,
    target_cluster: str | None,
    selected_environment: str | None,
    selected_cluster: str | None,
) -> bool:
    if selected_environment and target_environment != selected_environment:
        return False
    if selected_cluster and target_cluster != selected_cluster:
        return False
    return True


@router.get("/overview")
async def get_infrastructure_overview(
    environment: str | None = Query(default=None),
    cluster: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    selected_environment = _normalize_environment(environment) if environment else None
    selected_cluster = cluster.strip() if cluster else None
    default_environment = _project_default_environment(context)

    pipelines_result = await db.execute(select(Pipeline).where(Pipeline.project_id == context.project.id))
    pipelines = list(pipelines_result.scalars().all())

    assets_result = await db.execute(select(DataAsset).where(DataAsset.project_id == context.project.id))
    assets = list(assets_result.scalars().all())

    alerts_result = await db.execute(
        select(Alert).where(
            Alert.project_id == context.project.id,
            Alert.status == "OPEN",
        )
    )
    open_alerts = list(alerts_result.scalars().all())

    dags_result = await db.execute(select(SchedulerDag).where(SchedulerDag.project_id == context.project.id))
    dags = list(dags_result.scalars().all())
    dag_by_id = {dag.id: dag for dag in dags}

    dag_nodes_result = await db.execute(select(SchedulerDagNode).where(SchedulerDagNode.project_id == context.project.id))
    dag_nodes = list(dag_nodes_result.scalars().all())

    runs_result = await db.execute(select(SchedulerRun).where(SchedulerRun.project_id == context.project.id))
    runs = list(runs_result.scalars().all())

    latest_run_by_dag: dict[int, SchedulerRun] = {}
    for run in runs:
        existing = latest_run_by_dag.get(run.dag_id)
        if existing is None or run.started_at > existing.started_at:
            latest_run_by_dag[run.dag_id] = run

    pipeline_by_id = {pipeline.id: pipeline for pipeline in pipelines}
    topic_asset_by_name = {
        asset.object_name: asset
        for asset in assets
        if asset.asset_type == "TOPIC"
    }

    alerts_by_pipeline_id: dict[int, list[Alert]] = defaultdict(list)
    for alert in open_alerts:
        if alert.source_type != "PIPELINE":
            continue
        try:
            pipeline_id = int(alert.source_id)
        except ValueError:
            continue
        alerts_by_pipeline_id[pipeline_id].append(alert)

    dag_ids_by_pipeline_id: dict[int, set[int]] = defaultdict(set)
    for node in dag_nodes:
        node_tokens = set()
        for token in (node.input_assets or []):
            if token:
                node_tokens.add(str(token))
        for token in (node.output_assets or []):
            if token:
                node_tokens.add(str(token))
        if not node_tokens:
            continue
        for pipeline in pipelines:
            if pipeline.topic_name in node_tokens or pipeline.flink_job_name in node_tokens:
                dag_ids_by_pipeline_id[pipeline.id].add(node.dag_id)
                continue
            for token in node_tokens:
                if pipeline.event_code in token:
                    dag_ids_by_pipeline_id[pipeline.id].add(node.dag_id)
                    break

    environments_set = {default_environment}
    clusters_set: set[str] = set()
    for pipeline in pipelines:
        pipeline_env = _pipeline_environment(pipeline, default_environment)
        environments_set.add(pipeline_env)
        clusters_set.add(_pipeline_cluster(pipeline, "kafka", pipeline_env))
        clusters_set.add(_pipeline_cluster(pipeline, "flink", pipeline_env))
    for asset in assets:
        asset_env = _asset_environment(asset, default_environment)
        environments_set.add(asset_env)
        clusters_set.add(_storage_cluster(asset, asset_env))

    kafka_topics = []
    for pipeline in pipelines:
        pipeline_environment = _pipeline_environment(pipeline, default_environment)
        kafka_cluster_id = _pipeline_cluster(pipeline, "kafka", pipeline_environment)
        if not _matches_filter(
            target_environment=pipeline_environment,
            target_cluster=kafka_cluster_id,
            selected_environment=selected_environment,
            selected_cluster=selected_cluster,
        ):
            continue

        config = pipeline.config if isinstance(pipeline.config, dict) else {}
        partitions = _safe_int(config.get("partitions"), 6)
        replication_factor = _safe_int(config.get("replication_factor"), 3)
        retention_hours = _safe_int(config.get("retention_hours"), 168)
        alert_count = len(alerts_by_pipeline_id.get(pipeline.id, []))
        backlog_multiplier = {
            "FAILED": 4.0,
            "ROLLING_BACK": 3.5,
            "PROVISIONING": 2.0,
            "PENDING": 1.5,
            "RUNNING": 1.0,
            "STOPPED": 0.6,
        }.get(pipeline.status, 1.2)
        backlog_estimate = int(max(0, partitions * 120 * backlog_multiplier + pipeline.retry_count * 80 + alert_count * 160))
        topic_asset = topic_asset_by_name.get(pipeline.topic_name)

        kafka_topics.append(
            {
                "pipeline_id": pipeline.id,
                "topic_name": pipeline.topic_name,
                "event_code": pipeline.event_code,
                "status": pipeline.status,
                "environment": pipeline_environment,
                "cluster_id": kafka_cluster_id,
                "partitions": partitions,
                "replication_factor": replication_factor,
                "retention_hours": retention_hours,
                "estimated_backlog": backlog_estimate,
                "alert_count": alert_count,
                "catalog_asset_id": topic_asset.id if topic_asset else None,
                "links": {
                    "pipelines": "/pipelines",
                    "catalog": "/catalog",
                    "explore_prefill": f"/explore?source_type=PIPELINE&source_id={pipeline.id}",
                },
            }
        )

    kafka_clusters = []
    kafka_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for topic in kafka_topics:
        kafka_grouped[(topic["environment"], topic["cluster_id"])].append(topic)

    for (group_environment, group_cluster_id), topics in sorted(kafka_grouped.items(), key=lambda item: item[0]):
        topic_count = len(topics)
        failed_topics = len([topic for topic in topics if topic["status"] in {"FAILED", "ROLLING_BACK"}])
        warning_count = sum(topic["alert_count"] for topic in topics)
        broker_count = max(3, min(12, topic_count + 2))
        healthy_brokers = max(1, broker_count - failed_topics)
        failure_ratio = failed_topics / topic_count if topic_count else 0
        if failure_ratio >= 0.35:
            health_status = "CRITICAL"
        elif failure_ratio >= 0.15 or warning_count > topic_count:
            health_status = "DEGRADED"
        else:
            health_status = "HEALTHY"

        kafka_clusters.append(
            {
                "cluster_id": group_cluster_id,
                "environment": group_environment,
                "health_status": health_status,
                "version": "3.6.1",
                "controller": f"{group_cluster_id}-controller-1",
                "broker_count": broker_count,
                "healthy_brokers": healthy_brokers,
                "topic_count": topic_count,
                "warning_count": warning_count,
            }
        )

    flink_jobs = []
    for pipeline in pipelines:
        pipeline_environment = _pipeline_environment(pipeline, default_environment)
        flink_cluster_id = _pipeline_cluster(pipeline, "flink", pipeline_environment)
        if not _matches_filter(
            target_environment=pipeline_environment,
            target_cluster=flink_cluster_id,
            selected_environment=selected_environment,
            selected_cluster=selected_cluster,
        ):
            continue

        config = pipeline.config if isinstance(pipeline.config, dict) else {}
        job_id = str(config.get("flink_job_id") or f"job-{pipeline.id}")
        flink_state = _pipeline_flink_state(pipeline)
        alert_count = len(alerts_by_pipeline_id.get(pipeline.id, []))
        dag_ids = sorted(dag_ids_by_pipeline_id.get(pipeline.id, []))
        latest_scheduler_state = None
        if dag_ids:
            latest_scheduler_runs = [
                latest_run_by_dag[dag_id]
                for dag_id in dag_ids
                if dag_id in latest_run_by_dag
            ]
            if latest_scheduler_runs:
                latest_scheduler_state = sorted(
                    latest_scheduler_runs,
                    key=lambda item: item.started_at,
                    reverse=True,
                )[0].status

        flink_jobs.append(
            {
                "pipeline_id": pipeline.id,
                "job_name": pipeline.flink_job_name,
                "job_id": job_id,
                "state": flink_state,
                "pipeline_status": pipeline.status,
                "event_code": pipeline.event_code,
                "environment": pipeline_environment,
                "cluster_id": flink_cluster_id,
                "retry_count": pipeline.retry_count,
                "last_sync_at": _to_iso(pipeline.last_sync_at),
                "alert_count": alert_count,
                "scheduler_dag_ids": dag_ids,
                "latest_scheduler_state": latest_scheduler_state,
                "links": {
                    "pipelines": "/pipelines",
                    "scheduler": "/scheduler",
                    "explore_prefill": f"/explore?source_type=PIPELINE&source_id={pipeline.id}",
                },
            }
        )

    flink_clusters = []
    flink_grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for job in flink_jobs:
        flink_grouped[(job["environment"], job["cluster_id"])].append(job)

    for (group_environment, group_cluster_id), jobs in sorted(flink_grouped.items(), key=lambda item: item[0]):
        job_count = len(jobs)
        running_jobs = len([job for job in jobs if job["state"] in {"RUNNING", "DEPLOYED"}])
        failed_jobs = len([job for job in jobs if job["state"] in {"FAILED", "FAILING", "CANCELED"}])
        provisioning_jobs = len([job for job in jobs if job["state"] in {"CREATED", "INITIALIZING"}])
        taskmanagers_total = max(1, ceil(job_count / 2))
        taskmanagers_healthy = max(0, taskmanagers_total - failed_jobs)
        slots_total = max(4, taskmanagers_total * 4)
        slots_used = min(slots_total, running_jobs * 2 + provisioning_jobs)
        failed_ratio = failed_jobs / job_count if job_count else 0
        if failed_ratio >= 0.35:
            checkpoint_health = "CRITICAL"
        elif failed_ratio >= 0.15:
            checkpoint_health = "DEGRADED"
        else:
            checkpoint_health = "HEALTHY"
        if failed_ratio >= 0.35:
            health_status = "CRITICAL"
        elif failed_ratio >= 0.15:
            health_status = "DEGRADED"
        else:
            health_status = "HEALTHY"

        flink_clusters.append(
            {
                "cluster_id": group_cluster_id,
                "environment": group_environment,
                "health_status": health_status,
                "version": "1.18.1",
                "taskmanagers_total": taskmanagers_total,
                "taskmanagers_healthy": taskmanagers_healthy,
                "slots_total": slots_total,
                "slots_used": slots_used,
                "checkpoint_health": checkpoint_health,
                "job_count": job_count,
            }
        )

    storage_systems = []
    storage_key_paths = []

    system_groups: dict[tuple[str, str, str], list[DataAsset]] = defaultdict(list)
    key_path_groups: dict[tuple[str, str, str, str], list[DataAsset]] = defaultdict(list)
    for asset in assets:
        asset_environment = _asset_environment(asset, default_environment)
        system_cluster = _storage_cluster(asset, asset_environment)
        if not _matches_filter(
            target_environment=asset_environment,
            target_cluster=system_cluster,
            selected_environment=selected_environment,
            selected_cluster=selected_cluster,
        ):
            continue
        source_system = asset.source_system or "unknown"
        database_name = asset.database_name or "(default)"
        system_groups[(source_system, asset_environment, system_cluster)].append(asset)
        key_path_groups[(source_system, database_name, asset_environment, system_cluster)].append(asset)

    for (source_system, group_environment, group_cluster_id), group_assets in sorted(system_groups.items(), key=lambda item: item[0]):
        used_gb = round(sum(_asset_estimated_used_gb(asset) for asset in group_assets), 2)
        capacity_gb = round(max(20.0, used_gb * 2.4 + 30.0), 2)
        usage_rate = round(used_gb / capacity_gb if capacity_gb else 0.0, 4)
        storage_systems.append(
            {
                "source_system": source_system,
                "environment": group_environment,
                "cluster_id": group_cluster_id,
                "asset_count": len(group_assets),
                "used_gb": used_gb,
                "capacity_gb": capacity_gb,
                "usage_rate": usage_rate,
            }
        )

    topic_to_pipeline = {pipeline.topic_name: pipeline for pipeline in pipelines}
    for (source_system, database_name, group_environment, group_cluster_id), group_assets in sorted(
        key_path_groups.items(), key=lambda item: item[0]
    ):
        path = f"{source_system}.{database_name}"
        used_gb = round(sum(_asset_estimated_used_gb(asset) for asset in group_assets), 2)
        capacity_gb = round(max(8.0, used_gb * 2.1 + 10.0), 2)
        usage_rate = round(used_gb / capacity_gb if capacity_gb else 0.0, 4)

        related_pipeline_alerts = 0
        for asset in group_assets:
            if asset.asset_type != "TOPIC":
                continue
            pipeline = topic_to_pipeline.get(asset.object_name)
            if pipeline:
                related_pipeline_alerts += len(alerts_by_pipeline_id.get(pipeline.id, []))

        if usage_rate >= 0.85 or related_pipeline_alerts > 0:
            hot_level = "HIGH"
        elif usage_rate >= 0.65:
            hot_level = "MEDIUM"
        else:
            hot_level = "LOW"

        sample_assets = [
            {
                "id": asset.id,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "object_name": asset.object_name,
            }
            for asset in group_assets[:3]
        ]

        first_asset_id = group_assets[0].id if group_assets else None
        storage_key_paths.append(
            {
                "path": path,
                "source_system": source_system,
                "database_name": database_name,
                "environment": group_environment,
                "cluster_id": group_cluster_id,
                "asset_count": len(group_assets),
                "used_gb": used_gb,
                "capacity_gb": capacity_gb,
                "usage_rate": usage_rate,
                "hot_level": hot_level,
                "related_pipeline_alert_count": related_pipeline_alerts,
                "sample_assets": sample_assets,
                "links": {
                    "catalog": "/catalog",
                    "explore_prefill": (
                        f"/explore?source_type=DATA_ASSET&source_id={first_asset_id}"
                        if first_asset_id is not None
                        else None
                    ),
                },
            }
        )

    total_storage_capacity = round(sum(item["capacity_gb"] for item in storage_systems), 2)
    total_storage_used = round(sum(item["used_gb"] for item in storage_systems), 2)
    storage_usage_rate = round(total_storage_used / total_storage_capacity if total_storage_capacity else 0.0, 4)

    filtered_alerts = []
    for alert in open_alerts:
        alert_environment = default_environment
        alert_cluster = None
        if alert.source_type == "PIPELINE":
            try:
                pipeline_id = int(alert.source_id)
            except ValueError:
                continue
            pipeline = pipeline_by_id.get(pipeline_id)
            if pipeline is None:
                continue
            alert_environment = _pipeline_environment(pipeline, default_environment)
            alert_cluster = _pipeline_cluster(pipeline, "kafka", alert_environment)

        if not _matches_filter(
            target_environment=alert_environment,
            target_cluster=alert_cluster,
            selected_environment=selected_environment,
            selected_cluster=selected_cluster,
        ):
            continue

        links = {
            "pipelines": "/pipelines" if alert.source_type == "PIPELINE" else None,
            "data_quality": "/data-quality" if alert.source_type == "DATA_QUALITY_RULE" else None,
            "scheduler": "/scheduler" if alert.source_type == "SCHEDULER_DAG" else None,
            "explore_prefill": None,
        }
        if alert.source_type in {"PIPELINE", "DATA_QUALITY_RULE", "SCHEDULER_DAG"}:
            links["explore_prefill"] = f"/explore?source_type={alert.source_type}&source_id={alert.source_id}"

        filtered_alerts.append(
            {
                "id": alert.id,
                "source_type": alert.source_type,
                "source_id": alert.source_id,
                "severity": alert.severity,
                "status": alert.status,
                "title": alert.title,
                "description": alert.description,
                "environment": alert_environment,
                "cluster_id": alert_cluster,
                "created_at": _to_iso(alert.created_at),
                "links": links,
            }
        )

    filtered_alerts = sorted(filtered_alerts, key=lambda item: item["created_at"], reverse=True)

    alerts_by_source = defaultdict(int)
    for alert in filtered_alerts:
        alerts_by_source[alert["source_type"]] += 1

    kafka_totals = {
        "topic_count": len(kafka_topics),
        "running_topics": len([topic for topic in kafka_topics if topic["status"] == "RUNNING"]),
        "failed_topics": len([topic for topic in kafka_topics if topic["status"] in {"FAILED", "ROLLING_BACK"}]),
        "open_alerts": sum(topic["alert_count"] for topic in kafka_topics),
        "estimated_backlog": int(sum(topic["estimated_backlog"] for topic in kafka_topics)),
    }
    flink_totals = {
        "job_count": len(flink_jobs),
        "running_jobs": len([job for job in flink_jobs if job["state"] in {"RUNNING", "DEPLOYED"}]),
        "failed_jobs": len([job for job in flink_jobs if job["state"] in {"FAILED", "FAILING", "CANCELED"}]),
        "open_alerts": sum(job["alert_count"] for job in flink_jobs),
    }

    data = {
        "filters": {
            "selected_environment": selected_environment,
            "selected_cluster": selected_cluster,
            "available_environments": sorted(environments_set),
            "available_clusters": sorted(clusters_set),
        },
        "summary": {
            "kafka_clusters": len(kafka_clusters),
            "kafka_topics": len(kafka_topics),
            "flink_clusters": len(flink_clusters),
            "flink_jobs": len(flink_jobs),
            "storage_systems": len(storage_systems),
            "open_alerts": len(filtered_alerts),
        },
        "kafka": {
            "clusters": kafka_clusters,
            "topics": sorted(kafka_topics, key=lambda item: (item["status"] != "FAILED", item["topic_name"])),
            "totals": kafka_totals,
        },
        "flink": {
            "clusters": flink_clusters,
            "jobs": sorted(flink_jobs, key=lambda item: (item["state"] != "FAILED", item["job_name"])),
            "totals": flink_totals,
        },
        "storage": {
            "overview": {
                "capacity_total_gb": total_storage_capacity,
                "used_gb": total_storage_used,
                "usage_rate": storage_usage_rate,
                "hot_path_count": len([path for path in storage_key_paths if path["hot_level"] == "HIGH"]),
            },
            "systems": sorted(storage_systems, key=lambda item: item["source_system"]),
            "key_paths": sorted(storage_key_paths, key=lambda item: (item["hot_level"] != "HIGH", item["path"])),
        },
        "alerts": {
            "open_count": len(filtered_alerts),
            "critical_count": len([alert for alert in filtered_alerts if str(alert["severity"]).upper() == "CRITICAL"]),
            "high_count": len([alert for alert in filtered_alerts if str(alert["severity"]).upper() == "HIGH"]),
            "by_source": [
                {"source_type": source_type, "count": count}
                for source_type, count in sorted(alerts_by_source.items(), key=lambda item: item[0])
            ],
            "recent": filtered_alerts[:20],
        },
        "collected_at": datetime.now(timezone.utc).isoformat(),
    }

    await BaseRepository(AuditLog, db).create(
        {
            "action": "INFRA_OVERVIEW_VIEW",
            "entity_type": "INFRASTRUCTURE",
            "entity_id": str(context.project.id),
            "user_id": context.actor_id,
            "details": (
                f"environment={selected_environment or 'ALL'};"
                f"cluster={selected_cluster or 'ALL'};"
                f"kafka_topics={len(kafka_topics)};"
                f"flink_jobs={len(flink_jobs)};"
                f"alerts={len(filtered_alerts)}"
            ),
        }
    )

    return success_response(data)
