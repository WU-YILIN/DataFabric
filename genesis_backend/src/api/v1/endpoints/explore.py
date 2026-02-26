import csv
import io
import json
import math
import re
import sqlite3
import time
from collections import defaultdict
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.models.scheduler_run import SchedulerRun
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.data_asset_repo import DataAssetRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

READ_ONLY_SQL_RE = re.compile(r"^\s*(SELECT|WITH|EXPLAIN)\b", re.IGNORECASE | re.DOTALL)
FORBIDDEN_SQL_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|PRAGMA|VACUUM)\b",
    re.IGNORECASE,
)
MAX_SQL_LENGTH = 20000


class ExploreQueryRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=MAX_SQL_LENGTH)
    page: int = Field(default=1, ge=1, le=10000)
    page_size: int = Field(default=50, ge=1, le=500)


class ExploreExportRequest(BaseModel):
    sql: str = Field(..., min_length=1, max_length=MAX_SQL_LENGTH)
    format: str = Field(default="csv", min_length=3, max_length=8)


def _quote_ident(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _sanitize_identifier(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", value.strip())
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        normalized = "col"
    if normalized[0].isdigit():
        normalized = f"c_{normalized}"
    return normalized.lower()


def _ensure_utc_iso(dt) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def _normalize_sqlite_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=True)
    return str(value)


def _infer_sqlite_type(values: list[Any]) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, bool):
            return "INTEGER"
        if isinstance(value, int):
            return "INTEGER"
        if isinstance(value, float):
            return "REAL"
        return "TEXT"
    return "TEXT"


def _create_and_fill_table(
    conn: sqlite3.Connection,
    table_name: str,
    rows: list[dict[str, Any]],
    fallback_columns: list[str] | None = None,
) -> None:
    columns = list(fallback_columns or [])
    for row in rows:
        for key in row.keys():
            if key not in columns:
                columns.append(key)
    if not columns:
        columns = ["id"]

    normalized_rows = [
        {column: _normalize_sqlite_value(row.get(column)) for column in columns}
        for row in rows
    ]
    column_types = {
        column: _infer_sqlite_type([row.get(column) for row in normalized_rows])
        for column in columns
    }

    create_columns = ", ".join(
        f"{_quote_ident(column)} {column_types[column]}" for column in columns
    )
    conn.execute(f'CREATE TABLE {_quote_ident(table_name)} ({create_columns})')

    if normalized_rows:
        placeholders = ", ".join(["?"] * len(columns))
        insert_sql = (
            f'INSERT INTO {_quote_ident(table_name)} '
            f'({", ".join(_quote_ident(col) for col in columns)}) VALUES ({placeholders})'
        )
        conn.executemany(
            insert_sql,
            [tuple(row.get(column) for column in columns) for row in normalized_rows],
        )


def _asset_virtual_table_name(asset: DataAsset) -> str:
    return f"asset_{asset.id}"


def _asset_columns(asset: DataAsset) -> list[dict[str, Any]]:
    schema = asset.schema_definition if isinstance(asset.schema_definition, dict) else {}
    raw_columns = schema.get("columns", [])
    columns: list[dict[str, Any]] = []
    used_query_names: set[str] = set()

    if isinstance(raw_columns, list):
        for index, raw_column in enumerate(raw_columns):
            if not isinstance(raw_column, dict):
                continue
            raw_name = str(raw_column.get("name") or f"column_{index + 1}")
            query_name = _sanitize_identifier(raw_name)
            suffix = 2
            while query_name in used_query_names:
                query_name = f"{_sanitize_identifier(raw_name)}_{suffix}"
                suffix += 1
            used_query_names.add(query_name)
            columns.append(
                {
                    "name": raw_name,
                    "query_name": query_name,
                    "type": str(raw_column.get("type") or "string"),
                    "required": bool(raw_column.get("required", False)),
                    "description": raw_column.get("description"),
                }
            )

    if not columns:
        columns = [
            {
                "name": "value",
                "query_name": "value",
                "type": "string",
                "required": False,
                "description": None,
            }
        ]
    return columns


def _sample_value(column_type: str, row_index: int, col_index: int, query_name: str) -> Any:
    normalized = column_type.lower()
    if any(token in normalized for token in ["int", "long", "number"]):
        return row_index * 10 + col_index + 1
    if any(token in normalized for token in ["float", "double", "decimal"]):
        return round((row_index + 1) * 1.25 + col_index * 0.1, 4)
    if "bool" in normalized:
        return int((row_index + col_index) % 2 == 0)
    if "date" in normalized or "time" in normalized:
        return f"2026-01-{(row_index % 28) + 1:02d}T00:00:00Z"
    return f"{query_name}_{row_index + 1}"


def _asset_sample_rows(columns: list[dict[str, Any]], sample_size: int = 8) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row_index in range(sample_size):
        row: dict[str, Any] = {}
        for col_index, column in enumerate(columns):
            row[column["query_name"]] = _sample_value(
                column_type=column["type"],
                row_index=row_index,
                col_index=col_index,
                query_name=column["query_name"],
            )
        rows.append(row)
    return rows


def _validate_sql(sql: str) -> str:
    trimmed = sql.strip()
    if not trimmed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SQL cannot be empty")
    if len(trimmed) > MAX_SQL_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SQL exceeds max length")
    if not READ_ONLY_SQL_RE.search(trimmed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only read-only SELECT/WITH/EXPLAIN SQL is allowed",
        )
    if FORBIDDEN_SQL_RE.search(trimmed):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only read-only SQL is supported; mutating statements are blocked",
        )
    statement_count = len([part for part in trimmed.split(";") if part.strip()])
    if statement_count > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple SQL statements are not supported",
        )
    if ";" in trimmed and not trimmed.endswith(";"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Multiple SQL statements are not supported",
        )
    normalized = trimmed.rstrip(";")
    return normalized


def _parse_resource_id(raw_source_id: str, source_type: str) -> int:
    try:
        return int(raw_source_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"source_id must be an integer for {source_type}",
        ) from exc


async def _ensure_project_resource_exists(
    db: AsyncSession,
    model,
    project_id: int,
    resource_id: int,
    not_found_message: str,
) -> None:
    query = select(model).where(model.id == resource_id, model.project_id == project_id)
    result = await db.execute(query)
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_message)


async def _load_project_assets(
    db: AsyncSession,
    project_id: int,
    source_system: str | None = None,
) -> list[DataAsset]:
    return await DataAssetRepository(db).get_by_project_filtered(
        project_id=project_id,
        source_system=source_system,
        limit=2000,
    )


async def _build_snapshot(
    db: AsyncSession,
    context: RequestContext,
) -> tuple[sqlite3.Connection, dict[int, dict[str, Any]]]:
    project_id = context.project.id
    assets = await _load_project_assets(db, project_id)
    asset_meta: dict[int, dict[str, Any]] = {}

    for asset in assets:
        columns = _asset_columns(asset)
        sample_rows = _asset_sample_rows(columns)
        asset_meta[asset.id] = {
            "asset": asset,
            "virtual_table": _asset_virtual_table_name(asset),
            "columns": columns,
            "sample_rows": sample_rows,
        }

    events_result = await db.execute(
        select(TrackingEvent).where(TrackingEvent.project_id == project_id).limit(2000)
    )
    event_rows = list(events_result.scalars().all())
    events_data = [
        {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "description": item.description,
            "domain": item.domain,
            "status": item.status,
            "owner": item.owner,
            "governance_status": item.governance_status,
            "created_at": _ensure_utc_iso(item.created_at),
            "updated_at": _ensure_utc_iso(item.updated_at),
        }
        for item in event_rows
    ]

    governance_result = await db.execute(
        select(GovernanceCheck).where(GovernanceCheck.project_id == project_id).limit(2000)
    )
    governance_rows = list(governance_result.scalars().all())
    governance_data = [
        {
            "id": item.id,
            "event_name": item.event_name,
            "verdict": item.verdict,
            "score": item.score,
            "reasoning": item.reasoning,
            "actor_id": item.actor_id,
            "created_at": _ensure_utc_iso(item.created_at),
        }
        for item in governance_rows
    ]

    pipelines_result = await db.execute(
        select(Pipeline).where(Pipeline.project_id == project_id).limit(2000)
    )
    pipeline_rows = list(pipelines_result.scalars().all())
    pipelines_data = [
        {
            "id": item.id,
            "event_code": item.event_code,
            "topic_name": item.topic_name,
            "flink_job_name": item.flink_job_name,
            "status": item.status,
            "retry_count": item.retry_count,
            "error_message": item.error_message,
            "updated_at": _ensure_utc_iso(item.updated_at),
        }
        for item in pipeline_rows
    ]

    dq_result = await db.execute(
        select(DataQualityRule).where(DataQualityRule.project_id == project_id).limit(2000)
    )
    dq_rows = list(dq_result.scalars().all())
    dq_data = [
        {
            "id": item.id,
            "asset_id": item.asset_id,
            "event_id": item.event_id,
            "name": item.name,
            "rule_type": item.rule_type,
            "severity": item.severity,
            "status": item.status,
            "version": item.version,
            "updated_at": _ensure_utc_iso(item.updated_at),
        }
        for item in dq_rows
    ]

    alerts_result = await db.execute(
        select(Alert).where(Alert.project_id == project_id).limit(2000)
    )
    alert_rows = list(alerts_result.scalars().all())
    alerts_data = [
        {
            "id": item.id,
            "source_type": item.source_type,
            "source_id": item.source_id,
            "severity": item.severity,
            "title": item.title,
            "status": item.status,
            "created_at": _ensure_utc_iso(item.created_at),
            "resolved_at": _ensure_utc_iso(item.resolved_at),
        }
        for item in alert_rows
    ]

    dags_result = await db.execute(
        select(SchedulerDag).where(SchedulerDag.project_id == project_id).limit(2000)
    )
    dag_rows = list(dags_result.scalars().all())
    dags_data = [
        {
            "id": item.id,
            "name": item.name,
            "status": item.status,
            "trigger_mode": item.trigger_mode,
            "cron_expr": item.cron_expr,
            "version": item.version,
            "updated_at": _ensure_utc_iso(item.updated_at),
        }
        for item in dag_rows
    ]

    runs_result = await db.execute(
        select(SchedulerRun).where(SchedulerRun.project_id == project_id).limit(2000)
    )
    run_rows = list(runs_result.scalars().all())
    runs_data = [
        {
            "id": item.id,
            "dag_id": item.dag_id,
            "status": item.status,
            "trigger_source": item.trigger_source,
            "started_at": _ensure_utc_iso(item.started_at),
            "finished_at": _ensure_utc_iso(item.finished_at),
            "duration_ms": item.duration_ms,
        }
        for item in run_rows
    ]

    audit_result = await db.execute(
        select(AuditLog)
        .where(build_project_audit_filter(project_id))
        .order_by(AuditLog.timestamp.desc())
        .limit(3000)
    )
    audit_rows = list(audit_result.scalars().all())
    audit_data = [
        {
            "id": item.id,
            "action": item.action,
            "entity_type": item.entity_type,
            "entity_id": item.entity_id,
            "user_id": item.user_id,
            "timestamp": _ensure_utc_iso(item.timestamp),
        }
        for item in audit_rows
    ]

    catalog_data = [
        {
            "id": asset.id,
            "name": asset.name,
            "asset_type": asset.asset_type,
            "source_system": asset.source_system,
            "database_name": asset.database_name,
            "object_name": asset.object_name,
            "domain": asset.domain,
            "owner": asset.owner,
            "status": asset.status,
            "virtual_table": asset_meta[asset.id]["virtual_table"],
        }
        for asset in assets
    ]

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    _create_and_fill_table(
        conn,
        "catalog_assets",
        catalog_data,
        fallback_columns=[
            "id",
            "name",
            "asset_type",
            "source_system",
            "database_name",
            "object_name",
            "domain",
            "owner",
            "status",
            "virtual_table",
        ],
    )
    _create_and_fill_table(
        conn,
        "events",
        events_data,
        fallback_columns=[
            "id",
            "code",
            "name",
            "description",
            "domain",
            "status",
            "owner",
            "governance_status",
            "created_at",
            "updated_at",
        ],
    )
    _create_and_fill_table(
        conn,
        "governance_checks",
        governance_data,
        fallback_columns=["id", "event_name", "verdict", "score", "reasoning", "actor_id", "created_at"],
    )
    _create_and_fill_table(
        conn,
        "pipelines",
        pipelines_data,
        fallback_columns=[
            "id",
            "event_code",
            "topic_name",
            "flink_job_name",
            "status",
            "retry_count",
            "error_message",
            "updated_at",
        ],
    )
    _create_and_fill_table(
        conn,
        "data_quality_rules",
        dq_data,
        fallback_columns=["id", "asset_id", "event_id", "name", "rule_type", "severity", "status", "version", "updated_at"],
    )
    _create_and_fill_table(
        conn,
        "alerts",
        alerts_data,
        fallback_columns=["id", "source_type", "source_id", "severity", "title", "status", "created_at", "resolved_at"],
    )
    _create_and_fill_table(
        conn,
        "scheduler_dags",
        dags_data,
        fallback_columns=["id", "name", "status", "trigger_mode", "cron_expr", "version", "updated_at"],
    )
    _create_and_fill_table(
        conn,
        "scheduler_runs",
        runs_data,
        fallback_columns=["id", "dag_id", "status", "trigger_source", "started_at", "finished_at", "duration_ms"],
    )
    _create_and_fill_table(
        conn,
        "audit_logs",
        audit_data,
        fallback_columns=["id", "action", "entity_type", "entity_id", "user_id", "timestamp"],
    )

    for meta in asset_meta.values():
        _create_and_fill_table(
            conn,
            meta["virtual_table"],
            meta["sample_rows"],
            fallback_columns=[col["query_name"] for col in meta["columns"]],
        )
    return conn, asset_meta


async def _execute_readonly_query(
    db: AsyncSession,
    context: RequestContext,
    sql: str,
) -> tuple[list[str], list[dict[str, Any]], float]:
    normalized_sql = _validate_sql(sql)
    conn, _ = await _build_snapshot(db, context)
    started = time.perf_counter()
    try:
        cursor = conn.execute(normalized_sql)
        fetched = cursor.fetchall()
        elapsed_ms = (time.perf_counter() - started) * 1000
        columns = [item[0] for item in (cursor.description or [])]
        rows = [
            {
                column: (row[column] if isinstance(row, sqlite3.Row) else row[idx])
                for idx, column in enumerate(columns)
            }
            for row in fetched
        ]
        return columns, rows, elapsed_ms
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "SQL execution error: "
                f"{exc}. Tip: Use table names from Catalog Tree and only read-only SELECT/WITH."
            ),
        ) from exc
    finally:
        conn.close()


@router.get("/sources")
async def get_explore_sources(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    assets = await _load_project_assets(db, context.project.id)
    grouped: dict[str, dict[str, Any]] = {}
    for asset in assets:
        key = asset.source_system or "unknown"
        item = grouped.setdefault(key, {"source_system": key, "asset_count": 0, "databases": set()})
        item["asset_count"] += 1
        item["databases"].add(asset.database_name or "(default)")

    data = [
        {
            "source_system": value["source_system"],
            "asset_count": value["asset_count"],
            "database_count": len(value["databases"]),
        }
        for value in grouped.values()
    ]
    data.sort(key=lambda item: (item["source_system"] != "warehouse", item["source_system"]))
    return success_response(data)


@router.get("/catalog/tree")
async def get_explore_catalog_tree(
    source_system: str | None = Query(default=None),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    assets = await _load_project_assets(db, context.project.id, source_system=source_system)
    tree: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for asset in assets:
        columns = _asset_columns(asset)
        tree[asset.source_system or "unknown"][asset.database_name or "(default)"].append(
            {
                "id": asset.id,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "object_name": asset.object_name,
                "domain": asset.domain,
                "owner": asset.owner,
                "status": asset.status,
                "virtual_table": _asset_virtual_table_name(asset),
                "column_count": len(columns),
                "columns": [
                    {"name": col["name"], "query_name": col["query_name"], "type": col["type"]}
                    for col in columns
                ],
            }
        )

    result = []
    for source_name, db_map in sorted(tree.items(), key=lambda item: item[0]):
        databases = []
        for db_name, assets_in_db in sorted(db_map.items(), key=lambda item: item[0]):
            assets_in_db.sort(key=lambda item: (item["asset_type"], item["object_name"], item["id"]))
            databases.append(
                {
                    "database_name": db_name,
                    "assets": assets_in_db,
                }
            )
        result.append({"source_system": source_name, "databases": databases})
    return success_response(result)


@router.get("/assets/{asset_id}/profile")
async def get_explore_asset_profile(
    asset_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    asset = await DataAssetRepository(db).get(asset_id)
    if not asset or asset.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")

    columns = _asset_columns(asset)
    sample_rows = _asset_sample_rows(columns)
    virtual_table = _asset_virtual_table_name(asset)
    suggested_queries = [
        {
            "title": "Select sample rows",
            "sql": f"SELECT * FROM {virtual_table} LIMIT 100",
        },
        {
            "title": "Count rows",
            "sql": f"SELECT COUNT(*) AS total_rows FROM {virtual_table}",
        },
    ]

    return success_response(
        {
            "asset": {
                "id": asset.id,
                "name": asset.name,
                "asset_type": asset.asset_type,
                "source_system": asset.source_system,
                "database_name": asset.database_name,
                "object_name": asset.object_name,
                "domain": asset.domain,
                "owner": asset.owner,
                "status": asset.status,
                "virtual_table": virtual_table,
            },
            "columns": columns,
            "sample_rows": sample_rows,
            "suggested_queries": suggested_queries,
        }
    )


@router.post("/query")
async def run_explore_query(
    request: ExploreQueryRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    columns, rows, elapsed_ms = await _execute_readonly_query(db, context, request.sql)
    total_rows = len(rows)
    start = (request.page - 1) * request.page_size
    end = start + request.page_size
    paged_rows = rows[start:end]
    total_pages = max(1, math.ceil(total_rows / request.page_size))

    await BaseRepository(AuditLog, db).create(
        {
            "action": "EXPLORE_QUERY_EXECUTE",
            "entity_type": "EXPLORE_QUERY",
            "entity_id": str(context.project.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "sql": request.sql[:1000],
                    "page": request.page,
                    "page_size": request.page_size,
                    "total_rows": total_rows,
                    "execution_ms": round(elapsed_ms, 2),
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(
        {
            "columns": columns,
            "rows": paged_rows,
            "total_rows": total_rows,
            "page": request.page,
            "page_size": request.page_size,
            "total_pages": total_pages,
            "execution_ms": round(elapsed_ms, 2),
            "guidance": (
                "Only read-only SQL is supported. Available logical tables include: "
                "catalog_assets, events, governance_checks, pipelines, data_quality_rules, "
                "alerts, scheduler_dags, scheduler_runs, audit_logs, and asset_<id> virtual tables."
            ),
        }
    )


@router.post("/query/export")
async def export_explore_query(
    request: ExploreExportRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    export_format = request.format.strip().lower()
    if export_format not in {"csv", "json"}:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="format must be csv or json")

    columns, rows, elapsed_ms = await _execute_readonly_query(db, context, request.sql)

    if export_format == "json":
        content = json.dumps(rows, ensure_ascii=False, indent=2)
        mime_type = "application/json"
        filename = f"explore_results_project_{context.project.id}.json"
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(col) for col in columns])
        content = buffer.getvalue()
        mime_type = "text/csv"
        filename = f"explore_results_project_{context.project.id}.csv"

    await BaseRepository(AuditLog, db).create(
        {
            "action": "EXPLORE_QUERY_EXPORT",
            "entity_type": "EXPLORE_QUERY",
            "entity_id": str(context.project.id),
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "sql": request.sql[:1000],
                    "format": export_format,
                    "row_count": len(rows),
                    "execution_ms": round(elapsed_ms, 2),
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(
        {
            "format": export_format,
            "filename": filename,
            "mime_type": mime_type,
            "row_count": len(rows),
            "content": content,
        }
    )


@router.get("/prefill")
async def get_explore_prefill(
    source_type: str = Query(..., min_length=2, max_length=64),
    source_id: str = Query(..., min_length=1, max_length=128),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    source_type_normalized = source_type.strip().upper()
    parsed_source_id = _parse_resource_id(source_id, source_type_normalized)

    if source_type_normalized == "DATA_ASSET":
        asset = await DataAssetRepository(db).get(parsed_source_id)
        if not asset or asset.project_id != context.project.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data asset not found")
        virtual_table = _asset_virtual_table_name(asset)
        return success_response(
            {
                "title": f"Asset: {asset.name}",
                "description": "Prefilled query from Data Catalog asset",
                "sql": f"SELECT * FROM {virtual_table} LIMIT 100",
            }
        )

    if source_type_normalized == "EVENT":
        await _ensure_project_resource_exists(
            db=db,
            model=TrackingEvent,
            project_id=context.project.id,
            resource_id=parsed_source_id,
            not_found_message="Event not found",
        )
        return success_response(
            {
                "title": f"Event #{parsed_source_id}",
                "description": "Prefilled query from Event Catalog",
                "sql": f"SELECT * FROM events WHERE id = {parsed_source_id}",
            }
        )

    if source_type_normalized == "PIPELINE":
        await _ensure_project_resource_exists(
            db=db,
            model=Pipeline,
            project_id=context.project.id,
            resource_id=parsed_source_id,
            not_found_message="Pipeline not found",
        )
        return success_response(
            {
                "title": f"Pipeline #{parsed_source_id}",
                "description": "Prefilled query from Pipelines module",
                "sql": f"SELECT * FROM pipelines WHERE id = {parsed_source_id}",
            }
        )

    if source_type_normalized == "DATA_QUALITY_RULE":
        await _ensure_project_resource_exists(
            db=db,
            model=DataQualityRule,
            project_id=context.project.id,
            resource_id=parsed_source_id,
            not_found_message="Data quality rule not found",
        )
        return success_response(
            {
                "title": f"DQ Rule #{parsed_source_id}",
                "description": "Prefilled query from Data Quality module",
                "sql": f"SELECT * FROM data_quality_rules WHERE id = {parsed_source_id}",
            }
        )

    if source_type_normalized == "SCHEDULER_DAG":
        await _ensure_project_resource_exists(
            db=db,
            model=SchedulerDag,
            project_id=context.project.id,
            resource_id=parsed_source_id,
            not_found_message="Scheduler DAG not found",
        )
        return success_response(
            {
                "title": f"Scheduler DAG #{parsed_source_id}",
                "description": "Prefilled query from Scheduler module",
                "sql": (
                    "SELECT d.id, d.name, d.status, r.id AS run_id, r.status AS run_status, r.started_at "
                    "FROM scheduler_dags d LEFT JOIN scheduler_runs r ON r.dag_id = d.id "
                    f"WHERE d.id = {parsed_source_id} ORDER BY r.started_at DESC"
                ),
            }
        )

    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported source_type: {source_type}")
