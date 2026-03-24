from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Generic, Literal, TypeAlias, TypeVar, TypedDict

Role = Literal["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"]

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = dict[str, JsonValue]


class ConflictType(StrEnum):
    BUSINESS_DEFINITION_MISMATCH = "BUSINESS_DEFINITION_MISMATCH"
    FIELD_FACT_MISMATCH = "FIELD_FACT_MISMATCH"
    PERMISSION_BLOCKER = "PERMISSION_BLOCKER"
    HIGH_COST_REVIEW = "HIGH_COST_REVIEW"


class QuestionWeight(StrEnum):
    LIGHT = "LIGHT"
    HEAVY = "HEAVY"


class EvidenceSourceType(StrEnum):
    OFFICIAL = "OFFICIAL"
    HISTORICAL = "HISTORICAL"
    FIELD_FACT = "FIELD_FACT"


@dataclass(frozen=True)
class NormalizedQuestion:
    raw_question: str
    primary_metric_phrase: str | None
    metric_phrases: tuple[str, ...]
    metric_domains: tuple[str, ...]
    dimensions: tuple[str, ...]
    time_scope: str | None
    missing_time_scope: bool


@dataclass(frozen=True)
class ConflictRoute:
    conflict_type: ConflictType
    owner_role: Role
    escalation_roles: tuple[Role, ...]
    review_required: bool


@dataclass(frozen=True)
class QuestionClassification:
    weight: QuestionWeight
    review_required: bool
    cross_domain: bool
    is_core_metric: bool


@dataclass(frozen=True)
class OfficialEvidencePayload:
    content: str
    doc_type: str
    module: str
    tags: tuple[str, ...]
    meta_payload: JsonObject


@dataclass(frozen=True)
class HistoricalEvidencePayload:
    kind: str
    scenario: str
    status: str
    tags: tuple[str, ...]
    query_payload: JsonObject
    cached_result_payload: JsonObject


@dataclass(frozen=True)
class FieldFactEvidencePayload:
    asset_type: str
    source_system: str
    database_name: str
    object_name: str
    domain: str
    schema_definition: JsonObject
    tags: tuple[str, ...]


EvidencePayload = OfficialEvidencePayload | HistoricalEvidencePayload | FieldFactEvidencePayload
PayloadT = TypeVar("PayloadT", bound=EvidencePayload)


@dataclass(frozen=True)
class EvidenceItem(Generic[PayloadT]):
    title: str
    summary: str
    payload: PayloadT
    source_type: EvidenceSourceType


@dataclass(frozen=True)
class EvidenceBundle:
    official: tuple[EvidenceItem[OfficialEvidencePayload], ...]
    historical: tuple[EvidenceItem[HistoricalEvidencePayload], ...]
    field_facts: tuple[EvidenceItem[FieldFactEvidencePayload], ...]


class OfficialEvidenceRow(TypedDict):
    title: str
    summary: str
    content: str
    doc_type: str
    module: str
    tags: list[str]
    meta_payload: JsonObject


class HistoricalEvidenceRow(TypedDict):
    name: str
    description: str
    kind: str
    scenario: str
    status: str
    tags: list[str]
    query_payload: JsonObject
    cached_result_payload: JsonObject


class FieldFactEvidenceRow(TypedDict):
    name: str
    asset_type: str
    source_system: str
    database_name: str
    object_name: str
    domain: str
    description: str
    schema_definition: JsonObject
    tags: list[str]
