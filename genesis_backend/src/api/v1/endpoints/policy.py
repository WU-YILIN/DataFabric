import json
import re
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, TENANT_ELEVATED_ROLES, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.policy_rule import PolicyRule
from src.infrastructure.database.models.policy_rule_version import PolicyRuleVersion
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

RULE_TYPES = {
    "EVENT_NAMING",
    "EVENT_SCHEMA",
    "GOVERNANCE_POLICY",
    "DQ_TEMPLATE",
    "APPROVAL_POLICY",
    "PIPELINE_POLICY",
    "ACCESS_POLICY",
}
SCOPE_TYPES = {"GLOBAL", "TENANT", "PROJECT", "DOMAIN"}
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
RULE_STATUSES = {"DRAFT", "ACTIVE", "INACTIVE", "ARCHIVED"}
POLICY_WRITE_ROLES = {"OWNER", "ADMIN", "APPROVER"}

RULE_TEMPLATES: dict[str, dict[str, Any]] = {
    "EVENT_NAMING_STANDARD": {
        "key": "EVENT_NAMING_STANDARD",
        "rule_type": "EVENT_NAMING",
        "name": "Event naming standard",
        "description": "Event names should follow namespace.action format and snake_case tokens.",
        "severity": "MEDIUM",
        "scope_type": "PROJECT",
        "conditions_payload": {
            "regex_event_name": r"^[a-z]+(\.[a-z0-9_]+)+$",
        },
        "actions_payload": {
            "on_violation": "WARN",
            "recommendation": "Use lowercase namespace.action with snake_case segments.",
        },
        "content_payload": {
            "guidance": "Example: commerce.order_created",
        },
    },
    "DQ_FAILURE_GUARD": {
        "key": "DQ_FAILURE_GUARD",
        "rule_type": "DQ_TEMPLATE",
        "name": "DQ max failure guard",
        "description": "Block release when DQ failure rate exceeds configured threshold.",
        "severity": "HIGH",
        "scope_type": "PROJECT",
        "conditions_payload": {
            "max_failure_rate": 0.05,
        },
        "actions_payload": {
            "on_violation": "REJECT",
            "recommendation": "Investigate failing partitions and rerun quality checks.",
        },
        "content_payload": {
            "guidance": "If failure_rate > 5%, approval should be blocked.",
        },
    },
    "GOVERNANCE_APPROVAL_GATE": {
        "key": "GOVERNANCE_APPROVAL_GATE",
        "rule_type": "APPROVAL_POLICY",
        "name": "High risk approval gate",
        "description": "Require governance approver for high risk changes.",
        "severity": "HIGH",
        "scope_type": "TENANT",
        "conditions_payload": {
            "min_risk_score": 0.7,
            "modules": ["GOVERNANCE", "PIPELINES", "DATA_QUALITY"],
        },
        "actions_payload": {
            "on_violation": "WARN",
            "recommendation": "Route to APPROVER or ADMIN for final decision.",
        },
        "content_payload": {
            "guidance": "Escalate when risk_score >= 0.7",
        },
    },
}


class PolicyRuleCreateRequest(BaseModel):
    template_key: str | None = Field(default=None, max_length=128)
    rule_type: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    severity: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    scope_type: str | None = Field(default=None, max_length=32)
    scope_value: str | None = Field(default=None, max_length=255)
    project_id: int | None = Field(default=None, ge=1)
    conditions_payload: dict[str, Any] = Field(default_factory=dict)
    actions_payload: dict[str, Any] = Field(default_factory=dict)
    content_payload: dict[str, Any] = Field(default_factory=dict)
    prompt_text: str | None = Field(default=None, max_length=4000)
    change_note: str | None = Field(default=None, max_length=1000)


class PolicyRuleUpdateRequest(BaseModel):
    rule_type: str | None = Field(default=None, max_length=64)
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=1000)
    severity: str | None = Field(default=None, max_length=32)
    status: str | None = Field(default=None, max_length=32)
    scope_type: str | None = Field(default=None, max_length=32)
    scope_value: str | None = Field(default=None, max_length=255)
    project_id: int | None = Field(default=None, ge=1)
    conditions_payload: dict[str, Any] | None = None
    actions_payload: dict[str, Any] | None = None
    content_payload: dict[str, Any] | None = None
    prompt_text: str | None = Field(default=None, max_length=4000)
    change_note: str | None = Field(default=None, max_length=1000)


class PolicyRuleActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=32)
    change_note: str | None = Field(default=None, max_length=1000)


class PolicyRuleRollbackRequest(BaseModel):
    change_note: str | None = Field(default=None, max_length=1000)


class PolicyEvaluateRequest(BaseModel):
    module: str = Field(..., min_length=2, max_length=128)
    action: str = Field(..., min_length=2, max_length=64)
    context_payload: dict[str, Any] = Field(default_factory=dict)
    include_draft: bool = Field(default=False)
    limit: int = Field(default=200, ge=1, le=500)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _safe_json_loads(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _normalize_enum(value: str, *, allowed: set[str], field_name: str) -> str:
    normalized = value.strip().upper()
    if normalized not in allowed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported {field_name}: {value}")
    return normalized


def _actor(context: RequestContext) -> str:
    return context.user.email if context.user else parse_actor(context.actor_id)


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Policy API requires bearer user context")


def _require_policy_write(context: RequestContext) -> None:
    project_role = (context.project_role or "").upper()
    tenant_role = (context.tenant_role or "").upper()
    if project_role in POLICY_WRITE_ROLES:
        return
    if tenant_role in TENANT_ELEVATED_ROLES and (POLICY_WRITE_ROLES & TENANT_ELEVATED_ROLES):
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied for policy mutation")


def _tenant_id_from_context(context: RequestContext) -> int:
    if context.project.tenant_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current project has no tenant")
    return context.project.tenant_id


async def _validate_project_belongs_tenant(
    db: AsyncSession,
    *,
    tenant_id: int,
    project_id: int,
) -> Project:
    project_result = await db.execute(
        select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id)
    )
    project = project_result.scalar_one_or_none()
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _apply_template_payload(request: PolicyRuleCreateRequest) -> dict[str, Any]:
    base = {
        "rule_type": request.rule_type,
        "name": request.name,
        "description": request.description,
        "severity": request.severity,
        "status": request.status,
        "scope_type": request.scope_type,
        "scope_value": request.scope_value,
        "conditions_payload": request.conditions_payload,
        "actions_payload": request.actions_payload,
        "content_payload": request.content_payload,
        "prompt_text": request.prompt_text,
    }

    if request.template_key is None:
        return base

    template_key = request.template_key.strip().upper()
    template = RULE_TEMPLATES.get(template_key)
    if template is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Template not found: {request.template_key}")

    merged = dict(base)
    if not merged.get("rule_type"):
        merged["rule_type"] = template["rule_type"]
    if not merged.get("name"):
        merged["name"] = template["name"]
    if not merged.get("description"):
        merged["description"] = template["description"]
    if not merged.get("severity"):
        merged["severity"] = template["severity"]
    if not merged.get("scope_type"):
        merged["scope_type"] = template["scope_type"]
    if not isinstance(merged.get("conditions_payload"), dict) or not merged["conditions_payload"]:
        merged["conditions_payload"] = dict(template.get("conditions_payload", {}))
    if not isinstance(merged.get("actions_payload"), dict) or not merged["actions_payload"]:
        merged["actions_payload"] = dict(template.get("actions_payload", {}))
    if not isinstance(merged.get("content_payload"), dict) or not merged["content_payload"]:
        merged["content_payload"] = dict(template.get("content_payload", {}))
    return merged


def _build_snapshot(rule: PolicyRule) -> dict[str, Any]:
    return {
        "rule_type": rule.rule_type,
        "name": rule.name,
        "description": rule.description,
        "severity": rule.severity,
        "status": rule.status,
        "scope_type": rule.scope_type,
        "scope_value": rule.scope_value,
        "project_id": rule.project_id,
        "conditions_payload": dict(rule.conditions_payload or {}),
        "actions_payload": dict(rule.actions_payload or {}),
        "content_payload": dict(rule.content_payload or {}),
        "prompt_text": rule.prompt_text,
    }


def _rule_to_row(rule: PolicyRule, project_name: str | None = None) -> dict[str, Any]:
    return {
        "id": rule.id,
        "rule_type": rule.rule_type,
        "name": rule.name,
        "description": rule.description,
        "severity": rule.severity,
        "status": rule.status,
        "scope": {
            "scope_type": rule.scope_type,
            "scope_value": rule.scope_value,
            "project_id": rule.project_id,
            "project_name": project_name,
        },
        "conditions_payload": rule.conditions_payload or {},
        "actions_payload": rule.actions_payload or {},
        "content_payload": rule.content_payload or {},
        "prompt_text": rule.prompt_text,
        "version_no": rule.version_no,
        "created_by": rule.created_by,
        "updated_by": rule.updated_by,
        "created_at": _to_iso(rule.created_at),
        "updated_at": _to_iso(rule.updated_at),
    }


def _version_to_row(version: PolicyRuleVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "version_no": version.version_no,
        "change_note": version.change_note,
        "snapshot_payload": version.snapshot_payload or {},
        "created_by": version.created_by,
        "created_at": _to_iso(version.created_at),
    }


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    rule_id: int | str,
    details: dict[str, Any],
) -> None:
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "POLICY_RULE",
            "entity_id": str(rule_id),
            "user_id": context.actor_id,
            "details": json.dumps(details, ensure_ascii=True, default=str),
        }
    )


async def _append_version(
    db: AsyncSession,
    *,
    rule: PolicyRule,
    version_no: int,
    change_note: str | None,
    actor: str,
) -> PolicyRuleVersion:
    return await BaseRepository(PolicyRuleVersion, db).create(
        {
            "rule_id": rule.id,
            "version_no": version_no,
            "change_note": change_note,
            "snapshot_payload": _build_snapshot(rule),
            "created_by": actor,
        }
    )

async def _rule_matches_scope(
    rule: PolicyRule,
    *,
    project_id: int,
    domain_value: str | None,
) -> bool:
    if rule.scope_type in {"GLOBAL", "TENANT"}:
        return True
    if rule.scope_type == "PROJECT":
        return rule.project_id == project_id
    if rule.scope_type == "DOMAIN":
        if not rule.scope_value:
            return True
        if not domain_value:
            return False
        return rule.scope_value.strip().lower() == domain_value.strip().lower()
    return False


def _rule_decision_default(rule: PolicyRule) -> str:
    configured = str((rule.actions_payload or {}).get("on_violation", "")).strip().upper()
    if configured in {"WARN", "REJECT"}:
        return configured
    if rule.severity in {"HIGH", "CRITICAL"}:
        return "REJECT"
    return "WARN"


def _evaluate_single_rule(
    rule: PolicyRule,
    *,
    module: str,
    action: str,
    context_payload: dict[str, Any],
) -> tuple[bool, list[str]]:
    conditions = rule.conditions_payload or {}
    violations: list[str] = []

    modules = conditions.get("modules")
    if isinstance(modules, list):
        normalized = {str(item).strip().upper() for item in modules if str(item).strip()}
        if normalized and module not in normalized and "*" not in normalized:
            return False, []

    actions = conditions.get("actions")
    if isinstance(actions, list):
        normalized = {str(item).strip().upper() for item in actions if str(item).strip()}
        if normalized and action not in normalized and "*" not in normalized:
            return False, []

    required_fields = conditions.get("required_fields")
    fields = context_payload.get("fields")
    if isinstance(required_fields, list):
        field_set = set(fields.keys()) if isinstance(fields, dict) else set()
        missing = [str(item) for item in required_fields if str(item) and str(item) not in field_set]
        if missing:
            violations.append(f"Missing required fields: {', '.join(missing)}")

    forbidden_fields = conditions.get("forbidden_fields")
    if isinstance(forbidden_fields, list) and isinstance(fields, dict):
        blocked = [str(item) for item in forbidden_fields if str(item) and str(item) in fields]
        if blocked:
            violations.append(f"Forbidden fields present: {', '.join(blocked)}")

    max_failure_rate = conditions.get("max_failure_rate")
    if max_failure_rate is not None:
        try:
            threshold = float(max_failure_rate)
            current = float(context_payload.get("failure_rate", 0.0))
            if current > threshold:
                violations.append(f"failure_rate {current:.4f} exceeds threshold {threshold:.4f}")
        except (TypeError, ValueError):
            pass

    min_risk_score = conditions.get("min_risk_score")
    if min_risk_score is not None:
        try:
            threshold = float(min_risk_score)
            current = float(context_payload.get("risk_score", 0.0))
            if current >= threshold:
                violations.append(f"risk_score {current:.4f} reaches escalation threshold {threshold:.4f}")
        except (TypeError, ValueError):
            pass

    pattern = conditions.get("regex_event_name")
    if pattern:
        event_name = str(context_payload.get("event_name", "")).strip()
        if event_name and re.match(str(pattern), event_name) is None:
            violations.append(f"event_name '{event_name}' does not match regex")

    return True, violations


@router.get("/overview")
async def get_policy_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)

    result = await db.execute(select(PolicyRule).where(PolicyRule.tenant_id == tenant_id))
    rows = list(result.scalars().all())

    status_counter = Counter(row.status for row in rows)
    type_counter = Counter(row.rule_type for row in rows)
    scope_counter = Counter(row.scope_type for row in rows)

    audit_result = await db.execute(
        select(AuditLog)
        .where(and_(AuditLog.entity_type == "POLICY_RULE", build_project_audit_filter(context.project.id)))
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(20)
    )
    recent_activity = []
    for row in audit_result.scalars().all():
        details = _safe_json_loads(row.details)
        recent_activity.append(
            {
                "id": row.id,
                "timestamp": _to_iso(row.timestamp),
                "actor": parse_actor(row.user_id),
                "action": row.action,
                "rule_id": row.entity_id,
                "summary": details.get("summary") or details.get("message") or "",
            }
        )

    return success_response(
        {
            "summary": {
                "total_rules": len(rows),
                "active_rules": status_counter.get("ACTIVE", 0),
                "draft_rules": status_counter.get("DRAFT", 0),
                "inactive_rules": status_counter.get("INACTIVE", 0),
                "archived_rules": status_counter.get("ARCHIVED", 0),
                "project_scoped_rules": scope_counter.get("PROJECT", 0),
            },
            "status_distribution": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
            "type_distribution": [{"rule_type": key, "count": type_counter[key]} for key in sorted(type_counter.keys())],
            "scope_distribution": [{"scope_type": key, "count": scope_counter[key]} for key in sorted(scope_counter.keys())],
            "recent_activity": recent_activity,
        }
    )


@router.get("/templates")
async def list_policy_templates(
    context: RequestContext = Depends(get_request_context),
):
    _require_user_context(context)
    items = []
    for key in sorted(RULE_TEMPLATES.keys()):
        template = RULE_TEMPLATES[key]
        items.append(
            {
                "key": key,
                "rule_type": template["rule_type"],
                "name": template["name"],
                "description": template.get("description"),
                "severity": template["severity"],
                "scope_type": template["scope_type"],
                "conditions_payload": template.get("conditions_payload", {}),
                "actions_payload": template.get("actions_payload", {}),
                "content_payload": template.get("content_payload", {}),
            }
        )
    return success_response({"items": items, "total": len(items)})


@router.get("/rules")
async def list_policy_rules(
    q: str | None = Query(default=None),
    rule_type: str | None = Query(default=None),
    scope_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    project_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)

    normalized_type = _normalize_enum(rule_type, allowed=RULE_TYPES, field_name="rule_type") if rule_type else None
    normalized_scope = _normalize_enum(scope_type, allowed=SCOPE_TYPES, field_name="scope_type") if scope_type else None
    normalized_status = _normalize_enum(status_filter, allowed=RULE_STATUSES, field_name="status") if status_filter else None
    normalized_severity = _normalize_enum(severity, allowed=SEVERITIES, field_name="severity") if severity else None

    query = select(PolicyRule).where(PolicyRule.tenant_id == tenant_id)
    if normalized_type:
        query = query.where(PolicyRule.rule_type == normalized_type)
    if normalized_scope:
        query = query.where(PolicyRule.scope_type == normalized_scope)
    if normalized_status:
        query = query.where(PolicyRule.status == normalized_status)
    if normalized_severity:
        query = query.where(PolicyRule.severity == normalized_severity)
    if project_id is not None:
        query = query.where(PolicyRule.project_id == project_id)

    result = await db.execute(query.order_by(PolicyRule.updated_at.desc(), PolicyRule.id.desc()))
    rows = list(result.scalars().all())

    if q and q.strip():
        keyword = q.strip().lower()
        filtered = []
        for row in rows:
            text = " ".join([row.name or "", row.rule_type or "", row.description or "", row.scope_type or ""]).lower()
            if keyword in text:
                filtered.append(row)
        rows = filtered

    project_ids = sorted({row.project_id for row in rows if row.project_id is not None})
    project_map: dict[int, Project] = {}
    if project_ids:
        project_result = await db.execute(select(Project).where(Project.id.in_(project_ids)))
        project_map = {item.id: item for item in project_result.scalars().all()}

    total = len(rows)
    page_rows = rows[offset : offset + limit]

    status_counter = Counter(item.status for item in rows)
    type_counter = Counter(item.rule_type for item in rows)
    scope_counter = Counter(item.scope_type for item in rows)
    severity_counter = Counter(item.severity for item in rows)

    return success_response(
        {
            "items": [_rule_to_row(row, project_name=project_map.get(row.project_id).name if row.project_id in project_map else None) for row in page_rows],
            "total": total,
            "limit": limit,
            "offset": offset,
            "facets": {
                "statuses": [{"status": key, "count": status_counter[key]} for key in sorted(status_counter.keys())],
                "rule_types": [{"rule_type": key, "count": type_counter[key]} for key in sorted(type_counter.keys())],
                "scope_types": [{"scope_type": key, "count": scope_counter[key]} for key in sorted(scope_counter.keys())],
                "severities": [{"severity": key, "count": severity_counter[key]} for key in sorted(severity_counter.keys())],
            },
        }
    )


@router.get("/rules/{rule_id}")
async def get_policy_rule_detail(
    rule_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)

    rule_result = await db.execute(
        select(PolicyRule).where(PolicyRule.id == rule_id, PolicyRule.tenant_id == tenant_id)
    )
    rule = rule_result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    project_name = None
    if rule.project_id is not None:
        project_result = await db.execute(select(Project).where(Project.id == rule.project_id))
        project = project_result.scalar_one_or_none()
        project_name = project.name if project else None

    versions_result = await db.execute(
        select(PolicyRuleVersion)
        .where(PolicyRuleVersion.rule_id == rule.id)
        .order_by(PolicyRuleVersion.version_no.desc(), PolicyRuleVersion.id.desc())
    )
    versions = [_version_to_row(item) for item in versions_result.scalars().all()]

    return success_response(
        {
            "rule": _rule_to_row(rule, project_name=project_name),
            "versions": versions,
        }
    )

@router.post("/rules")
async def create_policy_rule(
    request: PolicyRuleCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_policy_write(context)
    tenant_id = _tenant_id_from_context(context)

    payload = _apply_template_payload(request)
    if not payload.get("rule_type") or not payload.get("name"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="rule_type and name are required")

    normalized_type = _normalize_enum(str(payload["rule_type"]), allowed=RULE_TYPES, field_name="rule_type")
    normalized_severity = _normalize_enum(str(payload.get("severity") or "MEDIUM"), allowed=SEVERITIES, field_name="severity")
    normalized_status = _normalize_enum(str(payload.get("status") or "DRAFT"), allowed=RULE_STATUSES, field_name="status")
    normalized_scope = _normalize_enum(str(payload.get("scope_type") or "PROJECT"), allowed=SCOPE_TYPES, field_name="scope_type")

    scoped_project_id = request.project_id
    if normalized_scope == "PROJECT":
        scoped_project_id = request.project_id or context.project.id
        await _validate_project_belongs_tenant(db, tenant_id=tenant_id, project_id=scoped_project_id)
    else:
        scoped_project_id = None

    actor = _actor(context)
    rule = await BaseRepository(PolicyRule, db).create(
        {
            "tenant_id": tenant_id,
            "project_id": scoped_project_id,
            "rule_type": normalized_type,
            "name": str(payload["name"]).strip(),
            "description": str(payload["description"]).strip() if payload.get("description") else None,
            "severity": normalized_severity,
            "status": normalized_status,
            "scope_type": normalized_scope,
            "scope_value": str(payload["scope_value"]).strip() if payload.get("scope_value") else None,
            "conditions_payload": payload.get("conditions_payload") or {},
            "actions_payload": payload.get("actions_payload") or {},
            "content_payload": payload.get("content_payload") or {},
            "prompt_text": str(payload["prompt_text"]).strip() if payload.get("prompt_text") else None,
            "version_no": 1,
            "created_by": actor,
            "updated_by": actor,
        }
    )
    await _append_version(
        db,
        rule=rule,
        version_no=1,
        change_note=request.change_note or "Initial version",
        actor=actor,
    )
    await _write_audit(
        db,
        context,
        "POLICY_RULE_CREATE",
        rule.id,
        {
            "summary": "Policy rule created",
            "name": rule.name,
            "rule_type": rule.rule_type,
            "status": rule.status,
            "scope_type": rule.scope_type,
        },
    )
    return success_response(
        _rule_to_row(rule),
        message="Policy rule created",
        code="POLICY_RULE_CREATED",
    )


@router.patch("/rules/{rule_id}")
async def update_policy_rule(
    rule_id: int,
    request: PolicyRuleUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_policy_write(context)
    tenant_id = _tenant_id_from_context(context)

    rule_result = await db.execute(
        select(PolicyRule).where(PolicyRule.id == rule_id, PolicyRule.tenant_id == tenant_id)
    )
    rule = rule_result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    patch = request.model_dump(exclude_none=True)
    if "rule_type" in patch:
        patch["rule_type"] = _normalize_enum(patch["rule_type"], allowed=RULE_TYPES, field_name="rule_type")
    if "severity" in patch:
        patch["severity"] = _normalize_enum(patch["severity"], allowed=SEVERITIES, field_name="severity")
    if "status" in patch:
        patch["status"] = _normalize_enum(patch["status"], allowed=RULE_STATUSES, field_name="status")

    target_scope = patch.get("scope_type", rule.scope_type)
    if "scope_type" in patch:
        target_scope = _normalize_enum(str(target_scope), allowed=SCOPE_TYPES, field_name="scope_type")
        patch["scope_type"] = target_scope

    if target_scope == "PROJECT":
        target_project_id = patch.get("project_id") or rule.project_id or context.project.id
        await _validate_project_belongs_tenant(db, tenant_id=tenant_id, project_id=target_project_id)
        patch["project_id"] = target_project_id
    else:
        patch["project_id"] = None

    actor = _actor(context)
    patch["version_no"] = (rule.version_no or 1) + 1
    patch["updated_by"] = actor
    if "name" in patch and patch["name"] is not None:
        patch["name"] = str(patch["name"]).strip()
    if "description" in patch and patch["description"] is not None:
        patch["description"] = str(patch["description"]).strip()
    if "scope_value" in patch and patch["scope_value"] is not None:
        patch["scope_value"] = str(patch["scope_value"]).strip()
    if "prompt_text" in patch and patch["prompt_text"] is not None:
        patch["prompt_text"] = str(patch["prompt_text"]).strip()

    updated = await BaseRepository(PolicyRule, db).update(rule, patch)
    await _append_version(
        db,
        rule=updated,
        version_no=updated.version_no,
        change_note=request.change_note or "Rule updated",
        actor=actor,
    )
    await _write_audit(
        db,
        context,
        "POLICY_RULE_UPDATE",
        updated.id,
        {
            "summary": "Policy rule updated",
            "version_no": updated.version_no,
        },
    )
    return success_response(
        _rule_to_row(updated),
        message="Policy rule updated",
        code="POLICY_RULE_UPDATED",
    )


@router.post("/rules/{rule_id}/actions")
async def operate_policy_rule(
    rule_id: int,
    request: PolicyRuleActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_policy_write(context)
    tenant_id = _tenant_id_from_context(context)

    rule_result = await db.execute(
        select(PolicyRule).where(PolicyRule.id == rule_id, PolicyRule.tenant_id == tenant_id)
    )
    rule = rule_result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    action = request.action.strip().upper()
    status_map = {
        "ACTIVATE": "ACTIVE",
        "DEACTIVATE": "INACTIVE",
        "ARCHIVE": "ARCHIVED",
        "DRAFT": "DRAFT",
    }
    if action not in status_map:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action: {request.action}")

    actor = _actor(context)
    updated = await BaseRepository(PolicyRule, db).update(
        rule,
        {
            "status": status_map[action],
            "version_no": (rule.version_no or 1) + 1,
            "updated_by": actor,
        },
    )
    await _append_version(
        db,
        rule=updated,
        version_no=updated.version_no,
        change_note=request.change_note or f"Rule action {action}",
        actor=actor,
    )
    await _write_audit(
        db,
        context,
        "POLICY_RULE_ACTION",
        updated.id,
        {
            "summary": "Policy rule action applied",
            "action": action,
            "status": updated.status,
            "version_no": updated.version_no,
        },
    )
    return success_response(
        _rule_to_row(updated),
        message="Policy rule action applied",
        code="POLICY_RULE_ACTION_APPLIED",
    )


@router.post("/rules/{rule_id}/versions/{version_id}/rollback")
async def rollback_policy_rule_version(
    rule_id: int,
    version_id: int,
    request: PolicyRuleRollbackRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    _require_policy_write(context)
    tenant_id = _tenant_id_from_context(context)

    rule_result = await db.execute(
        select(PolicyRule).where(PolicyRule.id == rule_id, PolicyRule.tenant_id == tenant_id)
    )
    rule = rule_result.scalar_one_or_none()
    if rule is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rule not found")

    version_result = await db.execute(
        select(PolicyRuleVersion).where(PolicyRuleVersion.id == version_id, PolicyRuleVersion.rule_id == rule_id)
    )
    version = version_result.scalar_one_or_none()
    if version is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    snapshot = version.snapshot_payload or {}
    target_scope = _normalize_enum(snapshot.get("scope_type", rule.scope_type), allowed=SCOPE_TYPES, field_name="scope_type")
    target_project_id = snapshot.get("project_id")
    if target_scope == "PROJECT":
        if target_project_id is None:
            target_project_id = context.project.id
        await _validate_project_belongs_tenant(db, tenant_id=tenant_id, project_id=int(target_project_id))
    else:
        target_project_id = None

    actor = _actor(context)
    patch = {
        "rule_type": _normalize_enum(snapshot.get("rule_type", rule.rule_type), allowed=RULE_TYPES, field_name="rule_type"),
        "name": str(snapshot.get("name", rule.name)).strip(),
        "description": str(snapshot.get("description")).strip() if snapshot.get("description") else None,
        "severity": _normalize_enum(snapshot.get("severity", rule.severity), allowed=SEVERITIES, field_name="severity"),
        "status": _normalize_enum(snapshot.get("status", rule.status), allowed=RULE_STATUSES, field_name="status"),
        "scope_type": target_scope,
        "scope_value": str(snapshot.get("scope_value")).strip() if snapshot.get("scope_value") else None,
        "project_id": int(target_project_id) if target_project_id is not None else None,
        "conditions_payload": snapshot.get("conditions_payload") or {},
        "actions_payload": snapshot.get("actions_payload") or {},
        "content_payload": snapshot.get("content_payload") or {},
        "prompt_text": str(snapshot.get("prompt_text")).strip() if snapshot.get("prompt_text") else None,
        "version_no": (rule.version_no or 1) + 1,
        "updated_by": actor,
    }
    updated = await BaseRepository(PolicyRule, db).update(rule, patch)
    await _append_version(
        db,
        rule=updated,
        version_no=updated.version_no,
        change_note=request.change_note or f"Rollback to version {version.version_no}",
        actor=actor,
    )
    await _write_audit(
        db,
        context,
        "POLICY_RULE_ROLLBACK",
        updated.id,
        {
            "summary": "Policy rule rolled back",
            "from_version": updated.version_no,
            "to_snapshot_version": version.version_no,
        },
    )
    return success_response(
        _rule_to_row(updated),
        message="Policy rule rolled back",
        code="POLICY_RULE_ROLLED_BACK",
    )


@router.post("/evaluate")
async def evaluate_policy_rules(
    request: PolicyEvaluateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    tenant_id = _tenant_id_from_context(context)

    module_key = request.module.strip().upper()
    action_key = request.action.strip().upper()
    domain_value = str(request.context_payload.get("domain", "")).strip() or None

    statuses = ["ACTIVE", "DRAFT"] if request.include_draft else ["ACTIVE"]
    result = await db.execute(
        select(PolicyRule)
        .where(
            PolicyRule.tenant_id == tenant_id,
            PolicyRule.status.in_(statuses),
        )
        .order_by(PolicyRule.severity.desc(), PolicyRule.updated_at.desc(), PolicyRule.id.desc())
        .limit(request.limit)
    )
    rows = list(result.scalars().all())

    matched_rules: list[dict[str, Any]] = []
    violations: list[dict[str, Any]] = []
    recommendations: list[str] = []

    for row in rows:
        if not await _rule_matches_scope(row, project_id=context.project.id, domain_value=domain_value):
            continue

        applicable, violation_messages = _evaluate_single_rule(
            row,
            module=module_key,
            action=action_key,
            context_payload=request.context_payload,
        )
        if not applicable:
            continue

        decision = "PASS"
        if violation_messages:
            decision = _rule_decision_default(row)
            recommendation = str((row.actions_payload or {}).get("recommendation") or (row.content_payload or {}).get("guidance") or "").strip()
            if recommendation:
                recommendations.append(recommendation)
            violations.append(
                {
                    "rule_id": row.id,
                    "rule_name": row.name,
                    "decision": decision,
                    "violations": violation_messages,
                }
            )

        matched_rules.append(
            {
                "rule_id": row.id,
                "name": row.name,
                "rule_type": row.rule_type,
                "severity": row.severity,
                "decision": decision,
                "version_no": row.version_no,
            }
        )

    final_decision = "PASS"
    if any(item["decision"] == "REJECT" for item in matched_rules):
        final_decision = "REJECT"
    elif any(item["decision"] == "WARN" for item in matched_rules):
        final_decision = "WARN"

    unique_recommendations = []
    for item in recommendations:
        if item and item not in unique_recommendations:
            unique_recommendations.append(item)

    return success_response(
        {
            "module": module_key,
            "action": action_key,
            "decision": final_decision,
            "matched_rule_count": len(matched_rules),
            "violation_count": len(violations),
            "matched_rules": matched_rules,
            "violations": violations,
            "recommendations": unique_recommendations,
        }
    )
