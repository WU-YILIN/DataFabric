from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

Role = Literal["VIEWER", "EDITOR", "APPROVER", "ADMIN", "OWNER"]


class ConflictType(StrEnum):
    BUSINESS_DEFINITION_MISMATCH = "BUSINESS_DEFINITION_MISMATCH"
    FIELD_FACT_MISMATCH = "FIELD_FACT_MISMATCH"
    PERMISSION_BLOCKER = "PERMISSION_BLOCKER"
    HIGH_COST_REVIEW = "HIGH_COST_REVIEW"


class QuestionWeight(StrEnum):
    LIGHT = "LIGHT"
    HEAVY = "HEAVY"


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
