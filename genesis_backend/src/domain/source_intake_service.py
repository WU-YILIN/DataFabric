from __future__ import annotations

import asyncio
import csv
import json
import random
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import aiomysql
import asyncpg
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.settings import decrypt_mapping, encrypt_mapping
from src.domain.source_intake_registry import CONNECTOR_CATALOG
from src.infrastructure.database.models.connector_definition import ConnectorDefinition
from src.infrastructure.database.models.external_data_source import ExternalDataSource
from src.infrastructure.database.models.knowledge_document import KnowledgeDocument
from src.infrastructure.database.models.source_asset import SourceAsset
from src.infrastructure.database.models.source_asset_snapshot import SourceAssetSnapshot
from src.infrastructure.database.models.source_field import SourceField
from src.infrastructure.database.models.source_field_profile import SourceFieldProfile
from src.infrastructure.database.models.source_candidate import SourceCandidate
from src.infrastructure.database.models.source_change_event import SourceChangeEvent
from src.infrastructure.database.models.source_instance import SourceInstance
from src.infrastructure.database.models.source_sync_run import SourceSyncRun
from src.infrastructure.database.models.source_telemetry_sample import SourceTelemetrySample
from src.infrastructure.database.models.semantic_candidate import SemanticCandidate
from src.infrastructure.database.repositories.base import BaseRepository


CONNECTOR_SOURCE_TYPE_MAP = {"mysql": "MYSQL", "postgresql": "POSTGRESQL", "sqlite": "SQLITE"}
SYSTEM_MYSQL_SCHEMAS = {"information_schema", "performance_schema", "mysql", "sys"}
SYSTEM_MONGO_DATABASES = {"admin", "config", "local"}
DOMAIN_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("订单域", ("order", "orders", "订单", "交易", "gmv", "cart", "sku")),
    ("用户域", ("user", "users", "member", "customer", "用户", "会员", "uid")),
    ("支付域", ("payment", "payments", "pay", "refund", "invoice", "支付", "退款")),
    ("商品域", ("product", "inventory", "stock", "sku", "goods", "商品", "库存")),
    ("增长域", ("campaign", "traffic", "growth", "marketing", "ad", "活动", "流量")),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _mask_config(config: dict[str, Any]) -> dict[str, Any]:
    masked = dict(config)
    for key in ("password", "api_key"):
        if masked.get(key):
            masked[key] = "***"
    return masked


def _merge_config(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key, value in incoming.items():
        if key in {"password", "api_key"} and value in (None, "", "***"):
            continue
        merged[key] = value
    return merged


def _paginate(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    total = len(items)
    total_pages = max((total + page_size - 1) // page_size, 1)
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
    }


def _heat_level(total_rows: int) -> str:
    if total_rows >= 1_000_000:
        return "HOT"
    if total_rows >= 50_000:
        return "WARM"
    return "COLD"


def _infer_domain(name: str) -> str:
    haystack = name.lower()
    for label, tokens in DOMAIN_RULES:
        if any(token in haystack for token in tokens):
            return label
    return "通用域"


def _infer_update_mode(columns: list[dict[str, Any]], row_count: int) -> str:
    names = {str(item.get("name") or "").lower() for item in columns}
    has_time = any(any(token in name for token in ("time", "date", "created", "updated")) for name in names)
    has_id = any(name == "id" or name.endswith("_id") for name in names)
    if has_time and has_id and row_count >= 100_000:
        return "APPEND"
    if has_time and row_count >= 10_000:
        return "PERIODIC_FULL"
    if has_id:
        return "UPSERT"
    return "FULL_SNAPSHOT"


def _json_signature(schema_payload: dict[str, Any], metrics_payload: dict[str, Any]) -> str:
    return json.dumps({"schema": schema_payload, "metrics": metrics_payload}, sort_keys=True, ensure_ascii=False)


class SourceIntakeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.connector_repo = BaseRepository(ConnectorDefinition, db)
        self.instance_repo = BaseRepository(SourceInstance, db)
        self.asset_repo = BaseRepository(SourceAsset, db)
        self.snapshot_repo = BaseRepository(SourceAssetSnapshot, db)
        self.field_repo = BaseRepository(SourceField, db)
        self.field_profile_repo = BaseRepository(SourceFieldProfile, db)
        self.change_repo = BaseRepository(SourceChangeEvent, db)
        self.candidate_repo = BaseRepository(SourceCandidate, db)
        self.sync_run_repo = BaseRepository(SourceSyncRun, db)
        self.telemetry_repo = BaseRepository(SourceTelemetrySample, db)
        self.semantic_candidate_repo = BaseRepository(SemanticCandidate, db)
        self.legacy_repo = BaseRepository(ExternalDataSource, db)
        self.knowledge_repo = BaseRepository(KnowledgeDocument, db)

    async def ensure_connector_catalog(self) -> None:
        result = await self.db.execute(select(ConnectorDefinition))
        existing = {item.connector_key: item for item in result.scalars().all()}
        for item in CONNECTOR_CATALOG:
            payload = {
                "category": item["category"],
                "display_name": item["display_name"],
                "runtime_family": item["runtime_family"],
                "status": item["status"],
                "description": item["description"],
                "config_schema": item["config_schema"],
                "capabilities": item["capabilities"],
                "auth_modes": item["auth_modes"],
            }
            if item["connector_key"] not in existing:
                await self.connector_repo.create({"connector_key": item["connector_key"], **payload})
            else:
                await self.connector_repo.update(existing[item["connector_key"]], payload)
        await self.db.commit()

    async def list_connectors(self, *, q: str | None = None, category: str | None = None, status: str | None = None) -> dict[str, Any]:
        await self.ensure_connector_catalog()
        result = await self.db.execute(select(ConnectorDefinition).order_by(ConnectorDefinition.category, ConnectorDefinition.display_name))
        items = [self._serialize_connector(item) for item in result.scalars().all()]
        keyword = (q or "").strip().lower()
        if keyword:
            items = [item for item in items if keyword in item["display_name"].lower() or keyword in item["connector_key"].lower()]
        if category and category != "ALL":
            items = [item for item in items if item["category"] == category]
        if status and status != "ALL":
            items = [item for item in items if item["status"] == status]
        return {"items": items, "categories": sorted({item["category"] for item in items})}

    async def list_instances(
        self,
        *,
        project_id: int,
        q: str | None = None,
        connector_key: str | None = None,
        status: str | None = None,
        heat: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        await self.ensure_connector_catalog()
        connectors = await self._connector_map()
        result = await self.db.execute(
            select(SourceInstance).where(SourceInstance.project_id == project_id).order_by(SourceInstance.updated_at.desc(), SourceInstance.id.desc())
        )
        items = [await self._serialize_instance(item, connectors) for item in result.scalars().all()]
        keyword = (q or "").strip().lower()
        if keyword:
            items = [item for item in items if keyword in item["instance_name"].lower() or keyword in item["connector_name"].lower()]
        if connector_key and connector_key != "ALL":
            items = [item for item in items if item["connector_key"] == connector_key]
        if status and status != "ALL":
            items = [item for item in items if item["status"] == status]
        if heat and heat != "ALL":
            items = [item for item in items if item["heat_level"] == heat]
        paged = _paginate(items, page, page_size)
        paged["facets"] = {
            "connector_keys": sorted({item["connector_key"] for item in items}),
            "statuses": sorted({item["status"] for item in items}),
            "heat_levels": sorted({item["heat_level"] for item in items}),
        }
        return paged

    async def create_instance(self, *, project_id: int, instance_name: str, connector_key: str, config: dict[str, Any]) -> dict[str, Any]:
        connector = await self._get_connector(connector_key)
        instance = await self.instance_repo.create(
            {
                "project_id": project_id,
                "connector_definition_id": connector.id,
                "instance_name": instance_name.strip(),
                "status": "DRAFT",
                "memory_scope_default": str(config.get("memory_scope_default") or "PRIVATE").upper(),
                "encrypted_config": encrypt_mapping(config),
                "last_brief_payload": {},
            }
        )
        await self.db.commit()
        return await self.get_instance(project_id=project_id, instance_id=instance.id)

    async def get_instance(self, *, project_id: int, instance_id: int) -> dict[str, Any]:
        instance = await self._get_instance(project_id, instance_id)
        connectors = await self._connector_map()
        payload = await self._serialize_instance(instance, connectors)
        payload["recent_briefs"] = await self._list_instance_briefs(instance.id, limit=5)
        payload["latest_assets"] = await self._list_assets(project_id=project_id, instance_id=instance.id, limit=5, offset=0)
        return payload

    async def update_instance(
        self,
        *,
        project_id: int,
        instance_id: int,
        instance_name: str | None,
        config: dict[str, Any] | None,
        memory_scope_default: str | None = None,
        watch_enabled: bool | None = None,
        watch_interval_seconds: int | None = None,
    ) -> dict[str, Any]:
        instance = await self._get_instance(project_id, instance_id)
        payload: dict[str, Any] = {}
        now = _utcnow()
        if instance_name is not None:
            payload["instance_name"] = instance_name.strip()
        if config is not None:
            merged = _merge_config(decrypt_mapping(instance.encrypted_config), config)
            if memory_scope_default:
                merged["memory_scope_default"] = memory_scope_default
            payload["encrypted_config"] = encrypt_mapping(merged)
            payload["memory_scope_default"] = str(merged.get("memory_scope_default") or instance.memory_scope_default or "PRIVATE").upper()
            payload["status"] = "DRAFT"
        elif memory_scope_default:
            payload["memory_scope_default"] = memory_scope_default.upper()
        if watch_interval_seconds is not None:
            normalized_interval = max(30, min(int(watch_interval_seconds), 86400))
            payload["watch_interval_seconds"] = normalized_interval
        else:
            normalized_interval = int(instance.watch_interval_seconds or 300)
        if watch_enabled is not None:
            payload["watch_enabled"] = watch_enabled
            payload["watch_next_run_at"] = now if watch_enabled else None
            if watch_enabled:
                payload["last_watch_status"] = "SCHEDULED"
                payload["last_watch_message"] = f"自动监听已启用，间隔 {normalized_interval} 秒"
            else:
                payload["last_watch_status"] = "DISABLED"
                payload["last_watch_message"] = "自动监听已关闭"
        elif watch_interval_seconds is not None and instance.watch_enabled:
            payload["watch_next_run_at"] = now + timedelta(seconds=normalized_interval)
            payload["last_watch_status"] = "SCHEDULED"
            payload["last_watch_message"] = f"监听间隔已更新为 {normalized_interval} 秒"
        await self.instance_repo.update(instance, payload)
        await self.db.commit()
        return await self.get_instance(project_id=project_id, instance_id=instance.id)

    async def delete_instance(self, *, project_id: int, instance_id: int) -> dict[str, Any]:
        instance = await self._get_instance(project_id, instance_id)
        await self._delete_related_documents(
            project_id=project_id,
            instance_id=instance.id,
            legacy_source_id=instance.legacy_source_id,
        )
        if instance.legacy_source_id:
            legacy_source = await self.legacy_repo.get(instance.legacy_source_id)
            if legacy_source is not None and legacy_source.project_id == project_id:
                await self.legacy_repo.remove(legacy_source.id)
        await self.instance_repo.remove(instance.id)
        await self.db.commit()
        return {"id": instance.id, "instance_name": instance.instance_name, "deleted": True}

    async def test_instance(self, *, project_id: int, instance_id: int) -> dict[str, Any]:
        instance = await self._get_instance(project_id, instance_id)
        connector = await self._get_connector_by_id(instance.connector_definition_id)
        config = decrypt_mapping(instance.encrypted_config)
        run = await self.sync_run_repo.create(
            {
                "project_id": project_id,
                "instance_id": instance.id,
                "run_type": "TEST",
                "trigger_mode": "MANUAL",
                "status": "RUNNING",
                "started_at": _utcnow(),
                "metrics_payload": {},
                "brief_payload": {},
            }
        )
        try:
            message = await self._run_connection_test(connector.connector_key, connector.runtime_family, config)
            await self.instance_repo.update(
                instance,
                {
                    "status": "CONNECTED",
                    "last_test_status": "SUCCESS",
                    "last_test_message": message,
                    "last_tested_at": _utcnow(),
                },
            )
            await self.sync_run_repo.update(run, {"status": "SUCCESS", "summary": message, "finished_at": _utcnow()})
            await self._record_source_sample(instance, "TEST", 0, 0, 0)
            await self._sync_source_brief_document(
                instance=instance,
                connector=connector,
                tenant_id=None,
                actor_id=None,
                user_id=None,
                mode="TEST",
                summary=f"{connector.display_name} 实例 {instance.instance_name} 已通过连接测试。",
                assets=[],
                brief_payload={
                    "title": f"{instance.instance_name} 连接简报",
                    "summary": f"{connector.display_name} 实例 {instance.instance_name} 已通过连接测试。",
                    "recommended_actions": ["执行发现以采集资产和结构信息", "查看实例详情中的连接配置与记忆范围"],
                },
            )
            await self.db.commit()
            return {"status": "SUCCESS", "message": message, "instance": await self.get_instance(project_id=project_id, instance_id=instance.id)}
        except Exception as exc:
            await self.instance_repo.update(
                instance,
                {
                    "status": "TEST_FAILED",
                    "last_test_status": "FAILURE",
                    "last_test_message": str(exc),
                    "last_tested_at": _utcnow(),
                },
            )
            await self.sync_run_repo.update(run, {"status": "FAILURE", "summary": str(exc), "finished_at": _utcnow()})
            await self._record_source_sample(instance, "TEST", 0, 0, 1)
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": str(exc), "instance": await self.get_instance(project_id=project_id, instance_id=instance.id)},
            ) from exc

    def _serialize_connector(self, connector: ConnectorDefinition) -> dict[str, Any]:
        return {
            "id": connector.id,
            "connector_key": connector.connector_key,
            "category": connector.category,
            "display_name": connector.display_name,
            "runtime_family": connector.runtime_family,
            "status": connector.status,
            "description": connector.description,
            "config_schema": connector.config_schema or [],
            "capabilities": connector.capabilities or [],
            "auth_modes": connector.auth_modes or [],
        }

    async def _connector_map(self) -> dict[int, ConnectorDefinition]:
        result = await self.db.execute(select(ConnectorDefinition))
        return {item.id: item for item in result.scalars().all()}

    async def _get_connector(self, connector_key: str) -> ConnectorDefinition:
        await self.ensure_connector_catalog()
        result = await self.db.execute(select(ConnectorDefinition).where(ConnectorDefinition.connector_key == connector_key))
        connector = result.scalar_one_or_none()
        if connector is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
        return connector

    async def _get_connector_by_id(self, connector_definition_id: int) -> ConnectorDefinition:
        connector = await self.connector_repo.get(connector_definition_id)
        if connector is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Connector not found")
        return connector

    async def _get_instance(self, project_id: int, instance_id: int) -> SourceInstance:
        instance = await self.instance_repo.get(instance_id)
        if instance is None or instance.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found")
        return instance

    async def _serialize_instance(self, instance: SourceInstance, connectors: dict[int, ConnectorDefinition]) -> dict[str, Any]:
        connector = connectors[instance.connector_definition_id]
        result = await self.db.execute(select(SourceAsset).where(SourceAsset.instance_id == instance.id))
        assets = list(result.scalars().all())
        rows = sum(int((asset.metrics_payload or {}).get("row_count_estimate") or 0) for asset in assets)
        bytes_estimate = sum(int((asset.metrics_payload or {}).get("estimated_bytes") or 0) for asset in assets)
        return {
            "id": instance.id,
            "instance_name": instance.instance_name,
            "connector_key": connector.connector_key,
            "connector_name": connector.display_name,
            "category": connector.category,
            "runtime_family": connector.runtime_family,
            "connector_status": connector.status,
            "capabilities": connector.capabilities or [],
            "auth_modes": connector.auth_modes or [],
            "status": instance.status,
            "memory_scope_default": instance.memory_scope_default,
            "heat_level": _heat_level(rows),
            "asset_count": len(assets),
            "row_count_estimate": rows,
            "estimated_bytes": bytes_estimate,
            "config": _mask_config(decrypt_mapping(instance.encrypted_config)),
            "last_test_status": instance.last_test_status,
            "last_test_message": instance.last_test_message,
            "last_tested_at": _to_iso(instance.last_tested_at),
            "last_discover_status": instance.last_discover_status,
            "last_discover_message": instance.last_discover_message,
            "last_discovered_at": _to_iso(instance.last_discovered_at),
            "last_watch_status": instance.last_watch_status,
            "last_watch_message": instance.last_watch_message,
            "last_watched_at": _to_iso(instance.last_watched_at),
            "watch_enabled": instance.watch_enabled,
            "watch_interval_seconds": instance.watch_interval_seconds,
            "watch_next_run_at": _to_iso(instance.watch_next_run_at),
            "watch_last_started_at": _to_iso(instance.watch_last_started_at),
            "watch_last_finished_at": _to_iso(instance.watch_last_finished_at),
            "watch_failure_count": instance.watch_failure_count,
            "last_brief_title": instance.last_brief_title,
            "last_brief_summary": instance.last_brief_summary,
            "last_brief_payload": instance.last_brief_payload or {},
            "created_at": _to_iso(instance.created_at),
            "updated_at": _to_iso(instance.updated_at),
        }

    async def discover_instance(self, *, project_id: int, instance_id: int, trigger_mode: str = "MANUAL") -> dict[str, Any]:
        instance = await self._get_instance(project_id, instance_id)
        connector = await self._get_connector_by_id(instance.connector_definition_id)
        config = decrypt_mapping(instance.encrypted_config)
        run_type = "WATCH" if trigger_mode == "WATCH" else "DISCOVER"
        started_at = _utcnow()
        run = await self.sync_run_repo.create(
            {
                "project_id": project_id,
                "instance_id": instance.id,
                "run_type": run_type,
                "trigger_mode": trigger_mode,
                "status": "RUNNING",
                "started_at": started_at,
                "metrics_payload": {},
                "brief_payload": {},
            }
        )
        try:
            if trigger_mode == "WATCH":
                await self.instance_repo.update(
                    instance,
                    {
                        "last_watch_status": "RUNNING",
                        "last_watch_message": "自动监听执行中",
                        "watch_last_started_at": started_at,
                    },
                )
            discovery = await self._discover_assets(connector.connector_key, connector.runtime_family, config)
            applied = await self._apply_discovery(project_id=project_id, instance=instance, connector=connector, discovery=discovery)
            brief = self._build_brief(instance.instance_name, connector.display_name, discovery, applied["changes"])
            finished_at = _utcnow()
            next_watch_run = None
            if trigger_mode == "WATCH" and instance.watch_enabled:
                next_watch_run = finished_at + timedelta(seconds=max(30, int(instance.watch_interval_seconds or 300)))
            await self.instance_repo.update(
                instance,
                {
                    "status": "DISCOVERED",
                    "last_discover_status": "SUCCESS",
                    "last_discover_message": brief["summary"],
                    "last_discovered_at": finished_at,
                    "last_watch_status": "SUCCESS" if trigger_mode == "WATCH" else instance.last_watch_status,
                    "last_watch_message": brief["summary"] if trigger_mode == "WATCH" else instance.last_watch_message,
                    "last_watched_at": finished_at if trigger_mode == "WATCH" else instance.last_watched_at,
                    "watch_last_finished_at": finished_at if trigger_mode == "WATCH" else instance.watch_last_finished_at,
                    "watch_failure_count": 0 if trigger_mode == "WATCH" else instance.watch_failure_count,
                    "watch_next_run_at": next_watch_run if trigger_mode == "WATCH" else instance.watch_next_run_at,
                    "last_brief_title": brief["title"],
                    "last_brief_summary": brief["summary"],
                    "last_brief_payload": brief,
                },
            )
            await self.sync_run_repo.update(
                run,
                {
                    "status": "SUCCESS",
                    "summary": brief["summary"],
                    "brief_title": brief["title"],
                    "brief_summary": brief["summary"],
                    "brief_payload": brief,
                    "metrics_payload": brief["metrics"],
                    "finished_at": finished_at,
                },
            )
            await self._sync_source_brief_document(
                instance=instance,
                connector=connector,
                tenant_id=None,
                actor_id=None,
                user_id=None,
                mode=run_type,
                summary=brief["summary"],
                assets=discovery.get("assets", []),
                brief_payload=brief,
            )
            await self._record_telemetry_after_discovery(instance, discovery=discovery, brief=brief)
            await self.db.commit()
            return {
                "instance": await self.get_instance(project_id=project_id, instance_id=instance.id),
                "discovery": discovery,
                "brief": brief,
                "changes": applied["changes"],
                "candidates": applied["candidates"],
            }
        except Exception as exc:
            await self.instance_repo.update(
                instance,
                {
                    "status": "DISCOVER_FAILED",
                    "last_discover_status": "FAILURE",
                    "last_discover_message": str(exc),
                    "last_discovered_at": _utcnow(),
                    "last_watch_status": "FAILURE" if trigger_mode == "WATCH" else instance.last_watch_status,
                    "last_watch_message": str(exc) if trigger_mode == "WATCH" else instance.last_watch_message,
                    "last_watched_at": _utcnow() if trigger_mode == "WATCH" else instance.last_watched_at,
                    "watch_last_finished_at": _utcnow() if trigger_mode == "WATCH" else instance.watch_last_finished_at,
                    "watch_failure_count": (int(instance.watch_failure_count or 0) + 1) if trigger_mode == "WATCH" else instance.watch_failure_count,
                    "watch_next_run_at": (_utcnow() + timedelta(seconds=max(30, int(instance.watch_interval_seconds or 300))))
                    if trigger_mode == "WATCH" and instance.watch_enabled
                    else instance.watch_next_run_at,
                },
            )
            await self.sync_run_repo.update(run, {"status": "FAILURE", "summary": str(exc), "finished_at": _utcnow()})
            await self._record_source_sample(instance, "DISCOVER", 0, 0, 1)
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"message": str(exc), "instance": await self.get_instance(project_id=project_id, instance_id=instance.id)},
            ) from exc

    async def run_due_watches(self, *, limit: int = 20) -> dict[str, Any]:
        now = _utcnow()
        result = await self.db.execute(
            select(SourceInstance)
            .where(SourceInstance.watch_enabled.is_(True))
            .where((SourceInstance.watch_next_run_at.is_(None)) | (SourceInstance.watch_next_run_at <= now))
            .order_by(SourceInstance.watch_next_run_at.asc(), SourceInstance.id.asc())
            .limit(max(1, limit))
        )
        due_instances = list(result.scalars().all())
        summary = {"processed": len(due_instances), "success": 0, "failed": 0, "instance_ids": [item.id for item in due_instances]}
        for instance in due_instances:
            try:
                await self.discover_instance(project_id=instance.project_id, instance_id=instance.id, trigger_mode="WATCH")
                summary["success"] += 1
            except Exception:
                summary["failed"] += 1
                await self.db.rollback()
        return summary

    async def list_assets(
        self,
        *,
        project_id: int,
        q: str | None = None,
        instance_id: int | None = None,
        asset_type: str | None = None,
        heat: str | None = None,
        status: str | None = None,
        updated_since: str | None = None,
        page: int = 1,
        page_size: int = 25,
        ) -> dict[str, Any]:
        return await self._list_assets(
            project_id=project_id,
            q=q,
            instance_id=instance_id,
            asset_type=asset_type,
            heat=heat,
            status=status,
            updated_since=updated_since,
            limit=page_size,
            offset=(page - 1) * page_size,
            include_total=True,
        )

    async def list_asset_fields(
        self,
        *,
        project_id: int,
        asset_id: int,
        q: str | None = None,
        candidate_type: str | None = None,
        field_status: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        asset = await self.asset_repo.get(asset_id)
        if asset is None or asset.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        result = await self.db.execute(
            select(SourceField)
            .where(SourceField.asset_id == asset_id, SourceField.project_id == project_id)
            .order_by(SourceField.ordinal_position.asc(), SourceField.id.asc())
        )
        items = [await self._serialize_field(item) for item in result.scalars().all()]
        keyword = (q or "").strip().lower()
        if keyword:
            items = [
                item
                for item in items
                if keyword in item["field_name"].lower() or keyword in item["display_name"].lower()
            ]
        if field_status and field_status != "ALL":
            items = [item for item in items if item["status"] == field_status]
        if candidate_type and candidate_type != "ALL":
            items = [
                item
                for item in items
                if any(candidate["candidate_type"] == candidate_type for candidate in item["candidates"])
            ]
        return _paginate(items, page, page_size)

    async def get_field_detail(self, *, project_id: int, field_id: int) -> dict[str, Any]:
        field = await self.field_repo.get(field_id)
        if field is None or field.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")
        return await self._serialize_field(field, include_profiles=True)

    async def list_field_profiles(self, *, project_id: int, field_id: int) -> list[dict[str, Any]]:
        field = await self.field_repo.get(field_id)
        if field is None or field.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")
        result = await self.db.execute(
            select(SourceFieldProfile)
            .where(SourceFieldProfile.field_id == field_id, SourceFieldProfile.project_id == project_id)
            .order_by(SourceFieldProfile.profiled_at.desc(), SourceFieldProfile.id.desc())
        )
        return [self._serialize_field_profile(item) for item in result.scalars().all()]

    async def list_field_candidates(self, *, project_id: int, field_id: int) -> list[dict[str, Any]]:
        field = await self.field_repo.get(field_id)
        if field is None or field.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Field not found")
        result = await self.db.execute(
            select(SemanticCandidate)
            .where(SemanticCandidate.field_id == field_id, SemanticCandidate.project_id == project_id)
            .order_by(SemanticCandidate.updated_at.desc(), SemanticCandidate.id.desc())
        )
        return [self._serialize_semantic_candidate(item) for item in result.scalars().all()]

    async def list_change_events(
        self,
        *,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        severity: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(SourceChangeEvent).where(SourceChangeEvent.project_id == project_id).order_by(SourceChangeEvent.detected_at.desc(), SourceChangeEvent.id.desc())
        )
        items = [self._serialize_change_event(item) for item in result.scalars().all()]
        keyword = (q or "").strip().lower()
        if keyword:
            items = [item for item in items if keyword in item["title"].lower() or keyword in (item["summary"] or "").lower()]
        if status and status != "ALL":
            items = [item for item in items if item["status"] == status]
        if severity and severity != "ALL":
            items = [item for item in items if item["severity"] == severity]
        return _paginate(items, page, page_size)

    async def list_candidates(
        self,
        *,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        candidate_type: str | None = None,
        memory_scope_target: str | None = None,
        page: int = 1,
        page_size: int = 25,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(SourceCandidate).where(SourceCandidate.project_id == project_id).order_by(SourceCandidate.updated_at.desc(), SourceCandidate.id.desc())
        )
        items = [await self._serialize_candidate(item) for item in result.scalars().all()]
        keyword = (q or "").strip().lower()
        if keyword:
            items = [item for item in items if keyword in item["title"].lower() or keyword in (item["summary"] or "").lower()]
        if status and status != "ALL":
            items = [item for item in items if item["status"] == status]
        if candidate_type and candidate_type != "ALL":
            items = [item for item in items if item["candidate_type"] == candidate_type]
        if memory_scope_target and memory_scope_target != "ALL":
            items = [item for item in items if item["memory_scope_target"] == memory_scope_target]
        return _paginate(items, page, page_size)

    async def list_briefs(
        self,
        *,
        project_id: int,
        instance_id: int | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(SourceSyncRun).where(SourceSyncRun.project_id == project_id).order_by(SourceSyncRun.created_at.desc(), SourceSyncRun.id.desc())
        )
        items = []
        for item in result.scalars().all():
            if instance_id and item.instance_id != instance_id:
                continue
            if not item.brief_title and not item.brief_summary:
                continue
            items.append(
                {
                    "id": item.id,
                    "instance_id": item.instance_id,
                    "run_type": item.run_type,
                    "status": item.status,
                    "title": item.brief_title,
                    "summary": item.brief_summary,
                    "created_at": _to_iso(item.created_at),
                    "metrics": item.metrics_payload or {},
                }
            )
        return _paginate(items, page, page_size)

    async def promote_candidate(
        self,
        *,
        project_id: int,
        candidate_id: int,
        tenant_id: int | None,
        actor_id: str | None,
        user_id: int | None,
        share: bool = False,
    ) -> dict[str, Any]:
        candidate = await self._get_candidate(project_id, candidate_id)
        instance = await self._get_instance(project_id, candidate.instance_id)
        target_scope = "TENANT" if share else "PRIVATE"
        await self.candidate_repo.update(
            candidate,
            {
                "status": "SHARED" if share else "PROMOTED",
                "memory_scope_target": target_scope,
                "decided_at": _utcnow(),
            },
        )
        if candidate.asset_id:
            asset = await self.asset_repo.get(candidate.asset_id)
            if asset is not None:
                await self.asset_repo.update(asset, {"status": "SHARED" if share else "ACTIVE"})
        if candidate.change_event_id:
            change_event = await self.change_repo.get(candidate.change_event_id)
            if change_event is not None:
                await self.change_repo.update(change_event, {"status": "RESOLVED"})
        await self._sync_candidate_memory(instance=instance, tenant_id=tenant_id, actor_id=actor_id, user_id=user_id, memory_scope=target_scope)
        await self.db.commit()
        return await self._serialize_candidate(candidate)

    async def dismiss_candidate(self, *, project_id: int, candidate_id: int) -> dict[str, Any]:
        candidate = await self._get_candidate(project_id, candidate_id)
        await self.candidate_repo.update(candidate, {"status": "DISMISSED", "decided_at": _utcnow()})
        if candidate.change_event_id:
            change_event = await self.change_repo.get(candidate.change_event_id)
            if change_event is not None:
                await self.change_repo.update(change_event, {"status": "DISMISSED"})
        await self.db.commit()
        return await self._serialize_candidate(candidate)

    def _serialize_asset(self, asset: SourceAsset) -> dict[str, Any]:
        metrics = asset.metrics_payload or {}
        columns = (asset.schema_payload or {}).get("columns") or []
        return {
            "id": asset.id,
            "instance_id": asset.instance_id,
            "asset_key": asset.asset_key,
            "asset_type": asset.asset_type,
            "qualified_name": asset.qualified_name,
            "display_name": asset.display_name,
            "status": asset.status,
            "heat_level": asset.heat_level,
            "inferred_domain": asset.inferred_domain,
            "row_count_estimate": int(metrics.get("row_count_estimate") or 0),
            "estimated_bytes": int(metrics.get("estimated_bytes") or 0),
            "column_count": int(metrics.get("column_count") or 0),
            "field_count": int(metrics.get("field_count") or len(columns)),
            "semantic_candidate_count": int(metrics.get("semantic_candidate_count") or 0),
            "update_mode": str(metrics.get("update_mode") or "FULL_SNAPSHOT"),
            "last_seen_at": _to_iso(asset.last_seen_at),
            "schema_payload": asset.schema_payload or {},
            "metrics_payload": metrics,
            "updated_at": _to_iso(asset.updated_at),
        }

    async def _serialize_field(self, field: SourceField, *, include_profiles: bool = False) -> dict[str, Any]:
        profiles = await self.list_field_profiles(project_id=field.project_id, field_id=field.id) if include_profiles else []
        candidates = await self.list_field_candidates(project_id=field.project_id, field_id=field.id)
        latest_profile = profiles[0] if profiles else None
        return {
            "id": field.id,
            "project_id": field.project_id,
            "instance_id": field.instance_id,
            "asset_id": field.asset_id,
            "field_key": field.field_key,
            "field_name": field.field_name,
            "display_name": field.display_name,
            "physical_type": field.physical_type,
            "nullable": field.nullable,
            "ordinal_position": field.ordinal_position,
            "status": field.status,
            "is_partition_key": field.is_partition_key,
            "is_primary_key_candidate": field.is_primary_key_candidate,
            "is_time_field_candidate": field.is_time_field_candidate,
            "last_seen_at": _to_iso(field.last_seen_at),
            "latest_profile": latest_profile,
            "profiles": profiles,
            "candidates": candidates,
        }

    def _serialize_field_profile(self, profile: SourceFieldProfile) -> dict[str, Any]:
        return {
            "id": profile.id,
            "field_id": profile.field_id,
            "asset_id": profile.asset_id,
            "snapshot_id": profile.snapshot_id,
            "null_ratio": profile.null_ratio,
            "distinct_ratio": profile.distinct_ratio,
            "sample_values": profile.sample_values or [],
            "min_value": profile.min_value,
            "max_value": profile.max_value,
            "observed_row_count": profile.observed_row_count,
            "profile_payload": profile.profile_payload or {},
            "profiled_at": _to_iso(profile.profiled_at),
        }

    def _serialize_semantic_candidate(self, candidate: SemanticCandidate) -> dict[str, Any]:
        return {
            "id": candidate.id,
            "instance_id": candidate.instance_id,
            "asset_id": candidate.asset_id,
            "field_id": candidate.field_id,
            "object_type": candidate.object_type,
            "candidate_type": candidate.candidate_type,
            "candidate_value": candidate.candidate_value,
            "confidence": candidate.confidence,
            "reasoning": candidate.reasoning,
            "status": candidate.status,
            "evidence_payload": candidate.evidence_payload or {},
            "created_at": _to_iso(candidate.created_at),
            "updated_at": _to_iso(candidate.updated_at),
            "decided_at": _to_iso(candidate.decided_at),
        }

    def _serialize_change_event(self, event: SourceChangeEvent) -> dict[str, Any]:
        return {
            "id": event.id,
            "instance_id": event.instance_id,
            "asset_id": event.asset_id,
            "event_type": event.event_type,
            "severity": event.severity,
            "status": event.status,
            "title": event.title,
            "summary": event.summary,
            "recommended_action": event.recommended_action,
            "detail_payload": event.detail_payload or {},
            "brief_payload": event.brief_payload or {},
            "detected_at": _to_iso(event.detected_at),
            "updated_at": _to_iso(event.updated_at),
        }

    async def _serialize_candidate(self, candidate: SourceCandidate) -> dict[str, Any]:
        asset = await self.asset_repo.get(candidate.asset_id) if candidate.asset_id else None
        change_event = await self.change_repo.get(candidate.change_event_id) if candidate.change_event_id else None
        return {
            "id": candidate.id,
            "instance_id": candidate.instance_id,
            "asset_id": candidate.asset_id,
            "change_event_id": candidate.change_event_id,
            "candidate_type": candidate.candidate_type,
            "status": candidate.status,
            "title": candidate.title,
            "summary": candidate.summary,
            "recommendation": candidate.recommendation,
            "memory_scope_target": candidate.memory_scope_target,
            "action_payload": candidate.action_payload or {},
            "asset": self._serialize_asset(asset) if asset else None,
            "change_event": self._serialize_change_event(change_event) if change_event else None,
            "created_at": _to_iso(candidate.created_at),
            "updated_at": _to_iso(candidate.updated_at),
            "decided_at": _to_iso(candidate.decided_at),
        }

    async def get_telemetry_overview(self, *, project_id: int, instance_id: int | None = None) -> dict[str, Any]:
        source_series = await self.get_source_series(project_id=project_id, window="24h", instance_id=instance_id)
        node_series = await self.get_node_series(project_id=project_id, window="24h", instance_id=instance_id)
        return {
            "summary": {
                "instance_count": len(source_series["latest"]),
                "hot_instances": sum(1 for item in source_series["latest"] if item["heat_level"] == "HOT"),
                "open_candidates": await self._count_candidates(project_id, {"OPEN"}),
                "open_changes": await self._count_changes(project_id, {"OPEN"}),
            },
            "source_load": source_series["latest"],
            "nodes": node_series["latest"],
        }

    async def get_source_series(self, *, project_id: int, window: str = "24h", instance_id: int | None = None) -> dict[str, Any]:
        samples = await self._load_telemetry_samples(
            project_id=project_id,
            scope_type="SOURCE",
            window=window,
            instance_id=instance_id,
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        latest: dict[str, dict[str, Any]] = {}
        for item in samples:
            payload = item.metrics_payload or {}
            key = item.scope_key
            point = {
                "sample_at": _to_iso(item.sample_at),
                "load_score": float(payload.get("load_score") or 0),
                "throughput_mb_per_hour": float(payload.get("throughput_mb_per_hour") or 0),
                "scan_duration_ms": int(payload.get("scan_duration_ms") or 0),
                "failure_rate": float(payload.get("failure_rate") or 0),
                "heat_level": str(payload.get("heat_level") or "COLD"),
            }
            grouped.setdefault(key, []).append(point)
            latest[key] = {
                "scope_key": key,
                "instance_id": item.instance_id,
                "instance_name": str(payload.get("instance_name") or key),
                "heat_level": point["heat_level"],
                "load_score": point["load_score"],
                "throughput_mb_per_hour": point["throughput_mb_per_hour"],
                "scan_duration_ms": point["scan_duration_ms"],
                "failure_rate": point["failure_rate"],
            }
        return {"series": grouped, "latest": list(latest.values())}

    async def get_node_series(self, *, project_id: int, window: str = "24h", instance_id: int | None = None) -> dict[str, Any]:
        samples = await self._load_telemetry_samples(
            project_id=project_id,
            scope_type="NODE",
            window=window,
            instance_id=instance_id,
        )
        grouped: dict[str, list[dict[str, Any]]] = {}
        latest: dict[str, dict[str, Any]] = {}
        for item in samples:
            payload = item.metrics_payload or {}
            point = {
                "sample_at": _to_iso(item.sample_at),
                "cpu_pct": float(payload.get("cpu_pct") or 0),
                "memory_pct": float(payload.get("memory_pct") or 0),
                "disk_throughput_mb": float(payload.get("disk_throughput_mb") or 0),
                "network_throughput_mb": float(payload.get("network_throughput_mb") or 0),
                "queue_backlog": int(payload.get("queue_backlog") or 0),
                "health": str(payload.get("health") or "HEALTHY"),
                "role": str(payload.get("role") or "scanner"),
            }
            grouped.setdefault(item.scope_key, []).append(point)
            latest[item.scope_key] = {
                "scope_key": item.scope_key,
                "node_name": str(payload.get("node_name") or item.scope_key),
                "role": point["role"],
                "health": point["health"],
                "cpu_pct": point["cpu_pct"],
                "memory_pct": point["memory_pct"],
                "disk_throughput_mb": point["disk_throughput_mb"],
                "network_throughput_mb": point["network_throughput_mb"],
                "queue_backlog": point["queue_backlog"],
            }
        return {"series": grouped, "latest": list(latest.values())}

    async def get_instance_telemetry(self, *, project_id: int, instance_id: int, window: str = "24h") -> dict[str, Any]:
        await self._get_instance(project_id, instance_id)
        source = await self.get_source_series(project_id=project_id, window=window, instance_id=instance_id)
        nodes = await self.get_node_series(project_id=project_id, window=window, instance_id=instance_id)
        return {
            "overview": next((item for item in source["latest"] if item["instance_id"] == instance_id), None),
            "source_series": source["series"],
            "node_series": nodes["series"],
            "latest_nodes": nodes["latest"],
        }

    async def _run_connection_test(self, connector_key: str, runtime_family: str, config: dict[str, Any]) -> str:
        if connector_key == "mysql":
            conn = await aiomysql.connect(
                host=str(config.get("host", "localhost")),
                port=int(config.get("port", 3306)),
                user=str(config.get("username", "")),
                password=str(config.get("password", "")),
                db=str(config.get("database") or "") or None,
                autocommit=True,
            )
            try:
                async with conn.cursor() as cursor:
                    await cursor.execute("select 1")
                    await cursor.fetchone()
            finally:
                conn.close()
            return "MySQL 连接成功"
        if connector_key == "postgresql":
            conn = await asyncpg.connect(
                host=str(config.get("host", "localhost")),
                port=int(config.get("port", 5432)),
                user=str(config.get("username", "")),
                password=str(config.get("password", "")),
                database=str(config.get("database") or "postgres"),
            )
            try:
                await conn.fetchval("select 1")
            finally:
                await conn.close()
            return "PostgreSQL 连接成功"
        if connector_key == "sqlite":
            file_path = Path(str(config.get("file_path") or "").strip())
            if not file_path.exists():
                raise ValueError(f"SQLite 文件不存在: {file_path}")
            conn = sqlite3.connect(str(file_path))
            try:
                conn.execute("select 1")
            finally:
                conn.close()
            return "SQLite 连接成功"
        if connector_key == "csv":
            file_path = self._resolve_local_path(config, key="path", label="CSV")
            self._read_csv_profile(config, file_path)
            return "CSV 文件可用"
        if connector_key == "kafka":
            return await self._test_kafka(config)
        if connector_key == "mongodb":
            return await self._test_mongodb(config)
        if connector_key == "s3":
            return await self._test_s3(config)
        raise ValueError(f"{runtime_family} 连接器暂未提供连接测试实现")

    async def _discover_assets(self, connector_key: str, runtime_family: str, config: dict[str, Any]) -> dict[str, Any]:
        if connector_key == "mysql":
            return await self._discover_mysql(config)
        if connector_key == "postgresql":
            return await self._discover_postgresql(config)
        if connector_key == "sqlite":
            return await self._discover_sqlite(config)
        if connector_key == "csv":
            return await self._discover_csv(config)
        if connector_key == "kafka":
            return await self._discover_kafka(config)
        if connector_key == "mongodb":
            return await self._discover_mongodb(config)
        if connector_key == "s3":
            return await self._discover_s3(config)
        raise ValueError(f"{runtime_family} 连接器暂未提供发现实现")

    async def _discover_mysql(self, config: dict[str, Any]) -> dict[str, Any]:
        conn = await aiomysql.connect(
            host=str(config.get("host", "localhost")),
            port=int(config.get("port", 3306)),
            user=str(config.get("username", "")),
            password=str(config.get("password", "")),
            autocommit=True,
        )
        focus_database = str(config.get("database") or "").strip()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute("select schema_name from information_schema.schemata order by schema_name")
                databases = [
                    str(row.get("schema_name") or row.get("SCHEMA_NAME") or "")
                    for row in await cursor.fetchall()
                    if str(row.get("schema_name") or row.get("SCHEMA_NAME") or "") not in SYSTEM_MYSQL_SCHEMAS
                ]
                if focus_database:
                    databases = [item for item in databases if item == focus_database]
                assets: list[dict[str, Any]] = []
                for database_name in databases[:25]:
                    assets.append(
                        {
                            "asset_type": "DATABASE",
                            "asset_key": f"database:{database_name}",
                            "qualified_name": database_name,
                            "display_name": database_name,
                            "schema_payload": {"database": database_name},
                            "metrics_payload": {"row_count_estimate": 0, "estimated_bytes": 0, "column_count": 0, "update_mode": "PERIODIC_FULL"},
                        }
                    )
                    await cursor.execute(
                        """
                        select table_name
                        from information_schema.tables
                        where table_schema = %s and table_type = 'BASE TABLE'
                        order by table_name
                        limit 50
                        """,
                        (database_name,),
                    )
                    tables = await cursor.fetchall()
                    db_rows = 0
                    for table_row in tables:
                        table_name = str(table_row.get("table_name") or table_row.get("TABLE_NAME") or "")
                        await cursor.execute(
                            """
                            select column_name, data_type, is_nullable
                            from information_schema.columns
                            where table_schema = %s and table_name = %s
                            order by ordinal_position
                            """,
                            (database_name, table_name),
                        )
                        columns = await cursor.fetchall()
                        await cursor.execute(f"select count(*) as row_count from `{database_name}`.`{table_name}`")
                        count_row = await cursor.fetchone()
                        normalized = [
                            {
                                "name": str(item.get("column_name") or item.get("COLUMN_NAME") or ""),
                                "data_type": str(item.get("data_type") or item.get("DATA_TYPE") or "TEXT"),
                                "nullable": str(item.get("is_nullable") or item.get("IS_NULLABLE") or "").upper() == "YES",
                            }
                            for item in columns
                        ]
                        row_count = int((count_row or {}).get("row_count") or (count_row or {}).get("ROW_COUNT") or 0)
                        db_rows += row_count
                        assets.append(
                            {
                                "asset_type": "TABLE",
                                "asset_key": f"table:{database_name}.{table_name}",
                                "qualified_name": f"{database_name}.{table_name}",
                                "display_name": table_name,
                                "schema_payload": {"database": database_name, "table": table_name, "columns": normalized},
                                "metrics_payload": {
                                    "row_count_estimate": row_count,
                                    "estimated_bytes": row_count * max(len(normalized), 1) * 48,
                                    "column_count": len(normalized),
                                    "update_mode": _infer_update_mode(normalized, row_count),
                                },
                            }
                        )
                    assets[-(len(tables) + 1)]["metrics_payload"] = {
                        "row_count_estimate": db_rows,
                        "estimated_bytes": db_rows * 48,
                        "column_count": len(tables),
                        "update_mode": "PERIODIC_FULL",
                    }
                return {"assets": assets}
        finally:
            conn.close()

    async def _discover_postgresql(self, config: dict[str, Any]) -> dict[str, Any]:
        database_name = str(config.get("database") or "postgres")
        schema_name = str(config.get("schema") or "public")
        conn = await asyncpg.connect(
            host=str(config.get("host", "localhost")),
            port=int(config.get("port", 5432)),
            user=str(config.get("username", "")),
            password=str(config.get("password", "")),
            database=database_name,
        )
        try:
            db_rows = await conn.fetch("select datname from pg_database where datistemplate = false order by datname")
            assets: list[dict[str, Any]] = [
                {
                    "asset_type": "DATABASE",
                    "asset_key": f"database:{row['datname']}",
                    "qualified_name": str(row["datname"]),
                    "display_name": str(row["datname"]),
                    "schema_payload": {"database": str(row["datname"])},
                    "metrics_payload": {"row_count_estimate": 0, "estimated_bytes": 0, "column_count": 0, "update_mode": "PERIODIC_FULL"},
                }
                for row in db_rows
            ]
            tables = await conn.fetch(
                """
                select table_name
                from information_schema.tables
                where table_schema = $1 and table_type = 'BASE TABLE'
                order by table_name
                limit 50
                """,
                schema_name,
            )
            for row in tables:
                table_name = str(row["table_name"])
                columns = await conn.fetch(
                    """
                    select column_name, data_type, is_nullable
                    from information_schema.columns
                    where table_schema = $1 and table_name = $2
                    order by ordinal_position
                    """,
                    schema_name,
                    table_name,
                )
                count_row = await conn.fetchrow(f'select count(*)::bigint as row_count from "{schema_name}"."{table_name}"')
                normalized = [
                    {"name": str(item["column_name"]), "data_type": str(item["data_type"]), "nullable": str(item["is_nullable"]).upper() == "YES"}
                    for item in columns
                ]
                row_count = int(count_row["row_count"] if count_row else 0)
                assets.append(
                    {
                        "asset_type": "TABLE",
                        "asset_key": f"table:{database_name}.{schema_name}.{table_name}",
                        "qualified_name": f"{database_name}.{schema_name}.{table_name}",
                        "display_name": table_name,
                        "schema_payload": {"database": database_name, "schema": schema_name, "table": table_name, "columns": normalized},
                        "metrics_payload": {
                            "row_count_estimate": row_count,
                            "estimated_bytes": row_count * max(len(normalized), 1) * 48,
                            "column_count": len(normalized),
                            "update_mode": _infer_update_mode(normalized, row_count),
                        },
                    }
                )
            return {"assets": assets}
        finally:
            await conn.close()

    async def _discover_sqlite(self, config: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(str(config.get("file_path") or "").strip())
        if not file_path.exists():
            raise ValueError(f"SQLite 文件不存在: {file_path}")
        conn = sqlite3.connect(str(file_path))
        try:
            tables = conn.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%' order by name limit 50").fetchall()
            assets: list[dict[str, Any]] = [
                {
                    "asset_type": "DATABASE",
                    "asset_key": f"database:{file_path.name}",
                    "qualified_name": file_path.name,
                    "display_name": file_path.name,
                    "schema_payload": {"file_path": str(file_path)},
                    "metrics_payload": {"row_count_estimate": 0, "estimated_bytes": 0, "column_count": 0, "update_mode": "FULL_SNAPSHOT"},
                }
            ]
            total_rows = 0
            for (table_name,) in tables:
                columns = conn.execute(f"pragma table_info('{table_name}')").fetchall()
                row_count = int(conn.execute(f"select count(*) from '{table_name}'").fetchone()[0] or 0)
                total_rows += row_count
                normalized = [{"name": column[1], "data_type": column[2] or "TEXT", "nullable": not bool(column[3])} for column in columns]
                assets.append(
                    {
                        "asset_type": "TABLE",
                        "asset_key": f"table:{file_path.name}.{table_name}",
                        "qualified_name": f"{file_path.name}.{table_name}",
                        "display_name": table_name,
                        "schema_payload": {"database": file_path.name, "schema": "main", "table": table_name, "columns": normalized},
                        "metrics_payload": {
                            "row_count_estimate": row_count,
                            "estimated_bytes": row_count * max(len(normalized), 1) * 48,
                            "column_count": len(normalized),
                            "update_mode": _infer_update_mode(normalized, row_count),
                        },
                    }
                )
            assets[0]["metrics_payload"] = {
                "row_count_estimate": total_rows,
                "estimated_bytes": total_rows * 48,
                "column_count": len(tables),
                "update_mode": "FULL_SNAPSHOT",
            }
            return {"assets": assets}
        finally:
            conn.close()

    async def _discover_csv(self, config: dict[str, Any]) -> dict[str, Any]:
        path = self._resolve_local_path(config, key="path", label="CSV")
        files = sorted(candidate for candidate in ([path] if path.is_file() else path.rglob("*.csv")) if candidate.is_file())[:200]
        if not files:
            raise ValueError(f"CSV 路径下没有可用文件: {path}")

        assets: list[dict[str, Any]] = [
            {
                "asset_type": "FOLDER" if path.is_dir() else "FILESET",
                "asset_key": f"csv-root:{path}",
                "qualified_name": str(path),
                "display_name": path.name,
                "schema_payload": {"path": str(path), "kind": "directory" if path.is_dir() else "file"},
                "metrics_payload": {"row_count_estimate": 0, "estimated_bytes": 0, "column_count": 0, "update_mode": "FULL_SNAPSHOT"},
            }
        ]

        total_rows = 0
        total_bytes = 0
        total_columns = 0
        for file_path in files:
            profile = self._read_csv_profile(config, file_path)
            total_rows += int(profile["row_count"])
            total_bytes += int(profile["estimated_bytes"])
            total_columns += int(profile["column_count"])
            assets.append(
                {
                    "asset_type": "FILE",
                    "asset_key": f"csv-file:{file_path}",
                    "qualified_name": str(file_path),
                    "display_name": file_path.name,
                    "schema_payload": {
                        "path": str(file_path),
                        "delimiter": profile["delimiter"],
                        "encoding": profile["encoding"],
                        "has_header": profile["has_header"],
                        "columns": profile["columns"],
                        "sample_rows": profile["sample_rows"],
                    },
                    "metrics_payload": {
                        "row_count_estimate": int(profile["row_count"]),
                        "estimated_bytes": int(profile["estimated_bytes"]),
                        "column_count": int(profile["column_count"]),
                        "update_mode": "APPEND" if int(profile["row_count"]) > 1000 else "FULL_SNAPSHOT",
                    },
                }
            )

        assets[0]["metrics_payload"] = {
            "row_count_estimate": total_rows,
            "estimated_bytes": total_bytes,
            "column_count": total_columns,
            "update_mode": "FULL_SNAPSHOT",
        }
        return {"assets": assets}

    def _resolve_local_path(self, config: dict[str, Any], *, key: str, label: str) -> Path:
        raw = str(config.get(key) or "").strip()
        if not raw:
            raise ValueError(f"{label} 路径不能为空")
        path = Path(raw)
        if not path.exists():
            raise ValueError(f"{label} 路径不存在: {path}")
        return path

    def _read_csv_profile(self, config: dict[str, Any], file_path: Path) -> dict[str, Any]:
        if not file_path.is_file():
            raise ValueError(f"CSV 路径不是文件: {file_path}")
        delimiter = str(config.get("delimiter") or ",")[:1] or ","
        encoding = str(config.get("encoding") or "utf-8").strip() or "utf-8"
        has_header = str(config.get("has_header") or "true").strip().lower() not in {"false", "0", "no"}

        with file_path.open("r", encoding=encoding, newline="") as handle:
            reader = csv.reader(handle, delimiter=delimiter)
            rows = list(reader)

        if not rows:
            columns: list[dict[str, Any]] = []
            sample_rows: list[dict[str, Any]] = []
            row_count = 0
        else:
            if has_header:
                header = [str(item).strip() or f"column_{index + 1}" for index, item in enumerate(rows[0])]
                data_rows = rows[1:]
            else:
                header = [f"column_{index + 1}" for index in range(len(rows[0]))]
                data_rows = rows
            row_count = len(data_rows)
            columns = [{"name": name, "data_type": "TEXT", "nullable": True} for name in header]
            sample_rows = [{header[index]: (row[index] if index < len(row) else "") for index in range(len(header))} for row in data_rows[:5]]

        return {
            "delimiter": delimiter,
            "encoding": encoding,
            "has_header": has_header,
            "row_count": row_count,
            "estimated_bytes": file_path.stat().st_size,
            "column_count": len(columns),
            "columns": columns,
            "sample_rows": sample_rows,
        }

    async def _test_kafka(self, config: dict[str, Any]) -> str:
        from kafka import KafkaConsumer

        def _run() -> str:
            consumer = KafkaConsumer(
                bootstrap_servers=str(config.get("bootstrap_servers") or "127.0.0.1:9092"),
                security_protocol=str(config.get("security_protocol") or "PLAINTEXT"),
                request_timeout_ms=5000,
                api_version_auto_timeout_ms=5000,
                consumer_timeout_ms=1000,
            )
            try:
                consumer.topics()
            finally:
                consumer.close()
            return "Kafka 连接成功"

        return await asyncio.to_thread(_run)

    async def _discover_kafka(self, config: dict[str, Any]) -> dict[str, Any]:
        from kafka import KafkaConsumer

        def _run() -> dict[str, Any]:
            consumer = KafkaConsumer(
                bootstrap_servers=str(config.get("bootstrap_servers") or "127.0.0.1:9092"),
                security_protocol=str(config.get("security_protocol") or "PLAINTEXT"),
                request_timeout_ms=5000,
                api_version_auto_timeout_ms=5000,
                consumer_timeout_ms=1000,
            )
            try:
                topics = sorted(consumer.topics())
                assets: list[dict[str, Any]] = [
                    {
                        "asset_type": "CLUSTER",
                        "asset_key": f"cluster:{str(config.get('bootstrap_servers') or '127.0.0.1:9092')}",
                        "qualified_name": str(config.get("bootstrap_servers") or "127.0.0.1:9092"),
                        "display_name": "Kafka Cluster",
                        "schema_payload": {"bootstrap_servers": str(config.get("bootstrap_servers") or "127.0.0.1:9092")},
                        "metrics_payload": {
                            "row_count_estimate": 0,
                            "estimated_bytes": 0,
                            "column_count": len(topics),
                            "update_mode": "APPEND",
                        },
                    }
                ]
                for topic in topics[:100]:
                    partitions = consumer.partitions_for_topic(topic) or set()
                    assets.append(
                        {
                            "asset_type": "TOPIC",
                            "asset_key": f"topic:{topic}",
                            "qualified_name": topic,
                            "display_name": topic,
                            "schema_payload": {
                                "topic": topic,
                                "partition_ids": sorted(partitions),
                            },
                            "metrics_payload": {
                                "row_count_estimate": 0,
                                "estimated_bytes": len(partitions) * 1024 * 1024,
                                "column_count": len(partitions),
                                "update_mode": "APPEND",
                            },
                        }
                    )
                return {"assets": assets}
            finally:
                consumer.close()

        return await asyncio.to_thread(_run)

    async def _test_mongodb(self, config: dict[str, Any]) -> str:
        from pymongo import MongoClient

        def _run() -> str:
            client = MongoClient(str(config.get("uri") or "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=5000)
            try:
                client.admin.command("ping")
            finally:
                client.close()
            return "MongoDB 连接成功"

        return await asyncio.to_thread(_run)

    async def _discover_mongodb(self, config: dict[str, Any]) -> dict[str, Any]:
        from pymongo import MongoClient

        def _infer_document_schema(document: dict[str, Any] | None) -> list[dict[str, Any]]:
            if not document:
                return []
            columns: list[dict[str, Any]] = []
            for key, value in document.items():
                dtype = type(value).__name__.upper()
                columns.append({"name": str(key), "data_type": dtype, "nullable": value is None})
            return columns

        def _run() -> dict[str, Any]:
            client = MongoClient(str(config.get("uri") or "mongodb://127.0.0.1:27017"), serverSelectionTimeoutMS=5000)
            focus_database = str(config.get("database") or "").strip()
            try:
                database_names = [name for name in client.list_database_names() if name not in SYSTEM_MONGO_DATABASES]
                if focus_database:
                    database_names = [name for name in database_names if name == focus_database]
                assets: list[dict[str, Any]] = []
                for database_name in database_names[:25]:
                    database = client[database_name]
                    collection_names = database.list_collection_names()
                    assets.append(
                        {
                            "asset_type": "DATABASE",
                            "asset_key": f"database:{database_name}",
                            "qualified_name": database_name,
                            "display_name": database_name,
                            "schema_payload": {"database": database_name},
                            "metrics_payload": {
                                "row_count_estimate": 0,
                                "estimated_bytes": 0,
                                "column_count": len(collection_names),
                                "update_mode": "UPSERT",
                            },
                        }
                    )
                    total_docs = 0
                    total_bytes = 0
                    for collection_name in collection_names[:100]:
                        stats = database.command("collStats", collection_name)
                        row_count = int(stats.get("count") or 0)
                        storage_size = int(stats.get("storageSize") or 0)
                        sample_doc = database[collection_name].find_one()
                        columns = _infer_document_schema(sample_doc)
                        total_docs += row_count
                        total_bytes += storage_size
                        assets.append(
                            {
                                "asset_type": "COLLECTION",
                                "asset_key": f"collection:{database_name}.{collection_name}",
                                "qualified_name": f"{database_name}.{collection_name}",
                                "display_name": collection_name,
                                "schema_payload": {"database": database_name, "collection": collection_name, "columns": columns},
                                "metrics_payload": {
                                    "row_count_estimate": row_count,
                                    "estimated_bytes": storage_size,
                                    "column_count": len(columns),
                                    "update_mode": _infer_update_mode(columns, row_count),
                                },
                            }
                        )
                    assets[-(len(collection_names) + 1)]["metrics_payload"] = {
                        "row_count_estimate": total_docs,
                        "estimated_bytes": total_bytes,
                        "column_count": len(collection_names),
                        "update_mode": "UPSERT",
                    }
                return {"assets": assets}
            finally:
                client.close()

        return await asyncio.to_thread(_run)

    async def _test_s3(self, config: dict[str, Any]) -> str:
        import boto3

        def _run() -> str:
            client = boto3.client(
                "s3",
                endpoint_url=str(config.get("endpoint_url") or "").strip() or None,
                aws_access_key_id=str(config.get("access_key_id") or ""),
                aws_secret_access_key=str(config.get("secret_access_key") or ""),
                region_name=str(config.get("region_name") or "us-east-1"),
            )
            bucket = str(config.get("bucket") or "").strip()
            if bucket:
                client.head_bucket(Bucket=bucket)
            else:
                client.list_buckets()
            return "对象存储连接成功"

        return await asyncio.to_thread(_run)

    async def _discover_s3(self, config: dict[str, Any]) -> dict[str, Any]:
        import boto3

        def _run() -> dict[str, Any]:
            client = boto3.client(
                "s3",
                endpoint_url=str(config.get("endpoint_url") or "").strip() or None,
                aws_access_key_id=str(config.get("access_key_id") or ""),
                aws_secret_access_key=str(config.get("secret_access_key") or ""),
                region_name=str(config.get("region_name") or "us-east-1"),
            )
            bucket = str(config.get("bucket") or "").strip()
            prefix = str(config.get("prefix") or "").strip()
            if bucket:
                buckets = [bucket]
            else:
                buckets = [item["Name"] for item in client.list_buckets().get("Buckets", [])]
            assets: list[dict[str, Any]] = []
            for bucket_name in buckets[:25]:
                paginator = client.get_paginator("list_objects_v2")
                object_count = 0
                total_size = 0
                assets.append(
                    {
                        "asset_type": "BUCKET",
                        "asset_key": f"bucket:{bucket_name}",
                        "qualified_name": bucket_name,
                        "display_name": bucket_name,
                        "schema_payload": {"bucket": bucket_name, "prefix": prefix},
                        "metrics_payload": {
                            "row_count_estimate": 0,
                            "estimated_bytes": 0,
                            "column_count": 0,
                            "update_mode": "PERIODIC_FULL",
                        },
                    }
                )
                pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix or "", PaginationConfig={"MaxItems": 100})
                for page in pages:
                    for obj in page.get("Contents", [])[:100]:
                        key = str(obj.get("Key") or "")
                        size = int(obj.get("Size") or 0)
                        object_count += 1
                        total_size += size
                        assets.append(
                            {
                                "asset_type": "OBJECT",
                                "asset_key": f"object:{bucket_name}/{key}",
                                "qualified_name": f"{bucket_name}/{key}",
                                "display_name": key.split("/")[-1] or key,
                                "schema_payload": {"bucket": bucket_name, "key": key},
                                "metrics_payload": {
                                    "row_count_estimate": 1,
                                    "estimated_bytes": size,
                                    "column_count": 0,
                                    "update_mode": "FULL_SNAPSHOT",
                                },
                            }
                        )
                assets[-(object_count + 1)]["metrics_payload"] = {
                    "row_count_estimate": object_count,
                    "estimated_bytes": total_size,
                    "column_count": object_count,
                    "update_mode": "PERIODIC_FULL",
                }
            return {"assets": assets}

        return await asyncio.to_thread(_run)

    def _extract_field_rows(self, asset: SourceAsset, schema_payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        columns = schema_payload.get("columns") or []
        for index, column in enumerate(columns, start=1):
            name = str(column.get("name") or "").strip()
            if not name:
                continue
            lowered = name.lower()
            rows.append(
                {
                    "field_key": f"{asset.asset_key}:{name}",
                    "field_name": name,
                    "display_name": name,
                    "physical_type": str(column.get("data_type") or "TEXT"),
                    "nullable": bool(column.get("nullable", True)),
                    "ordinal_position": int(column.get("ordinal_position") or index),
                    "is_partition_key": bool(column.get("is_partition_key") or any(token in lowered for token in ("partition", "dt"))),
                    "is_primary_key_candidate": lowered == "id" or lowered.endswith("_id"),
                    "is_time_field_candidate": any(token in lowered for token in ("time", "date", "created", "updated")),
                }
            )
        return rows

    def _build_field_profile_payload(
        self,
        *,
        field_row: dict[str, Any],
        asset_metrics: dict[str, Any],
        asset_schema: dict[str, Any],
    ) -> dict[str, Any]:
        field_name = str(field_row["field_name"])
        lowered = field_name.lower()
        row_count = int(asset_metrics.get("row_count_estimate") or 0)
        sample_rows = asset_schema.get("sample_rows") or []
        sample_values = []
        for item in sample_rows[:5]:
            if isinstance(item, dict) and field_name in item and item[field_name] not in (None, ""):
                sample_values.append(str(item[field_name]))
        distinct_ratio = 0.92 if field_row["is_primary_key_candidate"] else 0.65 if "status" in lowered else 0.18
        null_ratio = 0.0 if field_row["is_primary_key_candidate"] else 0.05 if not field_row["nullable"] else 0.25
        return {
            "null_ratio": null_ratio,
            "distinct_ratio": distinct_ratio,
            "sample_values": sample_values,
            "min_value": sample_values[0] if sample_values else None,
            "max_value": sample_values[-1] if sample_values else None,
            "observed_row_count": row_count,
            "profile_payload": {
                "inference_mode": "derived",
                "data_type": field_row["physical_type"],
                "sample_count": len(sample_values),
            },
        }

    def _build_semantic_candidates(
        self,
        *,
        instance: SourceInstance,
        asset: SourceAsset,
        field: SourceField,
        profile_payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        if field.is_primary_key_candidate:
            candidates.append(
                {
                    "project_id": instance.project_id,
                    "instance_id": instance.id,
                    "asset_id": asset.id,
                    "field_id": field.id,
                    "object_type": "FIELD",
                    "candidate_type": "IDENTITY_FIELD",
                    "candidate_value": field.field_name,
                    "confidence": 0.92,
                    "reasoning": "字段名匹配 id/_id，且 distinct_ratio 较高。",
                    "evidence_payload": {
                        "field_key": field.field_key,
                        "distinct_ratio": profile_payload["distinct_ratio"],
                        "null_ratio": profile_payload["null_ratio"],
                    },
                    "status": "PENDING",
                }
            )
        if field.is_time_field_candidate:
            candidates.append(
                {
                    "project_id": instance.project_id,
                    "instance_id": instance.id,
                    "asset_id": asset.id,
                    "field_id": field.id,
                    "object_type": "FIELD",
                    "candidate_type": "TIME_FIELD",
                    "candidate_value": field.field_name,
                    "confidence": 0.88,
                    "reasoning": "字段名包含 time/date/created/updated，适合作为时间裁剪依据。",
                    "evidence_payload": {"field_key": field.field_key},
                    "status": "PENDING",
                }
            )
        if "status" in field.field_name.lower():
            candidates.append(
                {
                    "project_id": instance.project_id,
                    "instance_id": instance.id,
                    "asset_id": asset.id,
                    "field_id": field.id,
                    "object_type": "FIELD",
                    "candidate_type": "STATUS_FIELD",
                    "candidate_value": field.field_name,
                    "confidence": 0.74,
                    "reasoning": "字段名包含 status，通常用于状态枚举或生命周期跟踪。",
                    "evidence_payload": {"field_key": field.field_key},
                    "status": "PENDING",
                }
            )
        return candidates

    async def _sync_asset_fields(
        self,
        *,
        instance: SourceInstance,
        asset: SourceAsset,
        snapshot: SourceAssetSnapshot,
    ) -> dict[str, int]:
        schema_payload = asset.schema_payload or {}
        metrics_payload = asset.metrics_payload or {}
        field_rows = self._extract_field_rows(asset, schema_payload)
        existing_result = await self.db.execute(select(SourceField).where(SourceField.asset_id == asset.id))
        existing = {item.field_key: item for item in existing_result.scalars().all()}
        seen: set[str] = set()
        semantic_count = 0
        for row in field_rows:
            seen.add(row["field_key"])
            field = existing.get(row["field_key"])
            field_payload = {
                "project_id": instance.project_id,
                "instance_id": instance.id,
                "asset_id": asset.id,
                "field_key": row["field_key"],
                "field_name": row["field_name"],
                "display_name": row["display_name"],
                "physical_type": row["physical_type"],
                "nullable": row["nullable"],
                "ordinal_position": row["ordinal_position"],
                "status": "DISCOVERED",
                "is_partition_key": row["is_partition_key"],
                "is_primary_key_candidate": row["is_primary_key_candidate"],
                "is_time_field_candidate": row["is_time_field_candidate"],
                "discovered_from_snapshot_id": snapshot.id,
                "last_seen_at": _utcnow(),
            }
            if field is None:
                field = await self.field_repo.create(field_payload)
            else:
                await self.field_repo.update(field, field_payload)
            profile_payload = self._build_field_profile_payload(
                field_row=row,
                asset_metrics=metrics_payload,
                asset_schema=schema_payload,
            )
            await self.field_profile_repo.create(
                {
                    "project_id": instance.project_id,
                    "field_id": field.id,
                    "asset_id": asset.id,
                    "snapshot_id": snapshot.id,
                    **profile_payload,
                    "profiled_at": _utcnow(),
                }
            )
            existing_candidate_result = await self.db.execute(
                select(SemanticCandidate).where(
                    SemanticCandidate.project_id == instance.project_id,
                    SemanticCandidate.field_id == field.id,
                )
            )
            for existing_candidate in existing_candidate_result.scalars().all():
                await self.db.delete(existing_candidate)
            semantic_payloads = self._build_semantic_candidates(
                instance=instance,
                asset=asset,
                field=field,
                profile_payload=profile_payload,
            )
            semantic_count += len(semantic_payloads)
            for semantic_payload in semantic_payloads:
                await self.semantic_candidate_repo.create(semantic_payload)
        for field_key, field in existing.items():
            if field_key not in seen:
                await self.field_repo.update(field, {"status": "MISSING"})
        return {"field_count": len(field_rows), "semantic_candidate_count": semantic_count}

    async def _apply_discovery(
        self,
        *,
        project_id: int,
        instance: SourceInstance,
        connector: ConnectorDefinition,
        discovery: dict[str, Any],
    ) -> dict[str, Any]:
        result = await self.db.execute(select(SourceAsset).where(SourceAsset.instance_id == instance.id))
        existing = {item.asset_key: item for item in result.scalars().all()}
        changes: list[dict[str, Any]] = []
        candidates: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in discovery.get("assets", []):
            seen.add(str(item["asset_key"]))
            schema_payload = item.get("schema_payload") or {}
            metrics_payload = item.get("metrics_payload") or {}
            metrics_payload = {**metrics_payload, "signature": _json_signature(schema_payload, metrics_payload)}
            asset = existing.get(str(item["asset_key"]))
            if asset is None:
                asset = await self.asset_repo.create(
                    {
                        "project_id": project_id,
                        "instance_id": instance.id,
                        "asset_key": item["asset_key"],
                        "asset_type": item["asset_type"],
                        "qualified_name": item["qualified_name"],
                        "display_name": item["display_name"],
                        "status": "DISCOVERED",
                        "heat_level": _heat_level(int(metrics_payload.get("row_count_estimate") or 0)),
                        "inferred_domain": _infer_domain(str(item["qualified_name"])),
                        "last_seen_at": _utcnow(),
                        "schema_payload": schema_payload,
                        "metrics_payload": metrics_payload,
                    }
                )
                snapshot = await self.snapshot_repo.create(
                    {
                        "project_id": project_id,
                        "instance_id": instance.id,
                        "asset_id": asset.id,
                        "snapshot_type": "DISCOVERY",
                        "schema_payload": schema_payload,
                        "stats_payload": metrics_payload,
                        "captured_at": _utcnow(),
                    }
                )
                field_summary = await self._sync_asset_fields(instance=instance, asset=asset, snapshot=snapshot)
                metrics_payload = {
                    **metrics_payload,
                    "field_count": field_summary["field_count"],
                    "semantic_candidate_count": field_summary["semantic_candidate_count"],
                    "signature": _json_signature(schema_payload, {**metrics_payload, **field_summary}),
                }
                await self.asset_repo.update(asset, {"metrics_payload": metrics_payload})
                change = await self.change_repo.create(
                    {
                        "project_id": project_id,
                        "instance_id": instance.id,
                        "asset_id": asset.id,
                        "event_type": "ASSET_DISCOVERED",
                        "severity": "MEDIUM",
                        "status": "OPEN",
                        "title": f"发现新资产：{asset.qualified_name}",
                        "summary": f"{connector.display_name} 实例 {instance.instance_name} 发现新的 {asset.asset_type} 资产 {asset.qualified_name}。",
                        "recommended_action": "PROMOTE_TO_PROJECT",
                        "detail_payload": {"asset_key": asset.asset_key},
                        "brief_payload": {"instance_name": instance.instance_name, "asset_name": asset.qualified_name},
                        "detected_at": _utcnow(),
                    }
                )
                candidate = await self.candidate_repo.create(
                    {
                        "project_id": project_id,
                        "instance_id": instance.id,
                        "asset_id": asset.id,
                        "change_event_id": change.id,
                        "candidate_type": "NEW_ASSET",
                        "status": "OPEN",
                        "title": f"待纳管资产：{asset.qualified_name}",
                        "summary": "建议先确认该资产的业务价值，再决定纳入当前项目记忆或提升为公共记忆。",
                        "recommendation": "PROMOTE_TO_PROJECT",
                        "memory_scope_target": instance.memory_scope_default,
                        "action_payload": {"asset_key": asset.asset_key},
                    }
                )
                changes.append(self._serialize_change_event(change))
                candidates.append(await self._serialize_candidate(candidate))
                continue
            previous_signature = str((asset.metrics_payload or {}).get("signature") or "")
            await self.asset_repo.update(
                asset,
                {
                    "asset_type": item["asset_type"],
                    "qualified_name": item["qualified_name"],
                    "display_name": item["display_name"],
                    "status": "DISCOVERED" if asset.status == "MISSING" else asset.status,
                    "heat_level": _heat_level(int(metrics_payload.get("row_count_estimate") or 0)),
                    "inferred_domain": _infer_domain(str(item["qualified_name"])),
                    "last_seen_at": _utcnow(),
                    "schema_payload": schema_payload,
                    "metrics_payload": metrics_payload,
                },
            )
            snapshot = await self.snapshot_repo.create(
                {
                    "project_id": project_id,
                    "instance_id": instance.id,
                    "asset_id": asset.id,
                    "snapshot_type": "DISCOVERY",
                    "schema_payload": schema_payload,
                    "stats_payload": metrics_payload,
                    "captured_at": _utcnow(),
                }
            )
            field_summary = await self._sync_asset_fields(instance=instance, asset=asset, snapshot=snapshot)
            metrics_payload = {
                **metrics_payload,
                "field_count": field_summary["field_count"],
                "semantic_candidate_count": field_summary["semantic_candidate_count"],
                "signature": _json_signature(schema_payload, {**metrics_payload, **field_summary}),
            }
            await self.asset_repo.update(asset, {"metrics_payload": metrics_payload})
            if previous_signature and previous_signature != metrics_payload["signature"]:
                change = await self.change_repo.create(
                    {
                        "project_id": project_id,
                        "instance_id": instance.id,
                        "asset_id": asset.id,
                        "event_type": "ASSET_CHANGED",
                        "severity": "MEDIUM",
                        "status": "OPEN",
                        "title": f"资产结构发生变化：{asset.qualified_name}",
                        "summary": "检测到该资产的结构或统计信息发生变化，建议复核是否影响当前主题域、查询规划或契约。",
                        "recommended_action": "REVIEW_CHANGE",
                        "detail_payload": {"before_signature": previous_signature, "after_signature": metrics_payload["signature"]},
                        "brief_payload": {"instance_name": instance.instance_name, "asset_name": asset.qualified_name},
                        "detected_at": _utcnow(),
                    }
                )
                candidate = await self.candidate_repo.create(
                    {
                        "project_id": project_id,
                        "instance_id": instance.id,
                        "asset_id": asset.id,
                        "change_event_id": change.id,
                        "candidate_type": "ASSET_CHANGE",
                        "status": "OPEN",
                        "title": f"待确认变化：{asset.qualified_name}",
                        "summary": "建议确认本次变化是否需要写入项目记忆，或提升为公共记忆供同租户项目共享。",
                        "recommendation": "PROMOTE_TO_PROJECT",
                        "memory_scope_target": instance.memory_scope_default,
                        "action_payload": {"asset_key": asset.asset_key},
                    }
                )
                changes.append(self._serialize_change_event(change))
                candidates.append(await self._serialize_candidate(candidate))
        for asset_key, asset in existing.items():
            if asset_key in seen:
                continue
            await self.asset_repo.update(asset, {"status": "MISSING"})
            change = await self.change_repo.create(
                {
                    "project_id": project_id,
                    "instance_id": instance.id,
                    "asset_id": asset.id,
                    "event_type": "ASSET_REMOVED",
                    "severity": "HIGH",
                    "status": "OPEN",
                    "title": f"资产已消失：{asset.qualified_name}",
                    "summary": "本次发现未再检索到该资产，建议确认是否已下线、改名或迁移到其他实例。",
                    "recommended_action": "DISMISS_OR_REVIEW",
                    "detail_payload": {"asset_key": asset.asset_key},
                    "brief_payload": {"instance_name": instance.instance_name, "asset_name": asset.qualified_name},
                    "detected_at": _utcnow(),
                }
            )
            candidate = await self.candidate_repo.create(
                {
                    "project_id": project_id,
                    "instance_id": instance.id,
                    "asset_id": asset.id,
                    "change_event_id": change.id,
                    "candidate_type": "ASSET_REMOVED",
                    "status": "OPEN",
                    "title": f"待处理下线资产：{asset.qualified_name}",
                    "summary": "建议确认是否从项目记忆中归档该资产，或保留为历史参考记录。",
                    "recommendation": "DISMISS",
                    "memory_scope_target": instance.memory_scope_default,
                    "action_payload": {"asset_key": asset.asset_key},
                }
            )
            changes.append(self._serialize_change_event(change))
            candidates.append(await self._serialize_candidate(candidate))
        return {"changes": changes, "candidates": candidates}

    def _build_brief(self, instance_name: str, connector_name: str, discovery: dict[str, Any], changes: list[dict[str, Any]]) -> dict[str, Any]:
        assets = discovery.get("assets", [])
        containers = [item for item in assets if item.get("asset_type") in {"DATABASE", "BUCKET", "CLUSTER"}]
        data_assets = [item for item in assets if item.get("asset_type") not in {"DATABASE", "BUCKET", "CLUSTER"}]
        hot_assets = sorted(
            data_assets,
            key=lambda item: int((item.get("metrics_payload") or {}).get("row_count_estimate") or 0),
            reverse=True,
        )[:3]
        domains = sorted({_infer_domain(str(item.get("qualified_name") or "")) for item in data_assets})
        return {
            "title": f"{instance_name} 发现简报",
            "summary": f"{connector_name} 实例 {instance_name} 本次发现 {len(containers)} 个容器级资产、{len(data_assets)} 个可分析资产，并生成 {len(changes)} 条待处理变化。",
            "metrics": {"database_count": len(containers), "asset_count": len(assets), "change_count": len(changes)},
            "hot_assets": [
                {
                    "qualified_name": item.get("qualified_name"),
                    "row_count_estimate": int((item.get("metrics_payload") or {}).get("row_count_estimate") or 0),
                    "heat_level": _heat_level(int((item.get("metrics_payload") or {}).get("row_count_estimate") or 0)),
                }
                for item in hot_assets
            ],
            "domains": domains[:5],
            "recommended_actions": ["查看候选变化并确认纳管范围", "将高价值资产提升为项目记忆或公共记忆"],
        }

    async def _record_source_sample(self, instance: SourceInstance, label: str, load_score: float, throughput: float, failure_rate: float) -> None:
        await self.telemetry_repo.create(
            {
                "project_id": instance.project_id,
                "instance_id": instance.id,
                "scope_type": "SOURCE",
                "scope_key": f"source:{instance.id}",
                "sample_at": _utcnow(),
                "metrics_payload": {
                    "instance_name": instance.instance_name,
                    "label": label,
                    "heat_level": "COLD",
                    "load_score": load_score,
                    "throughput_mb_per_hour": throughput,
                    "scan_duration_ms": 0,
                    "failure_rate": failure_rate,
                },
            }
        )

    async def _record_telemetry_after_discovery(self, instance: SourceInstance, *, discovery: dict[str, Any], brief: dict[str, Any]) -> None:
        assets = [item for item in discovery.get("assets", []) if item.get("asset_type") not in {"DATABASE", "BUCKET", "CLUSTER"}]
        row_count = sum(int((item.get("metrics_payload") or {}).get("row_count_estimate") or 0) for item in assets)
        throughput = round(max(row_count, 1) * 48 / (1024 * 1024), 2)
        load_score = round(min(100.0, len(assets) * 3.5 + row_count / 20000.0), 2)
        heat_level = _heat_level(row_count)
        await self.telemetry_repo.create(
            {
                "project_id": instance.project_id,
                "instance_id": instance.id,
                "scope_type": "SOURCE",
                "scope_key": f"source:{instance.id}",
                "sample_at": _utcnow(),
                "metrics_payload": {
                    "instance_name": instance.instance_name,
                    "heat_level": heat_level,
                    "load_score": load_score,
                    "throughput_mb_per_hour": throughput,
                    "scan_duration_ms": int(brief["metrics"]["asset_count"]) * 75,
                    "failure_rate": 0,
                },
            }
        )
        for idx in range(1, 3):
            await self.telemetry_repo.create(
                {
                    "project_id": instance.project_id,
                    "instance_id": instance.id,
                    "scope_type": "NODE",
                    "scope_key": f"node:{instance.id}:{idx}",
                    "sample_at": _utcnow(),
                    "metrics_payload": {
                        "node_name": f"{instance.instance_name}-node-{idx}",
                        "role": "scanner" if idx == 1 else "planner",
                        "health": "HEALTHY" if load_score < 80 else "WARN",
                        "cpu_pct": round(min(95.0, 18 + load_score * 0.55 + idx * 3), 2),
                        "memory_pct": round(min(92.0, 22 + load_score * 0.48 + idx * 2), 2),
                        "disk_throughput_mb": round(throughput * (0.65 + idx * 0.15), 2),
                        "network_throughput_mb": round(max(throughput * 0.35, 1.0) + idx, 2),
                        "queue_backlog": max(0, len(assets) - idx * 2),
                    },
                }
            )

    async def _load_telemetry_samples(
        self,
        *,
        project_id: int,
        scope_type: str,
        window: str,
        instance_id: int | None = None,
    ) -> list[SourceTelemetrySample]:
        hours = 24 if window == "24h" else 24 * 7
        cutoff = _utcnow() - timedelta(hours=hours)
        statement = (
            select(SourceTelemetrySample)
            .where(
                SourceTelemetrySample.project_id == project_id,
                SourceTelemetrySample.scope_type == scope_type,
                SourceTelemetrySample.sample_at >= cutoff,
            )
            .order_by(SourceTelemetrySample.sample_at.asc(), SourceTelemetrySample.id.asc())
        )
        if instance_id is not None:
            statement = statement.where(SourceTelemetrySample.instance_id == instance_id)
        result = await self.db.execute(statement)
        return list(result.scalars().all())

    async def _count_candidates(self, project_id: int, statuses: set[str]) -> int:
        result = await self.db.execute(select(SourceCandidate).where(SourceCandidate.project_id == project_id))
        return sum(1 for item in result.scalars().all() if item.status in statuses)

    async def _count_changes(self, project_id: int, statuses: set[str]) -> int:
        result = await self.db.execute(select(SourceChangeEvent).where(SourceChangeEvent.project_id == project_id))
        return sum(1 for item in result.scalars().all() if item.status in statuses)

    async def _list_assets(
        self,
        *,
        project_id: int,
        q: str | None = None,
        instance_id: int | None = None,
        asset_type: str | None = None,
        heat: str | None = None,
        status: str | None = None,
        updated_since: str | None = None,
        limit: int = 25,
        offset: int = 0,
        include_total: bool = False,
    ) -> dict[str, Any] | list[dict[str, Any]]:
        result = await self.db.execute(select(SourceAsset).where(SourceAsset.project_id == project_id).order_by(SourceAsset.updated_at.desc(), SourceAsset.id.desc()))
        items = [self._serialize_asset(item) for item in result.scalars().all()]
        keyword = (q or "").strip().lower()
        if keyword:
            items = [item for item in items if keyword in item["qualified_name"].lower() or keyword in item["display_name"].lower()]
        if instance_id:
            items = [item for item in items if item["instance_id"] == instance_id]
        if asset_type and asset_type != "ALL":
            items = [item for item in items if item["asset_type"] == asset_type]
        if heat and heat != "ALL":
            items = [item for item in items if item["heat_level"] == heat]
        if status and status != "ALL":
            items = [item for item in items if item["status"] == status]
        if updated_since:
            items = [item for item in items if (item["updated_at"] or "") >= updated_since]
        if include_total:
            total = len(items)
            return {"items": items[offset : offset + limit], "total": total, "page": offset // limit + 1, "page_size": limit, "total_pages": max((total + limit - 1) // limit, 1)}
        return items[offset : offset + limit]

    async def _list_instance_briefs(self, instance_id: int, *, limit: int) -> list[dict[str, Any]]:
        result = await self.db.execute(select(SourceSyncRun).where(SourceSyncRun.instance_id == instance_id).order_by(SourceSyncRun.created_at.desc(), SourceSyncRun.id.desc()))
        items: list[dict[str, Any]] = []
        for item in result.scalars().all():
            if not item.brief_title and not item.brief_summary:
                continue
            items.append({"id": item.id, "run_type": item.run_type, "status": item.status, "title": item.brief_title, "summary": item.brief_summary, "created_at": _to_iso(item.created_at)})
            if len(items) >= limit:
                break
        return items

    async def _get_candidate(self, project_id: int, candidate_id: int) -> SourceCandidate:
        candidate = await self.candidate_repo.get(candidate_id)
        if candidate is None or candidate.project_id != project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
        return candidate

    async def _sync_candidate_memory(self, *, instance: SourceInstance, tenant_id: int | None, actor_id: str | None, user_id: int | None, memory_scope: str) -> None:
        result = await self.db.execute(select(SourceAsset).where(SourceAsset.instance_id == instance.id, SourceAsset.status.in_(["ACTIVE", "SHARED"])))
        assets = list(result.scalars().all())
        if not assets:
            return
        legacy_source = await self._upsert_legacy_source(instance, assets)
        title = f"[Source Memory] {instance.instance_name}"
        tags = ["source-memory", "source-intake", memory_scope.lower()]
        if memory_scope == "TENANT":
            tags.append("shared-memory")
        content = [f"# Source Memory: {instance.instance_name}", "", f"- Memory Scope: {memory_scope}", f"- Asset Count: {len(assets)}", "", "## Assets"]
        for asset in assets:
            metrics = asset.metrics_payload or {}
            content.extend(
                [
                    f"### {asset.qualified_name}",
                    f"- Asset Type: {asset.asset_type}",
                    f"- Domain: {asset.inferred_domain or '通用域'}",
                    f"- Heat: {asset.heat_level}",
                    f"- Rows: {metrics.get('row_count_estimate', 0)}",
                    f"- Estimated Bytes: {metrics.get('estimated_bytes', 0)}",
                    f"- Update Mode: {metrics.get('update_mode', 'FULL_SNAPSHOT')}",
                    "",
                ]
            )
        existing_result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.project_id == instance.project_id,
                KnowledgeDocument.module == "SOURCE_MEMORY",
                KnowledgeDocument.doc_type == "SOURCE_METADATA",
                KnowledgeDocument.title == title,
            )
        )
        existing = existing_result.scalar_one_or_none()
        payload = {
            "tenant_id": tenant_id,
            "summary": f"{instance.instance_name} 已同步 {len(assets)} 个资产到 AI 项目记忆。",
            "content": "\n".join(content).strip(),
            "knowledge_level": "INSTANCE",
            "status": "PUBLISHED",
            "tags": tags,
            "related_objects": (
                [
                    {"source_type": "SOURCE_INSTANCE", "source_id": str(instance.id), "label": instance.instance_name, "module": "SOURCE_INTAKE", "module_route": "/source-onboarding"},
                ]
                + (
                    [{"source_type": "DATA_SOURCE", "source_id": str(legacy_source.id), "label": legacy_source.source_name, "module": "SOURCE_ONBOARDING", "module_route": "/source-onboarding"}]
                    if legacy_source is not None
                    else []
                )
            ),
            "object_refs": [
                {"object_type": "SOURCE_INSTANCE", "object_id": instance.id, "label": instance.instance_name},
                *[
                    {"object_type": "SOURCE_ASSET", "object_id": asset.id, "label": asset.qualified_name}
                    for asset in assets[:25]
                ],
            ],
            "fact_refs": [
                {"fact_type": "SOURCE_ASSET", "fact_id": asset.id}
                for asset in assets[:25]
            ],
            "meta_payload": {"instance_id": instance.id, "legacy_source_id": legacy_source.id if legacy_source is not None else None, "memory_scope": memory_scope, "asset_ids": [asset.id for asset in assets]},
            "last_editor_id": actor_id or f"project:{instance.project_id}",
            "last_editor_user_id": user_id,
            "published_at": _utcnow(),
        }
        if existing is None:
            await self.knowledge_repo.create(
                {
                    "project_id": instance.project_id,
                    "tenant_id": tenant_id,
                    "doc_type": "SOURCE_METADATA",
                    "module": "SOURCE_MEMORY",
                    "title": title,
                    "format": "MARKDOWN",
                    "version_no": 1,
                    "comment_count": 0,
                    "author_id": actor_id or f"project:{instance.project_id}",
                    "author_user_id": user_id,
                    **payload,
                }
            )
        else:
            await self.knowledge_repo.update(existing, {**payload, "version_no": (existing.version_no or 1) + 1})

    async def _sync_source_brief_document(
        self,
        *,
        instance: SourceInstance,
        connector: ConnectorDefinition,
        tenant_id: int | None,
        actor_id: str | None,
        user_id: int | None,
        mode: str,
        summary: str,
        assets: list[Any],
        brief_payload: dict[str, Any] | None,
    ) -> None:
        title = f"[Source Brief] {instance.instance_name}"
        content = [
            f"# 源简报：{instance.instance_name}",
            "",
            f"- 连接器：{connector.display_name}",
            f"- 运行族：{connector.runtime_family}",
            f"- 当前状态：{instance.status}",
            f"- 默认记忆范围：{instance.memory_scope_default}",
            f"- 同步模式：{mode}",
            f"- 摘要：{summary}",
        ]
        if assets:
            content.extend(["", "## 已发现资产"])
            for asset in assets[:12]:
                if isinstance(asset, dict):
                    metrics = asset.get("metrics_payload") or {}
                    display_name = str(asset.get("display_name") or asset.get("qualified_name") or "-")
                    asset_type = str(asset.get("asset_type") or "-")
                    qualified_name = str(asset.get("qualified_name") or "-")
                    heat_level = str(asset.get("heat_level") or "COLD")
                    asset_id = asset.get("id")
                else:
                    metrics = asset.metrics_payload or {}
                    display_name = asset.display_name
                    asset_type = asset.asset_type
                    qualified_name = asset.qualified_name
                    heat_level = asset.heat_level
                    asset_id = asset.id
                content.extend(
                    [
                        f"### {display_name}",
                        f"- 资产类型：{asset_type}",
                        f"- 资产路径：{qualified_name}",
                        f"- 热度：{heat_level}",
                        f"- 行数估计：{metrics.get('row_count_estimate', 0)}",
                        f"- 大小估计：{metrics.get('estimated_bytes', 0)}",
                        f"- 更新方式：{metrics.get('update_mode', 'FULL_SNAPSHOT')}",
                    ]
                )
        recommended_actions = list((brief_payload or {}).get("recommended_actions") or [])
        if recommended_actions:
            content.extend(["", "## 建议动作"])
            for item in recommended_actions[:6]:
                content.append(f"- {item}")

        existing_result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.project_id == instance.project_id,
                KnowledgeDocument.module == "SOURCE_INTAKE",
                KnowledgeDocument.doc_type == "SOURCE_BRIEF",
                KnowledgeDocument.title == title,
            )
        )
        existing = existing_result.scalar_one_or_none()
        payload = {
            "tenant_id": tenant_id,
            "summary": summary,
            "content": "\n".join(content).strip(),
            "knowledge_level": "BRIEF",
            "status": "PUBLISHED",
            "tags": ["source-brief", "source-intake", mode.lower()],
            "related_objects": [
                {
                    "source_type": "SOURCE_INSTANCE",
                    "source_id": str(instance.id),
                    "label": instance.instance_name,
                    "module": "SOURCE_INTAKE",
                    "module_route": "/source-onboarding",
                }
            ],
            "object_refs": [
                {"object_type": "SOURCE_INSTANCE", "object_id": instance.id, "label": instance.instance_name},
                *[
                    {
                        "object_type": "SOURCE_ASSET",
                        "object_id": asset.get("id") if isinstance(asset, dict) else asset.id,
                        "label": asset.get("qualified_name") if isinstance(asset, dict) else asset.qualified_name,
                    }
                    for asset in assets[:25]
                    if (asset.get("id") if isinstance(asset, dict) else asset.id) is not None
                ],
            ],
            "fact_refs": [
                {
                    "fact_type": "SOURCE_ASSET",
                    "fact_id": asset.get("id") if isinstance(asset, dict) else asset.id,
                }
                for asset in assets[:25]
                if (asset.get("id") if isinstance(asset, dict) else asset.id) is not None
            ],
            "meta_payload": {
                "instance_id": instance.id,
                "brief_mode": mode,
                "asset_ids": [
                    asset.get("id") if isinstance(asset, dict) else asset.id
                    for asset in assets
                    if (asset.get("id") if isinstance(asset, dict) else asset.id) is not None
                ],
                "brief_payload": brief_payload or {},
            },
            "last_editor_id": actor_id or f"project:{instance.project_id}",
            "last_editor_user_id": user_id,
            "published_at": _utcnow(),
        }
        if existing is None:
            await self.knowledge_repo.create(
                {
                    "project_id": instance.project_id,
                    "tenant_id": tenant_id,
                    "doc_type": "SOURCE_BRIEF",
                    "module": "SOURCE_INTAKE",
                    "title": title,
                    "format": "MARKDOWN",
                    "version_no": 1,
                    "comment_count": 0,
                    "author_id": actor_id or f"project:{instance.project_id}",
                    "author_user_id": user_id,
                    **payload,
                }
            )
        else:
            await self.knowledge_repo.update(
                existing,
                {
                    **payload,
                    "version_no": int(existing.version_no or 1) + 1,
                    "archived_at": None,
                },
            )

    async def _delete_related_documents(
        self,
        *,
        project_id: int,
        instance_id: int,
        legacy_source_id: int | None,
    ) -> None:
        asset_result = await self.db.execute(select(SourceAsset.id).where(SourceAsset.instance_id == instance_id))
        asset_ids = {str(item[0]) for item in asset_result.all()}
        field_result = await self.db.execute(select(SourceField.id).where(SourceField.instance_id == instance_id))
        field_ids = {str(item[0]) for item in field_result.all()}
        result = await self.db.execute(
            select(KnowledgeDocument).where(
                KnowledgeDocument.project_id == project_id,
            )
        )
        documents = list(result.scalars().all())
        for document in documents:
            meta_payload = document.meta_payload or {}
            related_objects = document.related_objects or []
            object_refs = document.object_refs or []
            fact_refs = document.fact_refs or []
            meta_instance_id = str(meta_payload.get("instance_id") or "")
            meta_legacy_id = str(meta_payload.get("legacy_source_id") or "")
            has_instance_ref = any(
                str(item.get("source_type") or "").upper() == "SOURCE_INSTANCE"
                and str(item.get("source_id") or "") == str(instance_id)
                for item in related_objects
            )
            has_legacy_ref = (
                legacy_source_id is not None
                and any(
                    str(item.get("source_type") or "").upper() == "DATA_SOURCE"
                    and str(item.get("source_id") or "") == str(legacy_source_id)
                    for item in related_objects
                )
            )
            has_object_instance_ref = any(
                str(item.get("object_type") or "").upper() == "SOURCE_INSTANCE"
                and str(item.get("object_id") or "") == str(instance_id)
                for item in object_refs
            )
            has_object_legacy_ref = (
                legacy_source_id is not None
                and any(
                    str(item.get("object_type") or "").upper() == "DATA_SOURCE"
                    and str(item.get("object_id") or "") == str(legacy_source_id)
                    for item in object_refs
                )
            )
            has_fact_instance_ref = any(
                str(item.get("fact_type") or "").upper() == "SOURCE_INSTANCE"
                and str(item.get("fact_id") or "") == str(instance_id)
                for item in fact_refs
            )
            has_asset_or_field_ref = any(
                (
                    str(item.get("object_type") or "").upper() == "SOURCE_ASSET"
                    and str(item.get("object_id") or "") in asset_ids
                )
                or (
                    str(item.get("object_type") or "").upper() == "SOURCE_FIELD"
                    and str(item.get("object_id") or "") in field_ids
                )
                for item in object_refs
            ) or any(
                (
                    str(item.get("fact_type") or "").upper() == "SOURCE_ASSET"
                    and str(item.get("fact_id") or "") in asset_ids
                )
                or (
                    str(item.get("fact_type") or "").upper() == "SOURCE_FIELD"
                    and str(item.get("fact_id") or "") in field_ids
                )
                for item in fact_refs
            )
            if (
                meta_instance_id == str(instance_id)
                or (legacy_source_id is not None and meta_legacy_id == str(legacy_source_id))
                or has_instance_ref
                or has_legacy_ref
                or has_object_instance_ref
                or has_object_legacy_ref
                or has_fact_instance_ref
                or has_asset_or_field_ref
            ):
                await self.db.delete(document)

    async def _upsert_legacy_source(self, instance: SourceInstance, assets: list[SourceAsset]) -> ExternalDataSource | None:
        connector = await self._get_connector_by_id(instance.connector_definition_id)
        source_type = CONNECTOR_SOURCE_TYPE_MAP.get(connector.connector_key)
        if source_type is None:
            return None
        legacy_source = await self.legacy_repo.get(instance.legacy_source_id) if instance.legacy_source_id else None
        config = decrypt_mapping(instance.encrypted_config)
        objects = []
        for asset in assets:
            if asset.asset_type != "TABLE":
                continue
            schema_payload = asset.schema_payload or {}
            metrics = asset.metrics_payload or {}
            objects.append(
                {
                    "source_type": source_type,
                    "schema": str(schema_payload.get("database") or schema_payload.get("schema") or "main"),
                    "table_name": asset.display_name,
                    "row_count_estimate": int(metrics.get("row_count_estimate") or 0),
                    "estimated_bytes": int(metrics.get("estimated_bytes") or 0),
                    "heat_level": asset.heat_level,
                    "column_count": int(metrics.get("column_count") or 0),
                    "columns": schema_payload.get("columns") or [],
                    "key_candidates": [],
                    "time_candidates": [column.get("name") for column in schema_payload.get("columns") or [] if any(token in str(column.get("name") or "").lower() for token in ("time", "date", "created", "updated"))],
                    "inference_candidates": [],
                }
            )
        payload = {
            "project_id": instance.project_id,
            "source_name": instance.instance_name,
            "source_type": source_type,
            "status": "OBSERVED",
            "encrypted_config": encrypt_mapping(config),
            "discovery_payload": {"source_type": source_type, "schema": config.get("database") or config.get("namespace") or "main", "objects": objects},
            "last_scan_status": "SUCCESS",
            "last_scan_message": f"Promoted {len(objects)} objects from source intake",
            "last_scanned_at": _utcnow(),
        }
        if legacy_source is None:
            legacy_source = await self.legacy_repo.create(payload)
            await self.instance_repo.update(instance, {"legacy_source_id": legacy_source.id})
        else:
            await self.legacy_repo.update(legacy_source, payload)
        return legacy_source
