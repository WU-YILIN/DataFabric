from __future__ import annotations

from collections.abc import Iterable

from src.domain.analysis_planner.types import (
    EvidenceBundle,
    EvidenceItem,
    EvidenceSourceType,
    FieldFactEvidencePayload,
    FieldFactEvidenceRow,
    HistoricalEvidencePayload,
    HistoricalEvidenceRow,
    OfficialEvidencePayload,
    OfficialEvidenceRow,
)


def _build_official_bucket(rows: Iterable[OfficialEvidenceRow]) -> tuple[EvidenceItem[OfficialEvidencePayload], ...]:
    return tuple(
        EvidenceItem(
            title=row["title"],
            summary=row["summary"],
            payload=OfficialEvidencePayload(
                content=row["content"],
                doc_type=row["doc_type"],
                module=row["module"],
                tags=tuple(row["tags"]),
                meta_payload=dict(row["meta_payload"]),
            ),
            source_type=EvidenceSourceType.OFFICIAL,
        )
        for row in rows
    )


def _build_historical_bucket(rows: Iterable[HistoricalEvidenceRow]) -> tuple[EvidenceItem[HistoricalEvidencePayload], ...]:
    return tuple(
        EvidenceItem(
            title=row["name"],
            summary=row["description"],
            payload=HistoricalEvidencePayload(
                kind=row["kind"],
                scenario=row["scenario"],
                status=row["status"],
                tags=tuple(row["tags"]),
                query_payload=dict(row["query_payload"]),
                cached_result_payload=dict(row["cached_result_payload"]),
            ),
            source_type=EvidenceSourceType.HISTORICAL,
        )
        for row in rows
    )


def _build_field_fact_bucket(rows: Iterable[FieldFactEvidenceRow]) -> tuple[EvidenceItem[FieldFactEvidencePayload], ...]:
    return tuple(
        EvidenceItem(
            title=row["name"],
            summary=row["description"],
            payload=FieldFactEvidencePayload(
                asset_type=row["asset_type"],
                source_system=row["source_system"],
                database_name=row["database_name"],
                object_name=row["object_name"],
                domain=row["domain"],
                schema_definition=dict(row["schema_definition"]),
                tags=tuple(row["tags"]),
            ),
            source_type=EvidenceSourceType.FIELD_FACT,
        )
        for row in rows
    )


def build_evidence_bundle(
    *,
    official_rows: Iterable[OfficialEvidenceRow],
    historical_rows: Iterable[HistoricalEvidenceRow],
    field_fact_rows: Iterable[FieldFactEvidenceRow],
) -> EvidenceBundle:
    return EvidenceBundle(
        official=_build_official_bucket(official_rows),
        historical=_build_historical_bucket(historical_rows),
        field_facts=_build_field_fact_bucket(field_fact_rows),
    )
