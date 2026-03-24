from __future__ import annotations

from src.domain.analysis_planner.types import (
    ConflictRoute,
    ConflictType,
    NormalizedQuestion,
    QuestionClassification,
    QuestionWeight,
)


def route_conflict(
    conflict_type: ConflictType,
    *,
    is_core_metric: bool = False,
    requires_cross_source_access: bool = False,
) -> ConflictRoute:
    if conflict_type is ConflictType.BUSINESS_DEFINITION_MISMATCH:
        escalation_roles = ("OWNER", "ADMIN") if is_core_metric else ()
        return ConflictRoute(
            conflict_type=conflict_type,
            owner_role="APPROVER",
            escalation_roles=escalation_roles,
            review_required=True,
        )

    if conflict_type is ConflictType.FIELD_FACT_MISMATCH:
        escalation_roles = ("ADMIN",) if requires_cross_source_access else ()
        return ConflictRoute(
            conflict_type=conflict_type,
            owner_role="EDITOR",
            escalation_roles=escalation_roles,
            review_required=True,
        )

    if conflict_type is ConflictType.PERMISSION_BLOCKER:
        return ConflictRoute(
            conflict_type=conflict_type,
            owner_role="ADMIN",
            escalation_roles=(),
            review_required=True,
        )

    return ConflictRoute(
        conflict_type=conflict_type,
        owner_role="APPROVER",
        escalation_roles=(),
        review_required=True,
    )


def classify_question(
    normalized: NormalizedQuestion,
    *,
    core_metrics: tuple[str, ...] = (),
) -> QuestionClassification:
    is_core_metric = any(metric in core_metrics for metric in normalized.metric_phrases)
    cross_domain = len(set(normalized.metric_domains)) > 1
    review_required = cross_domain or is_core_metric or normalized.missing_time_scope
    weight = QuestionWeight.HEAVY if cross_domain or is_core_metric else QuestionWeight.LIGHT
    return QuestionClassification(
        weight=weight,
        review_required=review_required,
        cross_domain=cross_domain,
        is_core_metric=is_core_metric,
    )
