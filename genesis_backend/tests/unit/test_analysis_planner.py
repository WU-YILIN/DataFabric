from src.domain.analysis_planner import (
    ConflictRoute,
    ConflictType,
    QuestionWeight,
    classify_question,
    normalize_question,
    route_conflict,
)


def test_normalize_question_extracts_metric_dimensions_and_missing_time_scope():
    normalized = normalize_question("为什么最近华东新客转化掉了？")

    assert normalized.metric_phrase == "新客转化"
    assert normalized.dimensions == ("华东",)
    assert normalized.time_scope is None
    assert normalized.missing_time_scope is True


def test_business_definition_mismatch_routes_to_approver_and_escalates_core_metrics():
    route = route_conflict(
        ConflictType.BUSINESS_DEFINITION_MISMATCH,
        is_core_metric=True,
    )

    assert route == ConflictRoute(
        conflict_type=ConflictType.BUSINESS_DEFINITION_MISMATCH,
        owner_role="APPROVER",
        escalation_roles=("OWNER", "ADMIN"),
        review_required=True,
    )


def test_field_fact_mismatch_routes_to_editor_and_escalates_cross_source_access():
    route = route_conflict(
        ConflictType.FIELD_FACT_MISMATCH,
        requires_cross_source_access=True,
    )

    assert route == ConflictRoute(
        conflict_type=ConflictType.FIELD_FACT_MISMATCH,
        owner_role="EDITOR",
        escalation_roles=("ADMIN",),
        review_required=True,
    )


def test_permission_blocker_routes_to_admin():
    route = route_conflict(ConflictType.PERMISSION_BLOCKER)

    assert route == ConflictRoute(
        conflict_type=ConflictType.PERMISSION_BLOCKER,
        owner_role="ADMIN",
        escalation_roles=(),
        review_required=True,
    )


def test_high_cost_review_routes_to_approver():
    route = route_conflict(ConflictType.HIGH_COST_REVIEW)

    assert route == ConflictRoute(
        conflict_type=ConflictType.HIGH_COST_REVIEW,
        owner_role="APPROVER",
        escalation_roles=(),
        review_required=True,
    )


def test_question_classification_marks_cross_domain_core_metric_as_heavy_review_required():
    normalized = normalize_question("为什么华东新客转化和投放成本一起掉了？")

    classification = classify_question(
        normalized,
        is_core_metric=True,
        cross_domain=True,
    )

    assert classification.weight is QuestionWeight.HEAVY
    assert classification.review_required is True
    assert classification.cross_domain is True
    assert classification.is_core_metric is True
