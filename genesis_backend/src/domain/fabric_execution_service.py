from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.fabric_architecture_service import FabricArchitectureService
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.executed_sql import ExecutedSQL
from src.infrastructure.database.models.execution_stage import ExecutionStage
from src.infrastructure.database.models.materialization_artifact import MaterializationArtifact
from src.infrastructure.database.models.query_intent import QueryIntent
from src.infrastructure.database.models.query_plan import QueryPlan
from src.infrastructure.database.models.query_run import QueryRun


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc).isoformat()
    return value.astimezone(timezone.utc).isoformat()


class FabricExecutionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.architecture = FabricArchitectureService(db)

    async def submit_query(
        self,
        *,
        project_id: int,
        tenant_id: int | None,
        actor_id: str,
        actor_user_id: int | None,
        question: str,
        latency_target_ms: int = 800,
    ) -> dict[str, Any]:
        preview = await self.architecture.plan_query(
            project_id=project_id,
            tenant_id=tenant_id,
            question=question,
            latency_target_ms=latency_target_ms,
        )
        profile = self._build_intent_profile(question=question, latency_target_ms=latency_target_ms, preview=preview)
        trace_id = f"trace_{uuid4().hex[:24]}"
        context_refs = preview.get("context_refs") or {
            "documents": [],
            "sources": [],
            "assets": [],
            "fields": [],
            "contracts": [],
        }

        intent = QueryIntent(
            project_id=project_id,
            actor_user_id=actor_user_id,
            actor_id=actor_id,
            trace_id=trace_id,
            question=question,
            intent_type=profile["intent_type"],
            domain=profile["domain"],
            time_scope=profile["time_scope"],
            dimensions=profile["dimensions"],
            metrics=profile["metrics"],
            operation_mode=profile["operation_mode"],
            latency_expectation=profile["latency_expectation"],
            candidate_paths=profile["candidate_paths"],
            payload=profile,
        )
        self.db.add(intent)
        await self.db.flush()

        plan = QueryPlan(
            project_id=project_id,
            intent_id=intent.id,
            trace_id=trace_id,
            selected_path=preview["strategy"],
            plan_status="READY",
            engine_strategy=self._engine_strategy(preview["strategy"]),
            rationale=self._planner_rationale(selected_path=preview["strategy"], profile=profile),
            plan_payload={
                "steps": preview["steps"],
                "domain": preview["domain"],
                "latency_target_ms": latency_target_ms,
                "execution_mode": "ASYNC" if self._requires_async(profile["intent_type"], preview["strategy"]) else "DIRECT",
                "default_manual_boundary": True,
                "context_refs": context_refs,
            },
            matched_payload={
                "sources": preview["matched_sources"],
                "memories": preview["matched_memories"],
                "contracts": preview["matched_contracts"],
            },
        )
        self.db.add(plan)
        await self.db.flush()

        if self._requires_async(profile["intent_type"], preview["strategy"]):
            run, artifacts = await self._create_async_run(
                project_id=project_id,
                trace_id=trace_id,
                intent=intent,
                plan=plan,
                preview=preview,
                profile=profile,
            )
        else:
            run, artifacts = await self._create_direct_run(
                project_id=project_id,
                trace_id=trace_id,
                intent=intent,
                plan=plan,
                preview=preview,
            )

        await self._write_audit_logs(actor_id=actor_id, intent=intent, plan=plan, run=run)
        await self.db.commit()

        return {
            "trace_id": trace_id,
            "intent": self._serialize_intent(intent),
            "plan": self._serialize_plan(plan),
            "run": self._serialize_run(run),
            "artifacts": [self._serialize_artifact(item) for item in artifacts],
        }

    async def list_query_runs(
        self,
        *,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        intent_type: str | None = None,
        selected_path: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(QueryRun).where(QueryRun.project_id == project_id).order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
        )
        runs = list(result.scalars().all())
        intent_rows = await self.db.execute(
            select(QueryIntent).where(QueryIntent.project_id == project_id)
        )
        intents = {item.id: item for item in intent_rows.scalars().all()}
        plan_rows = await self.db.execute(select(QueryPlan).where(QueryPlan.project_id == project_id))
        plans = {item.id: item for item in plan_rows.scalars().all()}

        keyword = (q or "").strip().lower()
        items: list[dict[str, Any]] = []
        for run in runs:
            intent = intents.get(run.intent_id)
            plan = plans.get(run.plan_id)
            if not intent or not plan:
                continue
            if keyword and keyword not in intent.question.lower() and keyword not in (intent.domain or "").lower():
                continue
            if status and status.upper() != "ALL" and run.status != status.upper():
                continue
            if intent_type and intent_type.upper() != "ALL" and intent.intent_type != intent_type.upper():
                continue
            if selected_path and selected_path.upper() != "ALL" and plan.selected_path != selected_path.upper():
                continue
            items.append(
                {
                    **self._serialize_run(run),
                    "intent_type": intent.intent_type,
                    "question": intent.question,
                    "domain": intent.domain,
                    "selected_path": plan.selected_path,
                }
            )

        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": sorted({item["status"] for item in items}),
                "intent_types": sorted({item["intent_type"] for item in items}),
                "selected_paths": sorted({item["selected_path"] for item in items}),
            },
        }

    async def get_query_run_detail(self, *, project_id: int, run_id: int) -> dict[str, Any] | None:
        run_result = await self.db.execute(
            select(QueryRun).where(QueryRun.project_id == project_id, QueryRun.id == run_id)
        )
        run = run_result.scalar_one_or_none()
        if run is None:
            return None

        intent_result = await self.db.execute(select(QueryIntent).where(QueryIntent.id == run.intent_id))
        intent = intent_result.scalar_one_or_none()
        plan_result = await self.db.execute(select(QueryPlan).where(QueryPlan.id == run.plan_id))
        plan = plan_result.scalar_one_or_none()
        stage_result = await self.db.execute(
            select(ExecutionStage).where(ExecutionStage.run_id == run.id).order_by(ExecutionStage.stage_no.asc())
        )
        sql_result = await self.db.execute(
            select(ExecutedSQL).where(ExecutedSQL.run_id == run.id).order_by(ExecutedSQL.id.asc())
        )
        artifact_result = await self.db.execute(
            select(MaterializationArtifact)
            .where(MaterializationArtifact.project_id == project_id, MaterializationArtifact.run_id == run.id)
            .order_by(MaterializationArtifact.updated_at.desc(), MaterializationArtifact.id.desc())
        )

        return {
            "trace_id": run.trace_id,
            "intent": self._serialize_intent(intent) if intent else None,
            "plan": self._serialize_plan(plan) if plan else None,
            "run": self._serialize_run(run),
            "stages": [self._serialize_stage(item) for item in stage_result.scalars().all()],
            "prepared_sql": [self._serialize_sql(item) for item in sql_result.scalars().all()],
            "artifacts": [self._serialize_artifact(item) for item in artifact_result.scalars().all()],
        }

    async def list_materialization_artifacts(
        self,
        *,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        heat: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(MaterializationArtifact)
            .where(MaterializationArtifact.project_id == project_id)
            .order_by(MaterializationArtifact.updated_at.desc(), MaterializationArtifact.id.desc())
        )
        keyword = (q or "").strip().lower()
        items = []
        for artifact in result.scalars().all():
            serialized = self._serialize_artifact(artifact)
            if keyword and keyword not in serialized["artifact_name"].lower() and keyword not in serialized["reason"].lower():
                continue
            if status and status.upper() != "ALL" and serialized["status"] != status.upper():
                continue
            if heat and heat.upper() != "ALL" and serialized["heat_level"] != heat.upper():
                continue
            items.append(serialized)
        return {
            "items": items[offset : offset + limit],
            "total": len(items),
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": sorted({item["status"] for item in items}),
                "heat_levels": sorted({item["heat_level"] for item in items}),
            },
        }

    async def get_trace(self, *, project_id: int, trace_id: str) -> dict[str, Any] | None:
        trace = (trace_id or "").strip()
        if not trace:
            return None

        intent_result = await self.db.execute(
            select(QueryIntent).where(QueryIntent.project_id == project_id, QueryIntent.trace_id == trace)
        )
        intent = intent_result.scalar_one_or_none()
        if intent is None:
            return None

        plan_result = await self.db.execute(
            select(QueryPlan).where(QueryPlan.project_id == project_id, QueryPlan.trace_id == trace)
        )
        plan = plan_result.scalar_one_or_none()

        run_result = await self.db.execute(
            select(QueryRun)
            .where(QueryRun.project_id == project_id, QueryRun.trace_id == trace)
            .order_by(QueryRun.created_at.desc(), QueryRun.id.desc())
        )
        runs = list(run_result.scalars().all())
        run_ids = [item.id for item in runs]

        stages_by_run: dict[int, list[dict[str, Any]]] = {}
        prepared_sql_by_run: dict[int, list[dict[str, Any]]] = {}

        if run_ids:
            stage_result = await self.db.execute(
                select(ExecutionStage)
                .where(ExecutionStage.run_id.in_(run_ids))
                .order_by(ExecutionStage.run_id.asc(), ExecutionStage.stage_no.asc())
            )
            for item in stage_result.scalars().all():
                stages_by_run.setdefault(item.run_id, []).append(self._serialize_stage(item))

            sql_result = await self.db.execute(
                select(ExecutedSQL)
                .where(ExecutedSQL.run_id.in_(run_ids))
                .order_by(ExecutedSQL.run_id.asc(), ExecutedSQL.id.asc())
            )
            for item in sql_result.scalars().all():
                prepared_sql_by_run.setdefault(item.run_id, []).append(self._serialize_sql(item))

        artifact_result = await self.db.execute(
            select(MaterializationArtifact)
            .where(MaterializationArtifact.project_id == project_id, MaterializationArtifact.trace_id == trace)
            .order_by(MaterializationArtifact.updated_at.desc(), MaterializationArtifact.id.desc())
        )

        return {
            "trace_id": trace,
            "intent": self._serialize_intent(intent),
            "plan": self._serialize_plan(plan) if plan else None,
            "runs": [self._serialize_run(item) for item in runs],
            "stages": stages_by_run,
            "prepared_sql": prepared_sql_by_run,
            "artifacts": [self._serialize_artifact(item) for item in artifact_result.scalars().all()],
        }

    def build_chat_trace_preview(
        self,
        *,
        question: str,
        latency_target_ms: int,
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        profile = self._build_intent_profile(question=question, latency_target_ms=latency_target_ms, preview=preview)
        return {
            "intent_type": profile["intent_type"],
            "domain": profile["domain"],
            "candidate_paths": profile["candidate_paths"],
            "selected_path": preview["strategy"],
            "latency_expectation": profile["latency_expectation"],
            "requires_async": self._requires_async(profile["intent_type"], preview["strategy"]),
        }

    async def _create_direct_run(
        self,
        *,
        project_id: int,
        trace_id: str,
        intent: QueryIntent,
        plan: QueryPlan,
        preview: dict[str, Any],
    ) -> tuple[QueryRun, list[MaterializationArtifact]]:
        run = QueryRun(
            project_id=project_id,
            intent_id=intent.id,
            plan_id=plan.id,
            trace_id=trace_id,
            run_key=f"run_{uuid4().hex[:16]}",
            execution_mode="DIRECT",
            status="COMPLETED",
            current_stage="RESULT_READY",
            engine_family=plan.engine_strategy,
            result_summary=self._direct_result_summary(preview["strategy"]),
            metrics_payload={"latency_target_ms": plan.plan_payload.get("latency_target_ms", 800)},
            submitted_at=_utcnow(),
            started_at=_utcnow(),
            finished_at=_utcnow(),
        )
        self.db.add(run)
        await self.db.flush()
        return run, []

    async def _create_async_run(
        self,
        *,
        project_id: int,
        trace_id: str,
        intent: QueryIntent,
        plan: QueryPlan,
        preview: dict[str, Any],
        profile: dict[str, Any],
    ) -> tuple[QueryRun, list[MaterializationArtifact]]:
        run = QueryRun(
            project_id=project_id,
            intent_id=intent.id,
            plan_id=plan.id,
            trace_id=trace_id,
            run_key=f"run_{uuid4().hex[:16]}",
            execution_mode="ASYNC",
            status="WAITING_CONFIRMATION",
            current_stage="PLAN_READY",
            engine_family=plan.engine_strategy,
            result_summary="已生成重型分析执行计划，等待人工确认后执行。",
            metrics_payload={
                "latency_target_ms": plan.plan_payload.get("latency_target_ms", 800),
                "manual_boundary": True,
            },
            submitted_at=_utcnow(),
        )
        self.db.add(run)
        await self.db.flush()

        stages = self._build_stage_blueprint(profile=profile, preview=preview)
        for stage in stages:
            stage_row = ExecutionStage(
                project_id=project_id,
                run_id=run.id,
                stage_no=stage["stage_no"],
                stage_key=stage["stage_key"],
                title=stage["title"],
                goal=stage["goal"],
                engine_key=stage["engine_key"],
                status="PENDING",
                planning_payload=stage["planning_payload"],
                metrics_payload={},
            )
            self.db.add(stage_row)
            await self.db.flush()

            sql_text = stage.get("prepared_sql")
            if sql_text:
                sql_hash = hashlib.sha1(sql_text.encode("utf-8")).hexdigest()
                self.db.add(
                    ExecutedSQL(
                        project_id=project_id,
                        run_id=run.id,
                        stage_id=stage_row.id,
                        engine_key=stage["engine_key"],
                        execution_role="PREPARED",
                        status="DRAFT",
                        sql_hash=sql_hash,
                        sql_text=sql_text,
                        metrics_payload={"origin": "planner"},
                    )
                )

        artifact = MaterializationArtifact(
            project_id=project_id,
            plan_id=plan.id,
            run_id=run.id,
            trace_id=trace_id,
            artifact_name=self._artifact_name(profile=profile),
            artifact_type="HOT_QUERY_RESULT" if preview["strategy"] == "HOT_MATERIALIZATION" else "TEMP_RESULT",
            status="RECOMMENDED",
            heat_level="HOT" if preview["strategy"] == "HOT_MATERIALIZATION" else "WARM",
            engine_key=self._artifact_engine(preview["strategy"]),
            storage_strategy="ANALYTICAL_WAREHOUSE_FIRST",
            retention_policy="未确认前仅保留为候选工件",
            reason=self._materialization_reason(selected_path=preview["strategy"], profile=profile),
            artifact_payload={
                "question": intent.question,
                "selected_path": preview["strategy"],
                "domain": profile["domain"],
                "candidate_paths": profile["candidate_paths"],
            },
        )
        self.db.add(artifact)
        await self.db.flush()
        return run, [artifact]

    async def _write_audit_logs(
        self,
        *,
        actor_id: str,
        intent: QueryIntent,
        plan: QueryPlan,
        run: QueryRun,
    ) -> None:
        logs = [
            AuditLog(
                user_id=actor_id,
                action="QUERY_INTENT_CREATED",
                entity_type="QUERY_INTENT",
                entity_id=str(intent.id),
                details=json.dumps(
                    {
                        "trace_id": intent.trace_id,
                        "intent_type": intent.intent_type,
                        "domain": intent.domain,
                    },
                    ensure_ascii=False,
                ),
            ),
            AuditLog(
                user_id=actor_id,
                action="QUERY_PLAN_CREATED",
                entity_type="QUERY_PLAN",
                entity_id=str(plan.id),
                details=json.dumps(
                    {
                        "trace_id": plan.trace_id,
                        "selected_path": plan.selected_path,
                        "engine_strategy": plan.engine_strategy,
                    },
                    ensure_ascii=False,
                ),
            ),
            AuditLog(
                user_id=actor_id,
                action="QUERY_RUN_CREATED",
                entity_type="QUERY_RUN",
                entity_id=str(run.id),
                details=json.dumps(
                    {
                        "trace_id": run.trace_id,
                        "status": run.status,
                        "execution_mode": run.execution_mode,
                    },
                    ensure_ascii=False,
                ),
            ),
        ]
        self.db.add_all(logs)

    def _build_intent_profile(
        self,
        *,
        question: str,
        latency_target_ms: int,
        preview: dict[str, Any],
    ) -> dict[str, Any]:
        normalized = question.lower()
        time_scope = self._extract_time_scope(question)
        metrics = self._extract_metrics(normalized)
        dimensions = self._extract_dimensions(normalized)
        intent_type = self._classify_intent(normalized)

        if intent_type == "MEMORY":
            candidate_paths = ["MEMORY_PATH"]
            operation_mode = "READ"
            latency_expectation = "INTERACTIVE"
        elif intent_type == "STATUS":
            candidate_paths = ["MEMORY_PATH", "CONTRACT_PATH"]
            operation_mode = "READ"
            latency_expectation = "INTERACTIVE"
        elif intent_type == "CONTRACT":
            candidate_paths = ["CONTRACT_PATH", "HOT_ARTIFACT_PATH"]
            operation_mode = "READ"
            latency_expectation = "INTERACTIVE"
        elif intent_type == "HOT_ANALYTICS":
            candidate_paths = ["HOT_ARTIFACT_PATH", "CONTRACT_PATH", "ON_DEMAND_COMPUTE_PATH"]
            operation_mode = "READ"
            latency_expectation = "INTERACTIVE" if latency_target_ms <= 1500 else "NEARLINE"
        elif intent_type == "GOVERNANCE_ACTION":
            candidate_paths = ["MEMORY_PATH", "CONTRACT_PATH"]
            operation_mode = "GOVERN"
            latency_expectation = "INTERACTIVE"
        else:
            candidate_paths = ["ON_DEMAND_COMPUTE_PATH", "HOT_ARTIFACT_PATH"]
            operation_mode = "READ"
            latency_expectation = "BACKGROUND" if self._looks_heavy(normalized) else "NEARLINE"

        return {
            "intent_type": intent_type,
            "domain": preview["domain"]["label"],
            "domain_key": preview["domain"]["domain_key"],
            "time_scope": time_scope,
            "dimensions": dimensions,
            "metrics": metrics,
            "operation_mode": operation_mode,
            "candidate_paths": candidate_paths,
            "latency_expectation": latency_expectation,
            "matched_sources": preview["matched_sources"],
            "matched_contracts": preview["matched_contracts"],
            "matched_memories": preview["matched_memories"],
        }

    def _classify_intent(self, normalized_question: str) -> str:
        if any(token in normalized_question for token in ["确认", "发布", "共享", "忽略", "纳入", "回滚", "confirm", "publish", "share", "ignore", "promote", "rollback", "approve"]):
            return "GOVERNANCE_ACTION"
        if any(token in normalized_question for token in ["状态", "失败", "运行", "监听", "告警", "延迟", "负载", "status", "failed", "running", "watch", "alert", "latency", "load"]):
            return "STATUS"
        if any(token in normalized_question for token in ["口径", "契约", "定义", "发布对象", "contract", "definition", "published object", "metric definition"]):
            return "CONTRACT"
        if any(
            token in normalized_question
            for token in [
                "趋势",
                "汇总",
                "排名",
                "分布",
                "同比",
                "环比",
                "最近7",
                "最近30",
                "最近",
                "占比",
                "比例",
                "比率",
                "人数",
                "人群",
                "统计",
                "分析",
                "top",
                "trend",
                "summary",
                "rank",
                "distribution",
                "ratio",
                "percentage",
                "month over month",
                "week over week",
            ]
        ):
            return "HOT_ANALYTICS"
        demographic_signals = [
            "地区",
            "地域",
            "省",
            "城市",
            "市",
            "年龄",
            "岁",
            "性别",
            "gender",
            "age",
            "region",
            "province",
            "city",
        ]
        if sum(1 for token in demographic_signals if token in normalized_question) >= 2:
            return "HOT_ANALYTICS"
        if any(token in normalized_question for token in ["复杂", "关联", "全量", "宽表", "重算", "多表", "异步", "join", "full load", "pb", "tb", "wide table", "recompute", "multi-table", "async"]):
            return "AD_HOC_ANALYTICS"
        return "MEMORY"

    def _extract_time_scope(self, question: str) -> str | None:
        patterns = [
            r"(最近\d+天)",
            r"(最近\d+周)",
            r"(最近\d+个月)",
            r"(近\d+天)",
            r"(近\d+周)",
            r"(近\d+个月)",
            r"(本月|本周|今年|去年|上月|上周)",
            r"(last\s+\d+\s+days?)",
            r"(last\s+\d+\s+weeks?)",
            r"(last\s+\d+\s+months?)",
            r"(recent\s+\d+\s+days?)",
            r"(recent\s+\d+\s+weeks?)",
            r"(recent\s+\d+\s+months?)",
            r"(this\s+month|this\s+week|this\s+year|last\s+month|last\s+week|last\s+year)",
        ]
        lowered = question.lower()
        for pattern in patterns:
            match = re.search(pattern, question)
            if match:
                return match.group(1)
            match = re.search(pattern, lowered)
            if match:
                return match.group(1)
        return None

    def _extract_metrics(self, normalized_question: str) -> list[str]:
        mapping = {
            "金额": "amount",
            "gmv": "gmv",
            "收入": "revenue",
            "订单": "orders",
            "支付": "payments",
            "用户": "users",
            "数量": "count",
            "人数": "count",
            "占比": "ratio",
            "比例": "ratio",
            "比率": "ratio",
            "amount": "amount",
            "revenue": "revenue",
            "order": "orders",
            "payment": "payments",
            "user": "users",
            "count": "count",
            "ratio": "ratio",
            "percentage": "ratio",
        }
        metrics = [value for key, value in mapping.items() if key in normalized_question]
        return list(dict.fromkeys(metrics))[:6]

    def _extract_dimensions(self, normalized_question: str) -> list[str]:
        mapping = {
            "地区": "region",
            "地域": "region",
            "省": "province",
            "城市": "city",
            "市": "city",
            "年龄": "age",
            "岁": "age",
            "性别": "gender",
            "渠道": "channel",
            "日期": "date",
            "天": "date",
            "周": "week",
            "月": "month",
            "项目": "project",
            "region": "region",
            "province": "province",
            "city": "city",
            "age": "age",
            "gender": "gender",
            "channel": "channel",
            "date": "date",
            "day": "date",
            "week": "week",
            "month": "month",
            "project": "project",
        }
        dimensions = [value for key, value in mapping.items() if key in normalized_question]
        return list(dict.fromkeys(dimensions))[:6]

    def _requires_async(self, intent_type: str, selected_path: str) -> bool:
        if selected_path in {"HOT_MATERIALIZATION", "ON_DEMAND_COMPUTE"}:
            return True
        return intent_type in {"HOT_ANALYTICS", "AD_HOC_ANALYTICS"} and selected_path != "MEMORY_ONLY"

    def _looks_heavy(self, normalized_question: str) -> bool:
        return any(token in normalized_question for token in ["复杂", "join", "pb", "tb", "20张", "二十张", "重算", "全量", "complex", "20 tables", "recompute", "full load"])

    def _engine_strategy(self, selected_path: str) -> str:
        if selected_path == "MEMORY_ONLY":
            return "memory-index"
        if selected_path == "CONTRACT_FIRST":
            return "contract-serving"
        if selected_path == "HOT_MATERIALIZATION":
            return "clickhouse-hot-tier"
        return "trino-spark-hybrid"

    def _artifact_engine(self, selected_path: str) -> str:
        if selected_path == "HOT_MATERIALIZATION":
            return "clickhouse"
        return "trino"

    def _direct_result_summary(self, selected_path: str) -> str:
        if selected_path == "MEMORY_ONLY":
            return "已命中项目记忆与共享记忆，可直接返回结果。"
        if selected_path == "CONTRACT_FIRST":
            return "已命中稳定契约或已发布对象，可直接服务。"
        return "已完成轻量路径规划，未触发重型异步执行。"

    def _artifact_name(self, *, profile: dict[str, Any]) -> str:
        domain_key = profile.get("domain_key") or "general"
        suffix = uuid4().hex[:8]
        return f"{domain_key}_artifact_{suffix}"

    def _planner_rationale(self, *, selected_path: str, profile: dict[str, Any]) -> str:
        domain_label = profile.get("domain") or "通用主题"
        if selected_path == "MEMORY_ONLY":
            return f"当前问题更适合直接命中项目记忆与共享记忆，不需要触发重型计算。主题域优先归入“{domain_label}”。"
        if selected_path == "CONTRACT_FIRST":
            return f"当前问题已命中稳定契约或已发布对象，优先走契约服务路径，避免重复扫描底层数据。主题域优先归入“{domain_label}”。"
        if selected_path == "HOT_MATERIALIZATION":
            return f"当前问题属于高频分析候选，适合先生成热点工件建议，再由人工确认是否晋升长期物化结果。主题域优先归入“{domain_label}”。"
        return f"当前问题属于按需计算或重型分析候选，系统先生成异步执行计划和预备 SQL，由人工确认后再进入执行层。主题域优先归入“{domain_label}”。"

    def _materialization_reason(self, *, selected_path: str, profile: dict[str, Any]) -> str:
        domain_label = profile.get("domain") or "通用主题"
        if selected_path == "HOT_MATERIALIZATION":
            return f"该问题命中热点分析路径，建议将 {domain_label} 相关结果作为热点工件候选，优先放入分析仓服务层。"
        return "该问题当前更适合作为临时中间工件保留，待验证复用度后再决定是否晋升为长期物化结果。"

    def _build_stage_blueprint(self, *, profile: dict[str, Any], preview: dict[str, Any]) -> list[dict[str, Any]]:
        domain_label = profile["domain"]
        source_names = [item["source_name"] for item in preview["matched_sources"][:3]]
        source_comment = ", ".join(source_names) if source_names else "候选源"
        time_predicate = profile["time_scope"] or "最近可用时间窗口"
        return [
            {
                "stage_no": 1,
                "stage_key": "SCAN_PRUNE",
                "title": "扫描裁剪与预聚合",
                "goal": f"围绕 {domain_label} 主题域，从 {source_comment} 中裁剪目标时间范围并生成中间结果。",
                "engine_key": "spark-sql",
                "planning_payload": {"domain": domain_label, "time_scope": time_predicate},
                "prepared_sql": (
                    f"-- 阶段 1：扫描裁剪与预聚合\n"
                    f"-- 主题域: {domain_label}\n"
                    f"-- 时间范围: {time_predicate}\n"
                    "SELECT *\nFROM source_fact_table\nWHERE event_time BETWEEN <start_time> AND <end_time>;"
                ),
            },
            {
                "stage_no": 2,
                "stage_key": "JOIN_ENRICH",
                "title": "多表关联与宽化",
                "goal": "将中间结果与主题域相关维表进行关联，生成可供分析的宽化数据集。",
                "engine_key": "trino",
                "planning_payload": {"dimensions": profile["dimensions"], "metrics": profile["metrics"]},
                "prepared_sql": (
                    "-- 阶段 2：多表关联与宽化\n"
                    "SELECT f.*, d1.*, d2.*\n"
                    "FROM stage_1_fact f\n"
                    "LEFT JOIN dim_table_1 d1 ON f.dim_key = d1.dim_key\n"
                    "LEFT JOIN dim_table_2 d2 ON f.other_key = d2.other_key;"
                ),
            },
            {
                "stage_no": 3,
                "stage_key": "AGGREGATE_OUTPUT",
                "title": "聚合与结果生成",
                "goal": "按问题要求聚合结果并生成候选交付对象。",
                "engine_key": "clickhouse",
                "planning_payload": {"selected_path": preview["strategy"]},
                "prepared_sql": (
                    "-- 阶段 3：聚合与结果生成\n"
                    "SELECT date, region, sum(amount) AS total_amount\n"
                    "FROM stage_2_enriched\n"
                    "GROUP BY date, region;"
                ),
            },
            {
                "stage_no": 4,
                "stage_key": "PROMOTION_CHECK",
                "title": "热点工件评估",
                "goal": "根据命中频率、延迟目标和复用度判断是否晋升为长期热点工件。",
                "engine_key": "planner",
                "planning_payload": {"candidate_paths": profile["candidate_paths"]},
            },
        ]

    def _serialize_intent(self, item: QueryIntent | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "trace_id": item.trace_id,
            "question": item.question,
            "intent_type": item.intent_type,
            "domain": item.domain,
            "time_scope": item.time_scope,
            "dimensions": item.dimensions,
            "metrics": item.metrics,
            "operation_mode": item.operation_mode,
            "latency_expectation": item.latency_expectation,
            "candidate_paths": item.candidate_paths,
            "created_at": _iso(item.created_at),
        }

    def _serialize_plan(self, item: QueryPlan | None) -> dict[str, Any] | None:
        if item is None:
            return None
        return {
            "id": item.id,
            "trace_id": item.trace_id,
            "intent_id": item.intent_id,
            "selected_path": item.selected_path,
            "plan_status": item.plan_status,
            "engine_strategy": item.engine_strategy,
            "rationale": item.rationale,
            "plan_payload": item.plan_payload,
            "matched_payload": item.matched_payload,
            "created_at": _iso(item.created_at),
        }

    def _serialize_run(self, item: QueryRun) -> dict[str, Any]:
        return {
            "id": item.id,
            "trace_id": item.trace_id,
            "run_key": item.run_key,
            "intent_id": item.intent_id,
            "plan_id": item.plan_id,
            "execution_mode": item.execution_mode,
            "status": item.status,
            "current_stage": item.current_stage,
            "engine_family": item.engine_family,
            "result_summary": item.result_summary,
            "error_message": item.error_message,
            "metrics_payload": item.metrics_payload,
            "submitted_at": _iso(item.submitted_at),
            "started_at": _iso(item.started_at),
            "finished_at": _iso(item.finished_at),
            "created_at": _iso(item.created_at),
        }

    def _serialize_stage(self, item: ExecutionStage) -> dict[str, Any]:
        return {
            "id": item.id,
            "run_id": item.run_id,
            "stage_no": item.stage_no,
            "stage_key": item.stage_key,
            "title": item.title,
            "goal": item.goal,
            "engine_key": item.engine_key,
            "status": item.status,
            "planning_payload": item.planning_payload,
            "metrics_payload": item.metrics_payload,
            "started_at": _iso(item.started_at),
            "finished_at": _iso(item.finished_at),
            "error_message": item.error_message,
        }

    def _serialize_sql(self, item: ExecutedSQL) -> dict[str, Any]:
        return {
            "id": item.id,
            "run_id": item.run_id,
            "stage_id": item.stage_id,
            "engine_key": item.engine_key,
            "execution_role": item.execution_role,
            "status": item.status,
            "sql_hash": item.sql_hash,
            "sql_text": item.sql_text,
            "metrics_payload": item.metrics_payload,
            "submitted_at": _iso(item.submitted_at),
            "started_at": _iso(item.started_at),
            "finished_at": _iso(item.finished_at),
        }

    def _serialize_artifact(self, item: MaterializationArtifact) -> dict[str, Any]:
        return {
            "id": item.id,
            "trace_id": item.trace_id,
            "plan_id": item.plan_id,
            "run_id": item.run_id,
            "artifact_name": item.artifact_name,
            "artifact_type": item.artifact_type,
            "status": item.status,
            "heat_level": item.heat_level,
            "engine_key": item.engine_key,
            "storage_strategy": item.storage_strategy,
            "retention_policy": item.retention_policy,
            "reason": item.reason,
            "artifact_payload": item.artifact_payload,
            "last_promoted_at": _iso(item.last_promoted_at),
            "last_accessed_at": _iso(item.last_accessed_at),
            "expires_at": _iso(item.expires_at),
            "updated_at": _iso(item.updated_at),
        }
