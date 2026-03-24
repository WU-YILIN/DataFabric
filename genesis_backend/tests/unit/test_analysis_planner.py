from src.domain.analysis_planner import (
    ConflictRoute,
    ConflictType,
    EvidenceBundle,
    EvidenceItem,
    FieldFactEvidencePayload,
    EvidenceSourceType,
    HistoricalEvidencePayload,
    OfficialEvidencePayload,
    QuestionWeight,
    build_evidence_bundle,
    classify_question,
    normalize_question,
    route_conflict,
)


def test_normalize_question_extracts_metric_dimensions_and_missing_time_scope():
    normalized = normalize_question("为什么最近华东新客转化掉了？")

    assert normalized.primary_metric_phrase == "新客转化"
    assert normalized.metric_phrases == ("新客转化",)
    assert normalized.dimensions == ("华东",)
    assert normalized.time_scope is None
    assert normalized.missing_time_scope is True


def test_normalize_question_keeps_primary_metric_without_losing_secondary_metrics():
    normalized = normalize_question("为什么华东新客转化和投放成本一起掉了？")

    assert normalized.primary_metric_phrase == "新客转化"
    assert normalized.metric_phrases == ("新客转化", "投放成本")
    assert normalized.metric_domains == ("acquisition", "marketing")


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


def test_business_definition_mismatch_routes_to_approver_without_escalation_by_default():
    route = route_conflict(ConflictType.BUSINESS_DEFINITION_MISMATCH)

    assert route == ConflictRoute(
        conflict_type=ConflictType.BUSINESS_DEFINITION_MISMATCH,
        owner_role="APPROVER",
        escalation_roles=(),
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


def test_field_fact_mismatch_routes_to_editor_without_escalation_by_default():
    route = route_conflict(ConflictType.FIELD_FACT_MISMATCH)

    assert route == ConflictRoute(
        conflict_type=ConflictType.FIELD_FACT_MISMATCH,
        owner_role="EDITOR",
        escalation_roles=(),
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

    classification = classify_question(normalized, core_metrics=("新客转化",))

    assert classification.weight is QuestionWeight.HEAVY
    assert classification.review_required is True
    assert classification.cross_domain is True
    assert classification.is_core_metric is True


def test_question_classification_stays_light_without_review_for_single_domain_scoped_question():
    normalized = normalize_question("为什么本周华东投放成本掉了？")

    classification = classify_question(normalized)

    assert classification.weight is QuestionWeight.LIGHT
    assert classification.review_required is False
    assert classification.cross_domain is False
    assert classification.is_core_metric is False


def test_question_classification_marks_missing_time_only_as_review_required_but_light():
    normalized = normalize_question("为什么最近华东投放成本掉了？")

    classification = classify_question(normalized)

    assert classification.weight is QuestionWeight.LIGHT
    assert classification.review_required is True
    assert classification.cross_domain is False
    assert classification.is_core_metric is False


def test_build_evidence_bundle_keeps_source_types_separate():
    bundle = build_evidence_bundle(
        official_rows=[
            {
                "title": "GMV definition",
                "summary": "Official GMV business definition",
                "content": "Gross merchandise value definition.",
                "doc_type": "METRIC_DEFINITION",
                "module": "finance",
                "tags": ["gmv", "north_star"],
                "meta_payload": {"document_id": "doc-1"},
            }
        ],
        historical_rows=[
            {
                "name": "Revenue dashboard",
                "description": "Saved dashboard used last quarter",
                "kind": "dashboard",
                "scenario": "quarterly_review",
                "status": "active",
                "tags": ["revenue"],
                "query_payload": {"dashboard_id": "dash-1"},
                "cached_result_payload": {"rows": 12},
            }
        ],
        field_fact_rows=[
            {
                "name": "orders.gmv",
                "asset_type": "COLUMN",
                "source_system": "warehouse",
                "database_name": "analytics",
                "object_name": "orders",
                "domain": "sales",
                "description": "Schema field metadata",
                "schema_definition": {"type": "decimal"},
                "tags": ["fact"],
            }
        ],
    )

    assert bundle.official == (
        EvidenceItem(
            title="GMV definition",
            summary="Official GMV business definition",
            payload=OfficialEvidencePayload(
                content="Gross merchandise value definition.",
                doc_type="METRIC_DEFINITION",
                module="finance",
                tags=("gmv", "north_star"),
                meta_payload={"document_id": "doc-1"},
            ),
            source_type=EvidenceSourceType.OFFICIAL,
        ),
    )
    assert bundle.historical == (
        EvidenceItem(
            title="Revenue dashboard",
            summary="Saved dashboard used last quarter",
            payload=HistoricalEvidencePayload(
                kind="dashboard",
                scenario="quarterly_review",
                status="active",
                tags=("revenue",),
                query_payload={"dashboard_id": "dash-1"},
                cached_result_payload={"rows": 12},
            ),
            source_type=EvidenceSourceType.HISTORICAL,
        ),
    )
    assert bundle.field_facts == (
        EvidenceItem(
            title="orders.gmv",
            summary="Schema field metadata",
            payload=FieldFactEvidencePayload(
                asset_type="COLUMN",
                source_system="warehouse",
                database_name="analytics",
                object_name="orders",
                domain="sales",
                schema_definition={"type": "decimal"},
                tags=("fact",),
            ),
            source_type=EvidenceSourceType.FIELD_FACT,
        ),
    )


def test_build_evidence_bundle_returns_empty_typed_buckets_for_empty_inputs():
    bundle = build_evidence_bundle(
        official_rows=[],
        historical_rows=[],
        field_fact_rows=[],
    )

    assert bundle == EvidenceBundle(
        official=(),
        historical=(),
        field_facts=(),
    )


def test_build_evidence_bundle_preserves_fields_and_source_labels_in_each_bucket():
    bundle = build_evidence_bundle(
        official_rows=[
            {
                "title": "North Star Metric",
                "summary": "Company metric definition",
                "content": "Used in board reporting.",
                "doc_type": "KPI",
                "module": "finance",
                "tags": ["board", "kpi"],
                "meta_payload": {"document_id": "doc-9", "owner": "finance"},
            }
        ],
        historical_rows=[
            {
                "name": "Weekly Ops View",
                "description": "Analyst saved view",
                "kind": "saved_view",
                "scenario": "ops_review",
                "status": "published",
                "tags": ["ops", "weekly"],
                "query_payload": {"view_id": "view-2", "workspace": "ops"},
                "cached_result_payload": {"preview_rows": 20},
            }
        ],
        field_fact_rows=[
            {
                "name": "customer_tier",
                "asset_type": "COLUMN",
                "source_system": "crm",
                "database_name": "customer360",
                "object_name": "customer_profile",
                "domain": "customer",
                "description": "Dimension column",
                "schema_definition": {"asset_id": "asset-5", "data_type": "string"},
                "tags": ["dimension"],
            }
        ],
    )

    official_item = bundle.official[0]
    historical_item = bundle.historical[0]
    field_fact_item = bundle.field_facts[0]

    assert (official_item.title, official_item.summary, official_item.payload, official_item.source_type) == (
        "North Star Metric",
        "Company metric definition",
        OfficialEvidencePayload(
            content="Used in board reporting.",
            doc_type="KPI",
            module="finance",
            tags=("board", "kpi"),
            meta_payload={"document_id": "doc-9", "owner": "finance"},
        ),
        EvidenceSourceType.OFFICIAL,
    )
    assert (
        historical_item.title,
        historical_item.summary,
        historical_item.payload,
        historical_item.source_type,
    ) == (
        "Weekly Ops View",
        "Analyst saved view",
        HistoricalEvidencePayload(
            kind="saved_view",
            scenario="ops_review",
            status="published",
            tags=("ops", "weekly"),
            query_payload={"view_id": "view-2", "workspace": "ops"},
            cached_result_payload={"preview_rows": 20},
        ),
        EvidenceSourceType.HISTORICAL,
    )
    assert (
        field_fact_item.title,
        field_fact_item.summary,
        field_fact_item.payload,
        field_fact_item.source_type,
    ) == (
        "customer_tier",
        "Dimension column",
        FieldFactEvidencePayload(
            asset_type="COLUMN",
            source_system="crm",
            database_name="customer360",
            object_name="customer_profile",
            domain="customer",
            schema_definition={"asset_id": "asset-5", "data_type": "string"},
            tags=("dimension",),
        ),
        EvidenceSourceType.FIELD_FACT,
    )
