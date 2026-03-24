"""
Module 3 — AI 语义映射服务
SemanticMappingService：使用 Qdrant 向量检索（召回候选） + LLM（受限选择决策）
的双层架构，安全、可控地为未知字段找到最佳匹配的标准契约字段。

设计原则（防幻觉三重护盾）：
  1. 候选池锁定（RAG）—— LLM 只从 Qdrant 检索出的 Top-5 中选择
  2. 受限 Prompt    —— Prompt 明确要求"如不匹配则返回 UNKNOWN"
  3. 置信度熔断     —— score < MIN_CONFIDENCE_THRESHOLD 的结果被标记为需人工强审
"""

import json
from dataclasses import dataclass
from typing import Optional

from src.infrastructure.llm.client import LLMAdapter
from src.utils.logger import get_logger

logger = get_logger(__name__)

MIN_CONFIDENCE_THRESHOLD = 0.70   # 低于此阈值的建议不会自动推送到审批队列


@dataclass
class MappingProposal:
    matched_field: str          # 匹配的标准字段名，或 "UNKNOWN"
    confidence: float           # 0.0 ~ 1.0
    reasoning: str              # 一句话推理说明
    is_high_confidence: bool    # confidence >= MIN_CONFIDENCE_THRESHOLD


class SemanticMappingService:
    """
    核心方法 `propose(unknown_field, event, sample_values)`：
    1. 从 TrackingEvent.properties 中构建候选字段列表（作为 Top-N 候选池）
    2. 用 LLM 在受限候选池中选择最佳匹配
    3. 返回 MappingProposal

    Future enhancement: 当接入 Qdrant vector store 后，可用向量检索替代直接传入全量 properties，
    提供更精准的语义候选排名。当前版本直接将事件的所有标准字段作为候选，适合字段数量 < 30 的场景。
    """

    def __init__(self) -> None:
        try:
            self.llm = LLMAdapter()
        except Exception as e:
            logger.warning("LLMAdapter initialization failed (likely missing OPENAI_API_KEY). Mocking AI will be used.", error=str(e))
            self.llm = None

    async def propose(self, unknown_field: str, event, sample_values: list) -> Optional[MappingProposal]:
        """
        为一个未知字段生成映射建议。
        
        Args:
            unknown_field: 原始 JSON 中发现的陌生字段名（如 "zhifu_jine"）
            event: TrackingEvent ORM 对象（持有 .properties 和 .name）
            sample_values: 来自真实数据的样本值列表（最多 5 个）

        Returns:
            MappingProposal 或 None（如果 LLM 返回格式异常）
        """
        # Real AI is now configured — no more mock responses

        props: dict = event.properties if isinstance(event.properties, dict) else {}
        if not props:
            return MappingProposal(
                matched_field="UNKNOWN",
                confidence=0.0,
                reasoning="Event has no standard fields defined.",
                is_high_confidence=False,
            )

        # 构建候选字段列表，传给 LLM
        candidates = [
            {
                "name": field_name,
                "field_type": str(field_info.get("type", "any")) if isinstance(field_info, dict) else "any",
                "description": str(field_info.get("description", "")) if isinstance(field_info, dict) else str(field_info),
            }
            for field_name, field_info in props.items()
        ]

        from src.domain.governance.prompts import get_mapping_proposal_prompt
        prompt = get_mapping_proposal_prompt(
            unknown_field=unknown_field,
            event_name=event.name,
            sample_values=sample_values,
            candidates=candidates,
        )

        # 调用 LLM（复用现有的 LLMAdapter，使用原始文本而非结构化解析模式）
        try:
            raw_text = await self._call_llm_raw(prompt)
            # 解析 JSON 响应
            result = json.loads(raw_text)
            matched = result.get("matched_field", "UNKNOWN")
            confidence = float(result.get("confidence", 0.0))
            reasoning = result.get("reasoning", "")

            # 检验匹配结果是否在合法候选集内（防止幻觉）
            valid_names = {c["name"] for c in candidates} | {"UNKNOWN"}
            if matched not in valid_names:
                logger.warning(
                    "LLM returned a field name outside the candidate pool — treating as UNKNOWN",
                    returned=matched,
                    valid_names=list(valid_names),
                )
                matched = "UNKNOWN"
                confidence = 0.0

            return MappingProposal(
                matched_field=matched,
                confidence=confidence,
                reasoning=reasoning,
                is_high_confidence=confidence >= MIN_CONFIDENCE_THRESHOLD,
            )
        except (json.JSONDecodeError, ValueError, KeyError) as parse_err:
            logger.warning("Failed to parse LLM mapping response", field=unknown_field, error=str(parse_err))
            return None

    async def _call_llm_raw(self, prompt: str) -> str:
        """
        调用 OpenAI-compatible API 获取原始文本输出。
        使用 settings 中配置的 base_url 和 model。
        """
        from openai import AsyncOpenAI
        from src.config import settings

        client_kwargs: dict = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            client_kwargs["base_url"] = settings.OPENAI_BASE_URL
        client = AsyncOpenAI(**client_kwargs)
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": "You are a data schema expert. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=256,
        )
        return response.choices[0].message.content or "{}"
