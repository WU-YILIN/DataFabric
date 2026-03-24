from __future__ import annotations

from src.domain.analysis_planner.types import NormalizedQuestion

REGION_DIMENSIONS = ("华东", "华南", "华北", "华中", "西南", "西北", "东北")
TIME_HINTS = ("本周", "本月", "本季度", "本年", "昨天", "今天", "上周", "上月")


def normalize_question(question: str) -> NormalizedQuestion:
    metric_phrase = None
    if "新客转化" in question:
        metric_phrase = "新客转化"
    elif "投放成本" in question:
        metric_phrase = "投放成本"

    dimensions = tuple(region for region in REGION_DIMENSIONS if region in question)

    time_scope = next((hint for hint in TIME_HINTS if hint in question), None)
    missing_time_scope = "最近" in question and time_scope is None

    return NormalizedQuestion(
        raw_question=question,
        metric_phrase=metric_phrase,
        dimensions=dimensions,
        time_scope=time_scope,
        missing_time_scope=missing_time_scope,
    )
