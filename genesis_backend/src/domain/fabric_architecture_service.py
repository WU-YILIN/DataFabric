from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.contract_artifact import ContractArtifact
from src.infrastructure.database.models.external_data_source import ExternalDataSource
from src.infrastructure.database.models.knowledge_document import KnowledgeDocument
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.source_field import SourceField


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


def _hours_since(value: datetime | None) -> float | None:
    if value is None:
        return None
    baseline = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    delta = _utcnow() - baseline.astimezone(timezone.utc)
    return round(delta.total_seconds() / 3600, 2)


def _normalize_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _collect_object_columns(discovery: dict[str, Any]) -> list[dict[str, Any]]:
    columns: list[dict[str, Any]] = []
    for obj in discovery.get("objects", []) if isinstance(discovery, dict) else []:
        for column in obj.get("columns", []) or []:
            columns.append(column)
    return columns


def _collect_table_names(discovery: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for obj in discovery.get("objects", []) if isinstance(discovery, dict) else []:
        schema_name = str(obj.get("schema") or "").strip()
        table_name = str(obj.get("table_name") or "").strip()
        if not table_name:
            continue
        names.append(f"{schema_name}.{table_name}".strip("."))
    return names


def _estimate_bytes(row_count: int, column_count: int) -> int:
    return int(row_count * max(column_count, 1) * 48)


def _heat_level(total_rows: int) -> str:
    if total_rows >= 1_000_000:
        return "HOT"
    if total_rows >= 50_000:
        return "WARM"
    return "COLD"


DOMAIN_RULES: list[tuple[str, str, tuple[str, ...]]] = [
    ("orders", "订单与交易", ("order", "orders", "交易", "订单", "gmv", "cart", "sku")),
    ("customers", "用户与客户", ("user", "users", "member", "customer", "客户", "用户", "uid")),
    ("payments", "支付与结算", ("payment", "payments", "pay", "refund", "invoice", "结算", "支付")),
    ("products", "商品与库存", ("product", "inventory", "stock", "sku", "goods", "商品", "库存")),
    ("growth", "营销与增长", ("campaign", "traffic", "growth", "marketing", "ad", "营销", "增长")),
    ("ops", "平台与运维", ("alert", "audit", "infra", "monitor", "scheduler", "pipeline", "运维", "平台")),
]


@dataclass
class DomainAccumulator:
    key: str
    label: str
    score: int = 0
    source_ids: set[int] | None = None
    memory_ids: set[int] | None = None
    contract_ids: set[int] | None = None
    evidences: list[str] | None = None

    def __post_init__(self) -> None:
        self.source_ids = set()
        self.memory_ids = set()
        self.contract_ids = set()
        self.evidences = []


class FabricArchitectureService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_source_profiles(
        self,
        *,
        project_id: int,
        q: str | None = None,
        source_type: str | None = None,
        heat: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        sources = await self._load_sources(project_id)
        items = [self._build_source_profile(source) for source in sources]
        items = self._filter_source_profiles(items, q=q, source_type=source_type, heat=heat)
        return self._paginate(
            items,
            limit=limit,
            offset=offset,
            facets={
                "source_types": sorted({item["source_type"] for item in items}),
                "heat_levels": sorted({item["heat_level"] for item in items}),
                "update_modes": sorted({item["update_mode"] for item in items}),
            },
        )

    async def list_update_semantics(
        self,
        *,
        project_id: int,
        q: str | None = None,
        mode: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        sources = await self._load_sources(project_id)
        items = [self._build_update_semantics(source) for source in sources]
        keyword = _normalize_text(q)
        if keyword:
            items = [
                item
                for item in items
                if keyword in _normalize_text(item["source_name"])
                or keyword in _normalize_text(item["update_mode"])
                or any(keyword in _normalize_text(reason) for reason in item["reasoning"])
            ]
        if mode and mode.upper() != "ALL":
            items = [item for item in items if item["update_mode"] == mode.upper()]
        return self._paginate(
            items,
            limit=limit,
            offset=offset,
            facets={"modes": sorted({item["update_mode"] for item in items})},
        )

    async def get_semantic_domains(self, *, project_id: int, tenant_id: int | None) -> dict[str, Any]:
        sources = await self._load_sources(project_id)
        documents = await self._load_documents(project_id, tenant_id)
        contracts = await self._load_contracts(project_id)
        accumulators = self._build_domain_accumulators(sources, documents, contracts)
        items = [
            {
                "domain_key": item.key,
                "label": item.label,
                "score": item.score,
                "source_count": len(item.source_ids or set()),
                "memory_count": len(item.memory_ids or set()),
                "contract_count": len(item.contract_ids or set()),
                "evidences": (item.evidences or [])[:8],
            }
            for item in sorted(accumulators.values(), key=lambda row: (-row.score, row.label))
            if item.score > 0
        ]
        return {
            "items": items,
            "summary": {
                "domain_count": len(items),
                "top_domain": items[0]["label"] if items else "通用基础",
            },
        }

    async def plan_query(
        self,
        *,
        project_id: int,
        tenant_id: int | None,
        question: str,
        latency_target_ms: int = 800,
    ) -> dict[str, Any]:
        sources = await self._load_sources(project_id)
        documents = await self._load_documents(project_id, tenant_id)
        contracts = await self._load_contracts(project_id)
        domains = self._build_domain_accumulators(sources, documents, contracts)

        top_domain = self._resolve_domain(question, domains)
        matched_sources = self._match_sources(question, sources)
        matched_docs = self._match_docs(question, documents)
        matched_contracts = self._match_contracts(question, contracts)
        matched_fields = await self._match_fields(project_id, question)
        context_refs = await self._build_context_refs(
            project_id=project_id,
            matched_docs=matched_docs,
            matched_sources=matched_sources,
            matched_contracts=matched_contracts,
            matched_fields=matched_fields,
        )

        if matched_docs and latency_target_ms <= 250:
            strategy = "MEMORY_ONLY"
            rationale = "当前问题更像元数据与知识检索，优先直接命中项目记忆和共享记忆。"
        elif matched_contracts:
            strategy = "CONTRACT_FIRST"
            rationale = "已存在可复用的契约工件，优先返回稳定语义结果。"
        elif any(self._build_source_profile(source)["heat_level"] == "HOT" for source in matched_sources):
            strategy = "HOT_MATERIALIZATION"
            rationale = "命中高热度数据源，优先走热点物化工件或缓存路径。"
        else:
            strategy = "ON_DEMAND_COMPUTE"
            rationale = "没有现成热点结果，建议按需计算，并评估是否值得晋升为长期工件。"

        steps = [
            {
                "step": 1,
                "title": "识别业务主题域",
                "detail": f"当前问题优先归入“{top_domain['label']}”主题域。",
            },
            {
                "step": 2,
                "title": "解析可用上下文",
                "detail": f"命中 {len(matched_docs)} 份记忆、{len(matched_sources)} 个数据源、{len(matched_contracts)} 个契约工件。",
            },
            {
                "step": 3,
                "title": "选择执行策略",
                "detail": f"规划器策略：{strategy}。{rationale}",
            },
            {
                "step": 4,
                "title": "生成返回结果",
                "detail": "执行结果会回写到项目记忆，并参与后续热点工件与契约评估。",
            },
        ]

        return {
            "question": question,
            "latency_target_ms": latency_target_ms,
            "domain": top_domain,
            "strategy": strategy,
            "rationale": rationale,
            "matched_sources": [
                {
                    "id": item.id,
                    "source_name": item.source_name,
                    "source_type": item.source_type,
                    "status": item.status,
                    "heat_level": self._build_source_profile(item)["heat_level"],
                }
                for item in matched_sources[:5]
            ],
            "matched_memories": [
                {"id": item.id, "title": item.title, "module": item.module, "status": item.status}
                for item in matched_docs[:5]
            ],
            "matched_contracts": [
                {
                    "id": item.id,
                    "contract_name": item.contract_name,
                    "event_code": item.event_code,
                    "serving_status": item.serving_status,
                }
                for item in matched_contracts[:5]
            ],
            "context_refs": context_refs,
            "steps": steps,
        }

    async def list_materializations(
        self,
        *,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        contracts = await self._load_contracts(project_id)
        sources = await self._load_sources(project_id)
        items: list[dict[str, Any]] = []
        for artifact in contracts:
            items.append(
                {
                    "id": f"contract-{artifact.id}",
                    "artifact_type": "CONTRACT_ARTIFACT",
                    "artifact_name": artifact.contract_name,
                    "source_name": artifact.event_code,
                    "heat_level": "HOT",
                    "status": artifact.serving_status,
                    "acceleration_tier": "READY",
                    "latency_target_ms": 120,
                    "reason": "已发布的契约工件适合直接承接高频对话与报表查询。",
                    "updated_at": _to_iso(artifact.updated_at),
                }
            )
        for source in sources:
            profile = self._build_source_profile(source)
            tier = "RECOMMENDED" if profile["heat_level"] in {"HOT", "WARM"} else "COLD_PATH"
            items.append(
                {
                    "id": f"source-{source.id}",
                    "artifact_type": "SOURCE_ACCELERATION",
                    "artifact_name": f"{source.source_name}_semantic_cache",
                    "source_name": source.source_name,
                    "heat_level": profile["heat_level"],
                    "status": "PLANNED" if tier != "COLD_PATH" else "DEFERRED",
                    "acceleration_tier": tier,
                    "latency_target_ms": 300 if tier == "RECOMMENDED" else 1200,
                    "reason": profile["materialization_reason"],
                    "updated_at": profile["last_scanned_at"],
                }
            )
        keyword = _normalize_text(q)
        if keyword:
            items = [
                item
                for item in items
                if keyword in _normalize_text(item["artifact_name"])
                or keyword in _normalize_text(item["source_name"])
                or keyword in _normalize_text(item["reason"])
            ]
        if status and status.upper() != "ALL":
            items = [item for item in items if item["status"] == status.upper()]
        return self._paginate(
            items,
            limit=limit,
            offset=offset,
            facets={
                "statuses": sorted({item["status"] for item in items}),
                "tiers": sorted({item["acceleration_tier"] for item in items}),
            },
        )

    async def get_telemetry_overview(self, *, project_id: int) -> dict[str, Any]:
        sources = await self._load_sources(project_id)
        pipelines = await self._load_pipelines(project_id)
        alerts = await self._load_alerts(project_id)

        source_profiles = [self._build_source_profile(source) for source in sources]
        hot_sources = [item for item in source_profiles if item["heat_level"] == "HOT"]
        scan_failures = [item for item in source_profiles if item["last_scan_status"] == "FAILURE"]
        open_alerts = [item for item in alerts if item.status != "RESOLVED"]
        running_pipelines = [item for item in pipelines if str(item.status).upper() == "RUNNING"]

        source_rows = []
        for item in source_profiles[:12]:
            throughput = round((item["estimated_bytes"] / (1024 * 1024)) / max(item["freshness_hours"] or 24, 1), 2)
            load_score = min(
                100,
                (60 if item["heat_level"] == "HOT" else 35 if item["heat_level"] == "WARM" else 12)
                + (15 if item["status"] in {"OBSERVED", "CONNECTED"} else 0)
                + (10 if item["update_mode"] in {"UPSERT", "APPEND"} else 0),
            )
            source_rows.append(
                {
                    "source_id": item["id"],
                    "source_name": item["source_name"],
                    "heat_level": item["heat_level"],
                    "freshness_hours": item["freshness_hours"],
                    "throughput_mb_per_hour": throughput,
                    "load_score": load_score,
                    "status": item["status"],
                }
            )

        node_rows = [
            {
                "node_name": "fabric-planner",
                "role": "planner",
                "health": "HEALTHY" if len(open_alerts) < 4 else "WARN",
                "cpu_pct": min(78, 22 + len(hot_sources) * 8),
                "memory_pct": min(82, 28 + len(source_profiles) * 3),
                "disk_throughput_mb": round(sum(item["throughput_mb_per_hour"] for item in source_rows[:6]) / 6 if source_rows else 0, 2),
                "derived": True,
            },
            {
                "node_name": "fabric-materializer",
                "role": "materialization",
                "health": "HEALTHY" if len(running_pipelines) < 4 else "WARN",
                "cpu_pct": min(85, 30 + len(running_pipelines) * 12),
                "memory_pct": min(88, 34 + len(source_profiles) * 2),
                "disk_throughput_mb": round(sum(item["throughput_mb_per_hour"] for item in source_rows[:4]) / 4 if source_rows else 0, 2),
                "derived": True,
            },
            {
                "node_name": "fabric-serving",
                "role": "serving",
                "health": "HEALTHY" if len(open_alerts) <= 2 else "WARN",
                "cpu_pct": min(70, 18 + len(hot_sources) * 10),
                "memory_pct": min(80, 26 + len(open_alerts) * 6),
                "disk_throughput_mb": round(sum(item["throughput_mb_per_hour"] for item in source_rows[:3]) / 3 if source_rows else 0, 2),
                "derived": True,
            },
        ]

        return {
            "summary": {
                "source_count": len(source_profiles),
                "hot_sources": len(hot_sources),
                "scan_failures": len(scan_failures),
                "running_pipelines": len(running_pipelines),
                "open_alerts": len(open_alerts),
            },
            "source_load": source_rows,
            "cluster_nodes": node_rows,
            "alerts": [
                {
                    "id": item.id,
                    "severity": item.severity,
                    "status": item.status,
                    "title": item.title,
                    "source_type": item.source_type,
                    "source_id": item.source_id,
                }
                for item in open_alerts[:10]
            ],
        }

    async def _load_sources(self, project_id: int) -> list[ExternalDataSource]:
        result = await self.db.execute(
            select(ExternalDataSource)
            .where(ExternalDataSource.project_id == project_id)
            .order_by(ExternalDataSource.updated_at.desc(), ExternalDataSource.id.desc())
        )
        return list(result.scalars().all())

    async def _load_documents(self, project_id: int, tenant_id: int | None) -> list[KnowledgeDocument]:
        result = await self.db.execute(
            select(KnowledgeDocument)
            .where(KnowledgeDocument.status != "ARCHIVED")
            .order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id.desc())
        )
        rows = list(result.scalars().all())
        return [
            item
            for item in rows
            if item.project_id == project_id
            or (tenant_id is not None and item.tenant_id == tenant_id and "shared-memory" in (item.tags or []))
        ]

    async def _load_contracts(self, project_id: int) -> list[ContractArtifact]:
        result = await self.db.execute(
            select(ContractArtifact)
            .where(ContractArtifact.project_id == project_id)
            .order_by(ContractArtifact.updated_at.desc(), ContractArtifact.id.desc())
        )
        return list(result.scalars().all())

    async def _build_context_refs(
        self,
        *,
        project_id: int,
        matched_docs: list[KnowledgeDocument],
        matched_sources: list[ExternalDataSource],
        matched_contracts: list[ContractArtifact],
        matched_fields: list[SourceField],
    ) -> dict[str, list[dict[str, Any]]]:
        document_refs: dict[int, dict[str, Any]] = {}
        source_refs: dict[int, dict[str, Any]] = {}
        contract_refs: dict[int, dict[str, Any]] = {}
        asset_refs: dict[int, dict[str, Any]] = {}
        field_refs: dict[int, dict[str, Any]] = {}

        field_ids: set[int] = set()
        asset_ids: set[int] = set()

        for item in matched_docs[:5]:
            document_refs[int(item.id)] = {
                "id": int(item.id),
                "object_type": "DOCUMENT",
                "label": item.title,
                "reason": "matched_memory",
                "evidence_mode": "KNOWLEDGE",
                "priority": 100,
            }

        for item in matched_sources[:5]:
            source_refs[int(item.id)] = {
                "id": int(item.id),
                "object_type": "SOURCE",
                "label": item.source_name,
                "reason": "matched_source",
                "evidence_mode": "FACT",
                "priority": 90,
            }

        for item in matched_contracts[:5]:
            contract_refs[int(item.id)] = {
                "id": int(item.id),
                "object_type": "CONTRACT",
                "label": item.contract_name,
                "reason": "matched_contract",
                "evidence_mode": "CONTRACT",
                "priority": 95,
            }

        for item in matched_fields[:5]:
            field_ids.add(int(item.id))
            field_refs.setdefault(
                int(item.id),
                {
                    "id": int(item.id),
                    "object_type": "FIELD",
                    "label": item.field_key,
                    "reason": "matched_field",
                    "evidence_mode": "FACT",
                    "priority": 98,
                },
            )

        for item in matched_docs[:5]:
            for ref in item.object_refs or []:
                object_type = str(ref.get("object_type") or "").upper()
                object_id = ref.get("object_id")
                if object_id is None:
                    continue
                if object_type == "FIELD":
                    field_ids.add(int(object_id))
                    field_refs.setdefault(
                        int(object_id),
                        {
                            "id": int(object_id),
                            "object_type": "FIELD",
                            "label": str(ref.get("field_key") or ref.get("label") or object_id),
                            "reason": "knowledge_object_ref",
                            "evidence_mode": "FACT",
                            "priority": 100,
                        },
                    )
                elif object_type == "ASSET":
                    asset_ids.add(int(object_id))
                    asset_refs.setdefault(
                        int(object_id),
                        {
                            "id": int(object_id),
                            "object_type": "ASSET",
                            "label": str(ref.get("label") or object_id),
                            "reason": "knowledge_object_ref",
                            "evidence_mode": "FACT",
                            "priority": 85,
                        },
                    )
                elif object_type in {"INSTANCE", "SOURCE"}:
                    source_refs.setdefault(
                        int(object_id),
                        {
                            "id": int(object_id),
                            "object_type": "SOURCE",
                            "label": str(ref.get("label") or object_id),
                            "reason": "knowledge_object_ref",
                            "evidence_mode": "FACT",
                            "priority": 85,
                        },
                    )

            for ref in item.fact_refs or []:
                fact_type = str(ref.get("fact_type") or "").upper()
                fact_id = ref.get("fact_id")
                if fact_id is None:
                    continue
                if fact_type == "SOURCE_FIELD":
                    field_ids.add(int(fact_id))
                    field_refs.setdefault(
                        int(fact_id),
                        {
                            "id": int(fact_id),
                            "object_type": "FIELD",
                            "label": str(ref.get("label") or fact_id),
                            "reason": "knowledge_fact_ref",
                            "evidence_mode": "FACT",
                            "priority": 96,
                        },
                    )
                elif fact_type in {"SOURCE_ASSET", "ASSET"}:
                    asset_ids.add(int(fact_id))
                    asset_refs.setdefault(
                        int(fact_id),
                        {
                            "id": int(fact_id),
                            "object_type": "ASSET",
                            "label": str(ref.get("label") or fact_id),
                            "reason": "knowledge_fact_ref",
                            "evidence_mode": "FACT",
                            "priority": 82,
                        },
                    )

        if field_ids:
            result = await self.db.execute(
                select(SourceField).where(
                    SourceField.project_id == project_id,
                    SourceField.id.in_(sorted(field_ids)),
                )
            )
            for item in result.scalars().all():
                asset_ids.add(int(item.asset_id))
                field_refs.setdefault(
                    int(item.id),
                    {
                        "id": int(item.id),
                        "object_type": "FIELD",
                        "label": item.field_key,
                        "reason": "field_fact",
                        "evidence_mode": "FACT",
                        "priority": 88,
                    },
                )
                asset_refs.setdefault(
                    int(item.asset_id),
                    {
                        "id": int(item.asset_id),
                        "object_type": "ASSET",
                        "label": str(item.asset_id),
                        "reason": "field_parent_asset",
                        "evidence_mode": "FACT",
                        "priority": 70,
                    },
                )

        return {
            "documents": sorted(document_refs.values(), key=lambda item: (-int(item["priority"]), int(item["id"]))),
            "sources": sorted(source_refs.values(), key=lambda item: (-int(item["priority"]), int(item["id"]))),
            "assets": sorted(asset_refs.values(), key=lambda item: (-int(item["priority"]), int(item["id"]))),
            "fields": sorted(field_refs.values(), key=lambda item: (-int(item["priority"]), int(item["id"]))),
            "contracts": sorted(contract_refs.values(), key=lambda item: (-int(item["priority"]), int(item["id"]))),
        }

    async def _load_pipelines(self, project_id: int) -> list[Pipeline]:
        result = await self.db.execute(
            select(Pipeline)
            .where(Pipeline.project_id == project_id)
            .order_by(Pipeline.updated_at.desc(), Pipeline.id.desc())
        )
        return list(result.scalars().all())

    async def _load_alerts(self, project_id: int) -> list[Alert]:
        result = await self.db.execute(
            select(Alert)
            .where(Alert.project_id == project_id)
            .order_by(Alert.updated_at.desc(), Alert.id.desc())
        )
        return list(result.scalars().all())

    def _build_source_profile(self, source: ExternalDataSource) -> dict[str, Any]:
        discovery = source.discovery_payload or {}
        objects = discovery.get("objects", []) if isinstance(discovery, dict) else []
        total_rows = sum(int(item.get("row_count_estimate") or 0) for item in objects)
        total_columns = sum(int(item.get("column_count") or 0) for item in objects)
        estimated_bytes = _estimate_bytes(total_rows, total_columns)
        key_candidates = sorted({candidate for item in objects for candidate in item.get("key_candidates", []) or []})
        time_candidates = sorted({candidate for item in objects for candidate in item.get("time_candidates", []) or []})
        domain_candidates = self._suggest_domain_labels(source.source_name, _collect_table_names(discovery))
        update_semantics = self._build_update_semantics(source)
        freshness_hours = _hours_since(source.last_scanned_at)
        heat_level = source.discovery_payload.get("heat_level") if isinstance(source.discovery_payload, dict) else None
        heat_level = heat_level or _heat_level(total_rows)
        return {
            "id": source.id,
            "source_name": source.source_name,
            "source_type": source.source_type,
            "status": source.status,
            "heat_level": heat_level,
            "total_objects": len(objects),
            "total_rows": total_rows,
            "total_columns": total_columns,
            "estimated_bytes": estimated_bytes,
            "key_candidates": key_candidates,
            "time_candidates": time_candidates,
            "domain_candidates": domain_candidates,
            "update_mode": update_semantics["update_mode"],
            "refresh_cadence": update_semantics["refresh_cadence"],
            "freshness_hours": freshness_hours,
            "last_scan_status": source.last_scan_status,
            "last_scanned_at": _to_iso(source.last_scanned_at),
            "materialization_reason": self._materialization_reason(heat_level, freshness_hours, len(objects)),
            "top_objects": [
                {
                    "name": f"{item.get('schema')}.{item.get('table_name')}".strip("."),
                    "rows": int(item.get("row_count_estimate") or 0),
                    "heat_level": item.get("heat_level") or _heat_level(int(item.get("row_count_estimate") or 0)),
                }
                for item in objects[:6]
            ],
        }

    def _build_update_semantics(self, source: ExternalDataSource) -> dict[str, Any]:
        discovery = source.discovery_payload or {}
        objects = discovery.get("objects", []) if isinstance(discovery, dict) else []
        key_candidates = sorted({candidate for item in objects for candidate in item.get("key_candidates", []) or []})
        time_candidates = sorted({candidate for item in objects for candidate in item.get("time_candidates", []) or []})
        lower_columns = [_normalize_text(column.get("name")) for column in _collect_object_columns(discovery)]

        if any(name in {"updated_at", "modified_at", "last_updated"} for name in lower_columns) and key_candidates:
            update_mode = "UPSERT"
            confidence = 0.88
            reasoning = ["发现了主键候选和更新时间字段，适合按主键合并更新。"]
        elif any(name in {"created_at", "event_time", "event_date"} for name in lower_columns) and not any(
            name in {"updated_at", "modified_at", "last_updated"} for name in lower_columns
        ):
            update_mode = "APPEND"
            confidence = 0.81
            reasoning = ["存在创建时间或事件时间字段，更像追加式离线明细。"]
        elif source.source_type == "SQLITE" or len(objects) <= 2:
            update_mode = "FULL_SNAPSHOT"
            confidence = 0.76
            reasoning = ["对象数量较少或来源较轻量，适合全量快照更新。"]
        elif any("partition" in name for name in lower_columns):
            update_mode = "PERIODIC_FULL"
            confidence = 0.72
            reasoning = ["检测到分区或批次痕迹，适合周期全量刷新。"]
        else:
            update_mode = "CDC_LIKE"
            confidence = 0.58
            reasoning = ["存在多类时间字段但缺少明确更新规则，建议按近 CDC 模式持续观察。"]

        freshness_hours = _hours_since(source.last_scanned_at)
        if freshness_hours is None:
            refresh_cadence = "UNKNOWN"
        elif freshness_hours <= 30:
            refresh_cadence = "DAILY"
        elif freshness_hours <= 24 * 8:
            refresh_cadence = "WEEKLY"
        elif freshness_hours <= 24 * 40:
            refresh_cadence = "MONTHLY"
        else:
            refresh_cadence = "IRREGULAR"

        planner_strategy = (
            "HOT_MATERIALIZATION"
            if update_mode in {"UPSERT", "APPEND"} and refresh_cadence in {"DAILY", "WEEKLY"}
            else "ON_DEMAND_COMPUTE"
        )
        return {
            "source_id": source.id,
            "source_name": source.source_name,
            "source_type": source.source_type,
            "update_mode": update_mode,
            "refresh_cadence": refresh_cadence,
            "confidence": confidence,
            "planner_strategy": planner_strategy,
            "key_candidates": key_candidates,
            "time_candidates": time_candidates,
            "freshness_hours": freshness_hours,
            "reasoning": reasoning,
            "recommended_actions": self._recommended_actions(update_mode, refresh_cadence),
            "last_scanned_at": _to_iso(source.last_scanned_at),
        }

    def _filter_source_profiles(
        self,
        items: list[dict[str, Any]],
        *,
        q: str | None,
        source_type: str | None,
        heat: str | None,
    ) -> list[dict[str, Any]]:
        keyword = _normalize_text(q)
        if keyword:
            items = [
                item
                for item in items
                if keyword in _normalize_text(item["source_name"])
                or keyword in _normalize_text(item["source_type"])
                or any(keyword in _normalize_text(domain) for domain in item["domain_candidates"])
            ]
        if source_type and source_type.upper() != "ALL":
            items = [item for item in items if item["source_type"] == source_type.upper()]
        if heat and heat.upper() != "ALL":
            items = [item for item in items if item["heat_level"] == heat.upper()]
        return items

    def _build_domain_accumulators(
        self,
        sources: list[ExternalDataSource],
        documents: list[KnowledgeDocument],
        contracts: list[ContractArtifact],
    ) -> dict[str, DomainAccumulator]:
        accumulators = {key: DomainAccumulator(key=key, label=label) for key, label, _ in DOMAIN_RULES}
        accumulators["general"] = DomainAccumulator(key="general", label="通用基础")

        for source in sources:
            text = " ".join([source.source_name, *_collect_table_names(source.discovery_payload or {})])
            matched = self._match_domain_rules(text) or ["general"]
            for key in matched:
                accumulators[key].score += 3
                accumulators[key].source_ids.add(source.id)
                accumulators[key].evidences.append(f"数据源：{source.source_name}")

        for doc in documents:
            text = " ".join([doc.title, doc.summary or "", " ".join(doc.tags or [])])
            matched = self._match_domain_rules(text) or ["general"]
            for key in matched:
                accumulators[key].score += 2
                accumulators[key].memory_ids.add(doc.id)
                accumulators[key].evidences.append(f"记忆：{doc.title}")

        for contract in contracts:
            text = " ".join([contract.contract_name, contract.event_code])
            matched = self._match_domain_rules(text) or ["general"]
            for key in matched:
                accumulators[key].score += 4
                accumulators[key].contract_ids.add(contract.id)
                accumulators[key].evidences.append(f"契约：{contract.contract_name}")
        return accumulators

    def _resolve_domain(self, question: str, domains: dict[str, DomainAccumulator]) -> dict[str, Any]:
        matched = self._match_domain_rules(question)
        item = (domains.get(matched[0]) if matched else None) or max(domains.values(), key=lambda row: row.score)
        return {"domain_key": item.key, "label": item.label, "evidences": (item.evidences or [])[:5]}

    def _match_domain_rules(self, text: str) -> list[str]:
        normalized = _normalize_text(text)
        matches: list[str] = []
        for key, _label, keywords in DOMAIN_RULES:
            if any(keyword in normalized for keyword in keywords):
                matches.append(key)
        return matches

    def _suggest_domain_labels(self, source_name: str, object_names: list[str]) -> list[str]:
        matches = self._match_domain_rules(" ".join([source_name, *object_names]))
        if not matches:
            return ["通用基础"]
        labels = []
        for key, label, _ in DOMAIN_RULES:
            if key in matches:
                labels.append(label)
        return labels[:3]

    def _match_sources(self, question: str, sources: list[ExternalDataSource]) -> list[ExternalDataSource]:
        normalized = _normalize_text(question)
        scored: list[tuple[int, ExternalDataSource]] = []
        for source in sources:
            haystack = " ".join([source.source_name, *_collect_table_names(source.discovery_payload or {})]).lower()
            score = sum(2 for token in normalized.split() if token and token in haystack)
            if score > 0:
                scored.append((score, source))
        scored.sort(key=lambda item: (-item[0], item[1].source_name.lower()))
        return [item[1] for item in scored] or sources[:3]

    def _match_docs(self, question: str, docs: list[KnowledgeDocument]) -> list[KnowledgeDocument]:
        normalized = _normalize_text(question)
        scored: list[tuple[int, KnowledgeDocument]] = []
        for doc in docs:
            haystack = " ".join([doc.title, doc.summary or "", " ".join(doc.tags or [])]).lower()
            score = sum(2 for token in normalized.split() if token and token in haystack)
            if score > 0:
                scored.append((score, doc))
        scored.sort(key=lambda item: (-item[0], item[1].title.lower()))
        return [item[1] for item in scored] or docs[:3]

    def _match_contracts(self, question: str, contracts: list[ContractArtifact]) -> list[ContractArtifact]:
        normalized = _normalize_text(question)
        scored: list[tuple[int, ContractArtifact]] = []
        for artifact in contracts:
            haystack = " ".join([artifact.contract_name, artifact.event_code]).lower()
            score = sum(3 for token in normalized.split() if token and token in haystack)
            if score > 0:
                scored.append((score, artifact))
        scored.sort(key=lambda item: (-item[0], item[1].contract_name.lower()))
        return [item[1] for item in scored]

    async def _match_fields(self, project_id: int, question: str) -> list[SourceField]:
        tokens = [token for token in _normalize_text(question).split() if token]
        if not tokens:
            return []

        result = await self.db.execute(select(SourceField).where(SourceField.project_id == project_id))
        fields = list(result.scalars().all())
        scored: list[tuple[int, SourceField]] = []
        for field in fields:
            haystack = " ".join(
                [
                    str(field.field_name or ""),
                    str(field.field_key or ""),
                    str(field.display_name or ""),
                    str(field.physical_type or ""),
                ]
            ).lower()
            score = sum(3 for token in tokens if token and token in haystack)
            if score > 0:
                scored.append((score, field))
        scored.sort(key=lambda item: (-item[0], -int(item[1].id)))
        return [item[1] for item in scored[:5]]

    def _recommended_actions(self, update_mode: str, refresh_cadence: str) -> list[str]:
        if update_mode == "UPSERT":
            return ["建议建立按主键合并的热点语义视图", "为更新时间字段建立 freshness 监控"]
        if update_mode == "APPEND":
            return ["优先生成按时间分区的查询契约", "对高频分析问题启用热点聚合工件"]
        if refresh_cadence == "MONTHLY":
            return ["默认按冷数据处理，仅保留摘要与按需计算能力", "避免长期全量物化，优先按会话即时分析"]
        return ["先补齐更新语义确认", "再观察一次完整刷新后决定是否晋升为热点工件"]

    def _materialization_reason(self, heat_level: str, freshness_hours: float | None, object_count: int) -> str:
        if heat_level == "HOT":
            return "当前数据热度高，建议生成热点契约或缓存工件，优先服务高频分析。"
        if heat_level == "WARM":
            return "数据热度中等，可按问题命中率决定是否晋升为热点工件。"
        if freshness_hours is not None and freshness_hours > 24 * 30:
            return "数据刷新较慢，保留记忆与按需计算即可，无需长期物化。"
        if object_count <= 1:
            return "对象数量较少，先走按需计算与轻量缓存。"
        return "默认保留为冷路径，仅在高频复用后再自动晋升。"

    def _paginate(
        self,
        items: list[dict[str, Any]],
        *,
        limit: int,
        offset: int,
        facets: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        total = len(items)
        return {
            "items": items[offset : offset + limit],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": facets or {},
        }
