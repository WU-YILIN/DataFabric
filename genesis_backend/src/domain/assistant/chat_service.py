from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.infrastructure.database.models.external_data_source import ExternalDataSource
from src.infrastructure.database.models.knowledge_document import KnowledgeDocument
from src.infrastructure.database.models.semantic_candidate import SemanticCandidate
from src.infrastructure.database.models.source_asset import SourceAsset
from src.infrastructure.database.models.source_field import SourceField
from src.infrastructure.database.models.source_field_profile import SourceFieldProfile


@dataclass
class ContextDoc:
    id: int
    title: str
    summary: str | None
    content: str
    knowledge_level: str
    status: str
    object_refs: list[dict[str, Any]]
    fact_refs: list[dict[str, Any]]
    score: int


@dataclass
class ContextSource:
    id: int
    source_name: str
    source_type: str
    status: str
    discovery_payload: dict[str, Any]
    score: int


@dataclass
class ContextAsset:
    id: int
    display_name: str
    qualified_name: str
    asset_type: str
    inferred_domain: str | None
    update_mode: str
    row_count_estimate: int
    score: int


@dataclass
class ContextField:
    id: int
    asset_id: int
    field_key: str
    field_name: str
    physical_type: str
    nullable: bool
    status: str
    latest_profile: dict[str, Any] | None
    candidates: list[dict[str, Any]]
    score: int


class AssistantChatService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def chat(
        self,
        *,
        project_id: int,
        tenant_id: int | None,
        messages: list[dict[str, str]],
        include_knowledge: bool,
        include_sources: bool,
        runtime_config: dict[str, Any] | None = None,
        query_trace: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        latest_question = next(
            (
                item["content"].strip()
                for item in reversed(messages)
                if item["role"] == "user" and item["content"].strip()
            ),
            "",
        )
        if not latest_question:
            raise ValueError("A user message is required")

        docs = await self._load_relevant_docs(project_id, tenant_id, latest_question) if include_knowledge else []
        sources = await self._load_relevant_sources(project_id, latest_question) if include_sources else []
        assets = await self._load_relevant_assets(project_id, latest_question) if include_sources else []
        fields = await self._load_relevant_fields(project_id, latest_question) if include_sources else []

        docs = self._filter_docs_by_context_refs(docs, query_trace)
        sources = self._filter_sources_by_context_refs(sources, query_trace)
        assets = self._filter_assets_by_context_refs(assets, query_trace)
        fields = self._filter_fields_by_context_refs(fields, query_trace)

        docs = self._apply_doc_planning_context(docs, query_trace)
        sources = self._apply_source_planning_context(sources, query_trace)
        assets = self._apply_asset_planning_context(assets, query_trace)
        fields = self._apply_field_planning_context(fields, docs, query_trace)

        citations = self._build_citations(fields, assets, docs, sources)
        client = self._build_client(runtime_config)
        model_name = str((runtime_config or {}).get("model") or settings.OPENAI_MODEL)

        if client is not None:
            try:
                answer = await self._answer_with_llm(
                    messages,
                    docs,
                    sources,
                    assets,
                    fields,
                    query_trace,
                    client=client,
                    model_name=model_name,
                )
                mode = "llm"
            except Exception:
                answer = self._fallback_answer(
                    latest_question,
                    docs,
                    sources,
                    assets,
                    fields,
                    query_trace=query_trace,
                )
                mode = "fallback"
        else:
            answer = self._fallback_answer(
                latest_question,
                docs,
                sources,
                assets,
                fields,
                query_trace=query_trace,
            )
            mode = "fallback"

        suggestions = self._build_suggestions(docs, sources, fields, query_trace=query_trace)
        return {
            "answer": answer,
            "mode": mode,
            "citations": citations[:12],
            "suggestions": suggestions,
        }

    async def _load_relevant_docs(
        self,
        project_id: int,
        tenant_id: int | None,
        query: str,
    ) -> list[ContextDoc]:
        result = await self.db.execute(select(KnowledgeDocument))
        docs = list(result.scalars().all())
        scoped_docs = [
            item
            for item in docs
            if item.status != "ARCHIVED"
            and (
                item.project_id == project_id
                or (
                    tenant_id is not None
                    and item.tenant_id == tenant_id
                    and "shared-memory" in (item.tags or [])
                )
            )
        ]

        ranked: list[ContextDoc] = []
        for item in scoped_docs:
            haystack = " ".join(
                filter(
                    None,
                    [
                        item.title,
                        item.summary,
                        item.content[:2500],
                        " ".join(item.tags or []),
                        item.knowledge_level or "",
                    ],
                )
            )
            score = self._score_text(query, haystack)
            if item.knowledge_level == "FIELD":
                score += 2
            if item.status == "PUBLISHED":
                score += 1
            if score <= 0 and query.strip():
                continue
            ranked.append(
                ContextDoc(
                    id=item.id,
                    title=item.title,
                    summary=item.summary,
                    content=item.content,
                    knowledge_level=item.knowledge_level or "BRIEF",
                    status=item.status,
                    object_refs=item.object_refs or [],
                    fact_refs=item.fact_refs or [],
                    score=score,
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.title.lower()))
        return ranked[:6]

    async def _load_relevant_sources(self, project_id: int, query: str) -> list[ContextSource]:
        result = await self.db.execute(
            select(ExternalDataSource).where(ExternalDataSource.project_id == project_id)
        )
        sources = list(result.scalars().all())
        ranked: list[ContextSource] = []
        for item in sources:
            discovery = item.discovery_payload or {}
            object_names = []
            for obj in discovery.get("objects", [])[:12]:
                schema_name = str(obj.get("schema") or "")
                table_name = str(obj.get("table_name") or "")
                object_names.append(f"{schema_name}.{table_name}".strip("."))
            haystack = " ".join(
                filter(
                    None,
                    [
                        item.source_name,
                        item.source_type,
                        item.status,
                        " ".join(object_names),
                    ],
                )
            )
            score = self._score_text(query, haystack)
            if score <= 0 and query.strip():
                continue
            ranked.append(
                ContextSource(
                    id=item.id,
                    source_name=item.source_name,
                    source_type=item.source_type,
                    status=item.status,
                    discovery_payload=discovery,
                    score=score,
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.source_name.lower()))
        return ranked[:4]

    async def _load_relevant_assets(self, project_id: int, query: str) -> list[ContextAsset]:
        result = await self.db.execute(select(SourceAsset).where(SourceAsset.project_id == project_id))
        assets = list(result.scalars().all())
        ranked: list[ContextAsset] = []
        for item in assets:
            metrics = item.metrics_payload or {}
            update_mode = str(metrics.get("update_mode") or "FULL_SNAPSHOT")
            row_count_estimate = int(metrics.get("row_count_estimate") or 0)
            haystack = " ".join(
                filter(
                    None,
                    [
                        item.display_name,
                        item.qualified_name,
                        item.asset_type,
                        item.inferred_domain,
                        update_mode,
                    ],
                )
            )
            score = self._score_text(query, haystack)
            if score <= 0 and query.strip():
                continue
            ranked.append(
                ContextAsset(
                    id=item.id,
                    display_name=item.display_name,
                    qualified_name=item.qualified_name,
                    asset_type=item.asset_type,
                    inferred_domain=item.inferred_domain,
                    update_mode=update_mode,
                    row_count_estimate=row_count_estimate,
                    score=score,
                )
            )
        ranked.sort(key=lambda item: (-item.score, item.qualified_name.lower()))
        return ranked[:6]

    async def _load_relevant_fields(self, project_id: int, query: str) -> list[ContextField]:
        field_result = await self.db.execute(select(SourceField).where(SourceField.project_id == project_id))
        fields = list(field_result.scalars().all())
        profile_result = await self.db.execute(
            select(SourceFieldProfile).where(SourceFieldProfile.project_id == project_id)
        )
        profiles = list(profile_result.scalars().all())
        candidate_result = await self.db.execute(
            select(SemanticCandidate).where(SemanticCandidate.project_id == project_id)
        )
        candidates = list(candidate_result.scalars().all())

        latest_profile_by_field: dict[int, SourceFieldProfile] = {}
        for profile in sorted(
            profiles,
            key=lambda item: (
                item.profiled_at.isoformat() if item.profiled_at else "",
                item.id,
            ),
            reverse=True,
        ):
            latest_profile_by_field.setdefault(profile.field_id, profile)

        candidates_by_field: dict[int, list[SemanticCandidate]] = {}
        for candidate in candidates:
            if candidate.field_id is None:
                continue
            candidates_by_field.setdefault(candidate.field_id, []).append(candidate)

        ranked: list[ContextField] = []
        for item in fields:
            haystack = " ".join(
                filter(
                    None,
                    [
                        item.field_key,
                        item.field_name,
                        item.display_name,
                        item.physical_type,
                    ],
                )
            )
            score = self._score_text(query, haystack)
            if item.is_primary_key_candidate or item.is_time_field_candidate:
                score += 1
            if score <= 0 and query.strip():
                continue
            profile = latest_profile_by_field.get(item.id)
            candidate_rows = candidates_by_field.get(item.id, [])
            ranked.append(
                ContextField(
                    id=item.id,
                    asset_id=item.asset_id,
                    field_key=item.field_key,
                    field_name=item.field_name,
                    physical_type=item.physical_type,
                    nullable=bool(item.nullable),
                    status=item.status,
                    latest_profile={
                        "null_ratio": profile.null_ratio,
                        "distinct_ratio": profile.distinct_ratio,
                        "sample_values": profile.sample_values or [],
                        "min_value": profile.min_value,
                        "max_value": profile.max_value,
                        "observed_row_count": profile.observed_row_count,
                    }
                    if profile
                    else None,
                    candidates=[
                        {
                            "id": candidate.id,
                            "candidate_type": candidate.candidate_type,
                            "candidate_value": candidate.candidate_value,
                            "confidence": candidate.confidence,
                            "reasoning": candidate.reasoning,
                            "status": candidate.status,
                        }
                        for candidate in sorted(
                            candidate_rows,
                            key=lambda value: (value.confidence or 0, value.id),
                            reverse=True,
                        )
                    ],
                    score=score,
                )
            )

        ranked.sort(key=lambda item: (-item.score, item.field_key.lower()))
        return ranked[:8]

    async def _answer_with_llm(
        self,
        messages: list[dict[str, str]],
        docs: list[ContextDoc],
        sources: list[ContextSource],
        assets: list[ContextAsset],
        fields: list[ContextField],
        query_trace: dict[str, Any] | None,
        *,
        client: AsyncOpenAI,
        model_name: str,
    ) -> str:
        context_sections: list[str] = []

        plan_context = self._build_query_trace_context(query_trace)
        if plan_context:
            context_sections.append(plan_context)

        if fields:
            field_blocks = []
            for item in fields[:6]:
                candidate_line = ", ".join(
                    f"{candidate['candidate_type']}({candidate['status']})"
                    for candidate in item.candidates[:3]
                ) or "无候选"
                profile = item.latest_profile or {}
                field_blocks.append(
                    f"[字段事实 #{item.id}] {item.field_key}\n"
                    f"类型: {item.physical_type}, 可空: {'是' if item.nullable else '否'}\n"
                    f"证据: null_ratio={profile.get('null_ratio', '-')}, distinct_ratio={profile.get('distinct_ratio', '-')}\n"
                    f"候选: {candidate_line}"
                )
            context_sections.append("字段级事实与候选：\n" + "\n\n".join(field_blocks))

        if assets:
            asset_blocks = []
            for item in assets[:6]:
                asset_blocks.append(
                    f"[资产事实 #{item.id}] {item.qualified_name}\n"
                    f"类型: {item.asset_type}, 主题域: {item.inferred_domain or '通用域'}, 更新语义: {item.update_mode}, 估算行数: {item.row_count_estimate}"
                )
            context_sections.append("资产级事实：\n" + "\n\n".join(asset_blocks))

        if docs:
            knowledge_blocks = []
            for item in docs[:6]:
                knowledge_blocks.append(
                    f"[知识 #{item.id}] {item.title}\n"
                    f"层级: {item.knowledge_level}, 状态: {item.status}, 事实引用数: {len(item.fact_refs)}\n"
                    f"摘要: {item.summary or '无'}\n"
                    f"内容: {item.content[:1200]}"
                )
            context_sections.append("知识与记忆：\n" + "\n\n".join(knowledge_blocks))

        if sources:
            source_blocks = []
            for item in sources[:4]:
                objects = item.discovery_payload.get("objects", [])[:6]
                object_lines = []
                for obj in objects:
                    object_lines.append(
                        f"- {obj.get('schema')}.{obj.get('table_name')} ({obj.get('column_count', 0)} 列)"
                    )
                source_blocks.append(
                    f"[源 #{item.id}] {item.source_name} ({item.source_type}, {item.status})\n"
                    + ("\n".join(object_lines) if object_lines else "- 暂无已扫描对象")
                )
            context_sections.append("接入源元数据：\n" + "\n\n".join(source_blocks))

        system_prompt = (
            "你是 DataFabric AI 助手。"
            "优先基于已确认事实回答；如果只有候选语义，必须明确标注为“待确认”或“候选判断”；"
            "如果没有足够证据，必须直接说明“当前没有足够证据”。"
            "回答尽量结构化，优先给结论，再给事实与建议。"
        )
        user_messages = [{"role": item["role"], "content": item["content"]} for item in messages[-12:]]
        if context_sections:
            user_messages.insert(0, {"role": "system", "content": "\n\n".join(context_sections)})

        response = await client.chat.completions.create(
            model=model_name,
            messages=[{"role": "system", "content": system_prompt}, *user_messages],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip() or "当前没有可用回答。"

    def _build_client(self, runtime_config: dict[str, Any] | None) -> AsyncOpenAI | None:
        config = runtime_config or {}
        api_key = str(config.get("api_key") or settings.OPENAI_API_KEY or "").strip()
        base_url = str(config.get("base_url") or settings.OPENAI_BASE_URL or "").strip()
        if not api_key:
            return None
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        return AsyncOpenAI(**client_kwargs)

    def _fallback_answer(
        self,
        question: str,
        docs: list[ContextDoc],
        sources: list[ContextSource],
        assets: list[ContextAsset],
        fields: list[ContextField],
        query_trace: dict[str, Any] | None = None,
    ) -> str:
        plan_context = self._build_query_trace_context(query_trace)
        if not docs and not sources and not assets and not fields:
            lines = [
                "当前没有足够证据来直接回答这个问题。",
                f"你的问题：{question}",
                "建议先完成数据源发现、候选纳管或补充知识对象后再继续查询。",
            ]
            if plan_context:
                lines.extend(["", plan_context])
            return "\n".join(lines)

        lines = [
            "当前环境没有可用的大模型密钥，以下内容基于已发现事实、候选语义和知识记忆自动整理。",
        ]
        if plan_context:
            lines.extend(["", plan_context])

        intent = (query_trace or {}).get("intent") or {}
        dimensions = [str(item).lower() for item in (intent.get("dimensions") or [])]
        metrics = [str(item).lower() for item in (intent.get("metrics") or [])]
        missing_field_hints = self._build_missing_field_hints(dimensions=dimensions, metrics=metrics)

        if intent.get("intent_type") in {"HOT_ANALYTICS", "AD_HOC_ANALYTICS"} and not fields and missing_field_hints:
            lines.append("\n当前还缺少可直接计算的字段事实：")
            lines.extend(f"- {item}" for item in missing_field_hints)
            lines.append("在这些字段完成发现、纳管或确认前，系统不会直接给出分析结果。")

        if fields:
            lines.append("\n已确认事实：")
            for item in fields[:4]:
                profile = item.latest_profile or {}
                evidence: list[str] = []
                if profile.get("distinct_ratio") is not None:
                    evidence.append(f"distinct_ratio={profile['distinct_ratio']}")
                if profile.get("null_ratio") is not None:
                    evidence.append(f"null_ratio={profile['null_ratio']}")
                nullable_label = "可空" if item.nullable else "非空"
                line = f"- 字段 {item.field_key}，类型 {item.physical_type}，{nullable_label}"
                if evidence:
                    line += f"，证据：{', '.join(evidence)}"
                lines.append(line)

        candidate_lines = [
            f"- {item.field_key}: {candidate['candidate_type']}（{candidate['status']}，置信度 {candidate['confidence']:.2f}）"
            for item in fields[:4]
            for candidate in item.candidates[:2]
        ]
        if candidate_lines:
            lines.append("\n待确认候选：")
            lines.extend(candidate_lines[:6])

        if docs:
            lines.append("\n引用记忆：")
            for item in docs[:4]:
                mode = "已发布知识" if item.status == "PUBLISHED" else "AI 简报/草稿"
                lines.append(f"- [{item.knowledge_level}] {item.title}（{mode}，事实引用 {len(item.fact_refs)}）")

        if assets and not fields:
            lines.append("\n相关资产：")
            for item in assets[:4]:
                lines.append(
                    f"- {item.qualified_name}（{item.asset_type}，主题域 {item.inferred_domain or '通用域'}，更新语义 {item.update_mode}）"
                )

        if sources and not assets:
            lines.append("\n相关数据源：")
            for item in sources[:3]:
                lines.append(f"- {item.source_name}（{item.source_type}，{item.status}）")

        lines.append(f"\n你的问题：{question}")
        lines.append("建议优先确认候选语义，再将已确认内容沉淀为字段级或资产级知识对象。")
        return "\n".join(lines)

    def _build_missing_field_hints(self, *, dimensions: list[str], metrics: list[str]) -> list[str]:
        hints: list[str] = []
        mapping = {
            "region": "地区/地域字段，例如 province、region、city 或 area_code",
            "province": "省份字段，例如 province、省、province_name",
            "city": "城市字段，例如 city、城市、city_name",
            "age": "年龄字段，例如 age，或可推导年龄的 birth_date / birthday",
            "gender": "性别字段，例如 gender、sex、gender_code",
        }
        for dimension in dimensions:
            hint = mapping.get(dimension)
            if hint and hint not in hints:
                hints.append(hint)
        if "ratio" in metrics and "用于计算占比/比例的分子与分母口径" not in hints:
            hints.append("用于计算占比/比例的分子与分母口径")
        if "count" in metrics and "用于统计人数/数量的主体字段，例如 user_id 或 entity_id" not in hints:
            hints.append("用于统计人数/数量的主体字段，例如 user_id 或 entity_id")
        return hints

    def _build_suggestions(
        self,
        docs: list[ContextDoc],
        sources: list[ContextSource],
        fields: list[ContextField],
        query_trace: dict[str, Any] | None = None,
    ) -> list[str]:
        suggestions: list[str] = []
        if fields:
            suggestions.append("总结当前命中的字段级事实和候选语义")
        if sources:
            suggestions.append("总结最近接入的数据源和结构变化")
        if docs:
            suggestions.append("基于当前项目记忆生成一份结构化简报")
        suggestions.extend(
            [
                "说明当前问题为什么走这条查询路径",
                "列出还缺少哪些事实证据才能做正式判断",
            ]
        )
        if query_trace:
            plan = query_trace.get("plan") or {}
            run = query_trace.get("run") or {}
            selected_path = str(plan.get("selected_path") or "").upper()
            execution_mode = str(run.get("execution_mode") or "").upper()
            if selected_path:
                suggestions.insert(0, f"解释当前为何命中 {selected_path} 路径")
            if execution_mode == "ASYNC":
                suggestions.append("查看异步执行计划、阶段和预备 SQL")
        unique: list[str] = []
        for item in suggestions:
            if item not in unique:
                unique.append(item)
        return unique[:4]

    def _build_query_trace_context(self, query_trace: dict[str, Any] | None) -> str:
        if not query_trace:
            return ""

        intent = query_trace.get("intent") or {}
        plan = query_trace.get("plan") or {}
        run = query_trace.get("run") or {}
        artifacts = query_trace.get("artifacts") or []

        lines = ["规划上下文："]
        trace_id = str(query_trace.get("trace_id") or "").strip()
        if trace_id:
            lines.append(f"- trace_id: {trace_id}")
        if intent.get("intent_type"):
            lines.append(f"- intent_type: {intent['intent_type']}")
        if intent.get("domain"):
            lines.append(f"- domain: {intent['domain']}")
        if plan.get("selected_path"):
            lines.append(f"- selected_path: {plan['selected_path']}")
        if run.get("execution_mode"):
            lines.append(f"- execution_mode: {run['execution_mode']}")
        if run.get("status"):
            lines.append(f"- run_status: {run['status']}")
        if artifacts:
            lines.append(f"- artifact_count: {len(artifacts)}")
        rationale = str(plan.get("rationale") or "").strip()
        if rationale:
            lines.append(f"- rationale: {rationale}")
        return "\n".join(lines)

    def _extract_context_refs(self, query_trace: dict[str, Any] | None) -> dict[str, set[int]]:
        context_refs = ((((query_trace or {}).get("plan") or {}).get("plan_payload") or {}).get("context_refs") or {})
        return {
            "documents": self._extract_context_ref_ids(context_refs.get("documents", [])),
            "sources": self._extract_context_ref_ids(context_refs.get("sources", [])),
            "assets": self._extract_context_ref_ids(context_refs.get("assets", [])),
            "fields": self._extract_context_ref_ids(context_refs.get("fields", [])),
            "contracts": self._extract_context_ref_ids(context_refs.get("contracts", [])),
        }

    def _extract_context_ref_ids(self, values: list[Any]) -> set[int]:
        refs: set[int] = set()
        for value in values or []:
            try:
                if isinstance(value, dict):
                    ref_id = value.get("id")
                    if ref_id is not None:
                        refs.add(int(ref_id))
                elif value is not None:
                    refs.add(int(value))
            except (TypeError, ValueError):
                continue
        return refs

    def _has_context_ref_payload(self, query_trace: dict[str, Any] | None) -> bool:
        plan_payload = (((query_trace or {}).get("plan") or {}).get("plan_payload") or {})
        return "context_refs" in plan_payload

    def _filter_docs_by_context_refs(
        self,
        docs: list[ContextDoc],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextDoc]:
        refs = self._extract_context_refs(query_trace)["documents"]
        if not refs:
            return [] if self._has_context_ref_payload(query_trace) else docs
        filtered = [item for item in docs if item.id in refs]
        return filtered or ([] if self._has_context_ref_payload(query_trace) else docs)

    def _filter_sources_by_context_refs(
        self,
        sources: list[ContextSource],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextSource]:
        refs = self._extract_context_refs(query_trace)["sources"]
        if not refs:
            return [] if self._has_context_ref_payload(query_trace) else sources
        filtered = [item for item in sources if item.id in refs]
        return filtered or ([] if self._has_context_ref_payload(query_trace) else sources)

    def _filter_assets_by_context_refs(
        self,
        assets: list[ContextAsset],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextAsset]:
        refs = self._extract_context_refs(query_trace)["assets"]
        if not refs:
            return [] if self._has_context_ref_payload(query_trace) else assets
        filtered = [item for item in assets if item.id in refs]
        return filtered or ([] if self._has_context_ref_payload(query_trace) else assets)

    def _filter_fields_by_context_refs(
        self,
        fields: list[ContextField],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextField]:
        refs = self._extract_context_refs(query_trace)["fields"]
        if not refs:
            return [] if self._has_context_ref_payload(query_trace) else fields
        filtered = [item for item in fields if item.id in refs]
        return filtered or ([] if self._has_context_ref_payload(query_trace) else fields)

    def _apply_doc_planning_context(
        self,
        docs: list[ContextDoc],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextDoc]:
        if not docs:
            return docs

        matched_memory_ids = {
            int(item["id"])
            for item in (((query_trace or {}).get("plan") or {}).get("matched_payload") or {}).get("memories", [])
            if item.get("id") is not None
        }
        selected_path = str((((query_trace or {}).get("plan") or {}).get("selected_path") or "")).upper()
        domain = str((((query_trace or {}).get("intent") or {}).get("domain") or "")).strip().lower()

        for item in docs:
            if item.id in matched_memory_ids:
                item.score += 10
            if selected_path == "MEMORY_ONLY" and item.status == "PUBLISHED":
                item.score += 2
            if domain and domain in f"{item.title} {item.summary or ''} {item.content[:300]}".lower():
                item.score += 2

        docs.sort(key=lambda value: (-value.score, value.title.lower()))
        return docs[:6]

    def _apply_source_planning_context(
        self,
        sources: list[ContextSource],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextSource]:
        if not sources:
            return sources

        matched_source_ids = {
            int(item["id"])
            for item in (((query_trace or {}).get("plan") or {}).get("matched_payload") or {}).get("sources", [])
            if item.get("id") is not None
        }
        domain = str((((query_trace or {}).get("intent") or {}).get("domain") or "")).strip().lower()

        for item in sources:
            if item.id in matched_source_ids:
                item.score += 10
            if domain and domain in item.source_name.lower():
                item.score += 2

        sources.sort(key=lambda value: (-value.score, value.source_name.lower()))
        return sources[:4]

    def _apply_asset_planning_context(
        self,
        assets: list[ContextAsset],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextAsset]:
        if not assets:
            return assets

        domain = str((((query_trace or {}).get("intent") or {}).get("domain") or "")).strip().lower()
        selected_path = str((((query_trace or {}).get("plan") or {}).get("selected_path") or "")).upper()

        for item in assets:
            if domain and (
                domain in (item.inferred_domain or "").lower()
                or domain in item.display_name.lower()
                or domain in item.qualified_name.lower()
            ):
                item.score += 4
            if selected_path == "HOT_MATERIALIZATION" and item.update_mode in {"APPEND", "UPSERT"}:
                item.score += 2

        assets.sort(key=lambda value: (-value.score, value.qualified_name.lower()))
        return assets[:6]

    def _apply_field_planning_context(
        self,
        fields: list[ContextField],
        docs: list[ContextDoc],
        query_trace: dict[str, Any] | None,
    ) -> list[ContextField]:
        if not fields:
            return fields

        matched_memory_ids = {
            int(item["id"])
            for item in (((query_trace or {}).get("plan") or {}).get("matched_payload") or {}).get("memories", [])
            if item.get("id") is not None
        }
        referenced_field_ids: set[int] = set()
        referenced_asset_ids: set[int] = set()
        for doc in docs:
            if matched_memory_ids and doc.id not in matched_memory_ids:
                continue
            for ref in doc.object_refs:
                object_type = str(ref.get("object_type") or "").upper()
                object_id = ref.get("object_id")
                if object_type == "FIELD" and object_id is not None:
                    referenced_field_ids.add(int(object_id))
                if object_type == "ASSET" and object_id is not None:
                    referenced_asset_ids.add(int(object_id))
            for ref in doc.fact_refs:
                fact_type = str(ref.get("fact_type") or "").upper()
                fact_id = ref.get("fact_id")
                if fact_type == "SOURCE_FIELD" and fact_id is not None:
                    referenced_field_ids.add(int(fact_id))

        domain = str((((query_trace or {}).get("intent") or {}).get("domain") or "")).strip().lower()
        for item in fields:
            if item.id in referenced_field_ids:
                item.score += 10
            if item.asset_id in referenced_asset_ids:
                item.score += 4
            if domain and domain in f"{item.field_key} {item.field_name}".lower():
                item.score += 2

        fields.sort(key=lambda value: (-value.score, value.field_key.lower()))
        return fields[:8]

    def _build_citations(
        self,
        fields: list[ContextField],
        assets: list[ContextAsset],
        docs: list[ContextDoc],
        sources: list[ContextSource],
    ) -> list[dict[str, Any]]:
        citations: list[dict[str, Any]] = []
        for field in fields:
            citations.append(
                {
                    "type": "SOURCE_FIELD",
                    "kind": "FACT",
                    "id": field.id,
                    "label": field.field_key,
                    "object_type": "FIELD",
                    "status": field.status,
                    "evidence_mode": "FACT",
                }
            )
            for candidate in field.candidates[:2]:
                citations.append(
                    {
                        "type": "SEMANTIC_CANDIDATE",
                        "kind": "CANDIDATE",
                        "id": candidate["id"],
                        "label": f"{field.field_name} -> {candidate['candidate_type']}",
                        "object_type": "FIELD",
                        "status": candidate["status"],
                        "evidence_mode": "CANDIDATE",
                    }
                )
        for item in docs[:6]:
            citations.append(
                {
                    "type": "KNOWLEDGE_DOC",
                    "kind": "BRIEF" if item.knowledge_level == "BRIEF" else "KNOWLEDGE",
                    "id": item.id,
                    "label": item.title,
                    "object_type": item.knowledge_level,
                    "status": item.status,
                    "evidence_mode": "FACT" if item.fact_refs else "EXPLANATION",
                }
            )
        for asset in assets[:4]:
            citations.append(
                {
                    "type": "SOURCE_ASSET",
                    "kind": "ASSET",
                    "id": asset.id,
                    "label": asset.qualified_name,
                    "object_type": "ASSET",
                    "status": "ACTIVE",
                    "evidence_mode": "FACT",
                }
            )
        for item in sources[:3]:
            citations.append(
                {
                    "type": "DATA_SOURCE",
                    "kind": "ASSET",
                    "id": item.id,
                    "label": item.source_name,
                    "object_type": "INSTANCE",
                    "status": item.status,
                    "evidence_mode": "FACT",
                }
            )
        return citations

    def _score_text(self, query: str, haystack: str) -> int:
        query_tokens = [token.lower() for token in query.replace("_", " ").split() if token.strip()]
        target = haystack.lower()
        if not query_tokens:
            return 0
        score = 0
        for token in query_tokens:
            if token in target:
                score += 2
        if query.lower() in target:
            score += 4
        return score
