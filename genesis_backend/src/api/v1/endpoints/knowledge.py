import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import parse_actor
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.knowledge_document import KnowledgeDocument
from src.infrastructure.database.models.knowledge_document_comment import KnowledgeDocumentComment
from src.infrastructure.database.models.knowledge_document_version import KnowledgeDocumentVersion
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.session import get_async_session

router = APIRouter()

DOC_STATUSES = {"DRAFT", "PUBLISHED", "ARCHIVED"}
DOC_ACTIONS = {"PUBLISH", "ARCHIVE", "UNARCHIVE"}
DOC_FORMATS = {"MARKDOWN", "RICH_TEXT"}

SOURCE_ROUTE_MAP = {
    "TRACKING_EVENT": "/events",
    "EVENT": "/events",
    "DATA_ASSET": "/catalog",
    "DATA_QUALITY_RULE": "/data-quality",
    "PIPELINE": "/pipelines",
    "SCHEDULER_DAG": "/scheduler",
    "SCHEDULER_RUN": "/scheduler",
    "ALERT": "/monitoring",
    "COLLAB_WORKFLOW": "/collaboration",
    "PROJECT_SETTING": "/settings",
    "TENANT_SETTING": "/settings",
}

SOURCE_MODULE_MAP = {
    "TRACKING_EVENT": "EVENTS",
    "EVENT": "EVENTS",
    "DATA_ASSET": "CATALOG",
    "DATA_QUALITY_RULE": "DATA_QUALITY",
    "PIPELINE": "PIPELINES",
    "SCHEDULER_DAG": "SCHEDULER",
    "SCHEDULER_RUN": "SCHEDULER",
    "ALERT": "MONITORING",
    "COLLAB_WORKFLOW": "COLLABORATION",
    "PROJECT_SETTING": "SETTINGS",
    "TENANT_SETTING": "SETTINGS",
}


def _knowledge_templates() -> dict[str, dict[str, str]]:
    return {
        "EVENT_SPEC": {
            "doc_type": "EVENT_SPEC",
            "module": "EVENTS",
            "title": "Event Spec Template",
            "summary": "Template for describing event definition and governance context.",
            "content": (
                "# Event Overview\n\n"
                "## Purpose\n- Why this event exists\n\n"
                "## Schema\n- Fields and constraints\n\n"
                "## Governance\n- Risks\n- Approval notes\n\n"
                "## Consumers\n- Downstream pipelines and dashboards\n"
            ),
        },
        "DQ_RULE_GUIDE": {
            "doc_type": "DQ_RULE_GUIDE",
            "module": "DATA_QUALITY",
            "title": "DQ Rule Guide Template",
            "summary": "Template for documenting rule intent and operational thresholds.",
            "content": (
                "# Rule Summary\n\n"
                "## Rule Intent\n- What this rule protects\n\n"
                "## Configuration\n- Target field/operator/threshold\n\n"
                "## Alert Policy\n- Severity and channels\n\n"
                "## Playbook\n- Triage and remediation steps\n"
            ),
        },
        "INCIDENT_RUNBOOK": {
            "doc_type": "RUNBOOK",
            "module": "MONITORING",
            "title": "Incident Runbook Template",
            "summary": "Template for incident handling and escalation workflows.",
            "content": (
                "# Incident Runbook\n\n"
                "## Trigger Signals\n- Alert IDs / thresholds\n\n"
                "## Immediate Actions\n1. Claim alert\n2. Validate blast radius\n3. Notify stakeholders\n\n"
                "## Diagnostics\n- Queries and dashboards\n\n"
                "## Recovery and Verification\n- Steps and checks\n\n"
                "## Postmortem Inputs\n- Timeline\n- Root cause\n- Follow-up tasks\n"
            ),
        },
    }


class RelatedObjectInput(BaseModel):
    source_type: str = Field(..., min_length=2, max_length=64)
    source_id: str = Field(..., min_length=1, max_length=128)
    label: str | None = Field(default=None, max_length=255)
    module: str | None = Field(default=None, max_length=64)


class KnowledgeCreateRequest(BaseModel):
    doc_type: str = Field(..., min_length=2, max_length=64)
    module: str = Field(..., min_length=2, max_length=64)
    title: str = Field(..., min_length=2, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    content: str | None = Field(default=None, max_length=100000)
    format: str = Field(default="MARKDOWN", max_length=32)
    status: str = Field(default="DRAFT", max_length=32)
    tags: list[str] = Field(default_factory=list)
    related_objects: list[RelatedObjectInput] = Field(default_factory=list)
    meta_payload: dict[str, Any] = Field(default_factory=dict)
    template_key: str | None = Field(default=None, max_length=64)
    change_note: str | None = Field(default=None, max_length=1000)


class KnowledgeUpdateRequest(BaseModel):
    doc_type: str | None = Field(default=None, min_length=2, max_length=64)
    module: str | None = Field(default=None, min_length=2, max_length=64)
    title: str | None = Field(default=None, min_length=2, max_length=255)
    summary: str | None = Field(default=None, max_length=2000)
    content: str | None = Field(default=None, max_length=100000)
    format: str | None = Field(default=None, max_length=32)
    tags: list[str] | None = None
    related_objects: list[RelatedObjectInput] | None = None
    meta_payload: dict[str, Any] | None = None
    change_note: str | None = Field(default=None, max_length=1000)


class KnowledgeCommentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class KnowledgeActionRequest(BaseModel):
    action: str = Field(..., min_length=3, max_length=32)
    change_note: str | None = Field(default=None, max_length=1000)


class KnowledgeRestoreVersionRequest(BaseModel):
    change_note: str | None = Field(default=None, max_length=1000)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.isoformat()


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return _to_iso(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, set):
        return [_json_safe(item) for item in value]
    return value


def _require_user_context(context: RequestContext) -> None:
    if context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Knowledge API requires bearer user context",
        )


def _normalize_status(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in DOC_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported status: {value}")
    return normalized


def _normalize_format(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in DOC_FORMATS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported format: {value}")
    return normalized


def _normalize_text_token(value: str, field_name: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"{field_name} cannot be empty")
    return normalized


def _normalize_tags(tags: list[str]) -> list[str]:
    unique: list[str] = []
    for raw in tags:
        tag = raw.strip()
        if not tag:
            continue
        if tag not in unique:
            unique.append(tag)
    return unique


def _mentions_from_text(content: str) -> list[str]:
    matches = re.findall(r"@([A-Za-z0-9_.+\-]+)", content)
    unique_values: list[str] = []
    for item in matches:
        if item not in unique_values:
            unique_values.append(item)
    return unique_values


def _normalize_related_objects(raw: list[RelatedObjectInput]) -> list[dict[str, Any]]:
    unique: dict[tuple[str, str], dict[str, Any]] = {}
    for item in raw:
        source_type = _normalize_text_token(item.source_type, "source_type")
        source_id = item.source_id.strip()
        if not source_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_id cannot be empty")
        key = (source_type, source_id)
        module = _normalize_text_token(item.module, "module") if item.module else SOURCE_MODULE_MAP.get(source_type)
        route = SOURCE_ROUTE_MAP.get(source_type, "/logs")
        unique[key] = {
            "source_type": source_type,
            "source_id": source_id,
            "label": item.label.strip() if item.label else None,
            "module": module,
            "module_route": route,
        }
    return list(unique.values())


def _related_object_exists_model(source_type: str):
    normalized = source_type.upper()
    if normalized in {"TRACKING_EVENT", "EVENT"}:
        return TrackingEvent
    if normalized == "DATA_ASSET":
        return DataAsset
    if normalized == "DATA_QUALITY_RULE":
        return DataQualityRule
    if normalized == "PIPELINE":
        return Pipeline
    if normalized == "ALERT":
        return Alert
    if normalized == "SCHEDULER_DAG":
        return SchedulerDag
    return None


async def _enrich_related_objects(
    db: AsyncSession,
    project_id: int,
    related_objects: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in related_objects:
        source_type = str(item.get("source_type", "")).upper()
        source_id = str(item.get("source_id", ""))
        model = _related_object_exists_model(source_type)
        exists = None
        if model is not None and source_id.isdigit():
            result = await db.execute(
                select(model).where(model.id == int(source_id), model.project_id == project_id)
            )
            exists = result.scalar_one_or_none() is not None
        enriched.append(
            {
                **item,
                "module_route": item.get("module_route") or SOURCE_ROUTE_MAP.get(source_type, "/logs"),
                "exists": exists,
            }
        )
    return enriched


def _document_to_row(document: KnowledgeDocument, related_objects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    preview = document.content.strip()
    if len(preview) > 280:
        preview = f"{preview[:280]}..."
    return {
        "id": document.id,
        "project_id": document.project_id,
        "tenant_id": document.tenant_id,
        "doc_type": document.doc_type,
        "module": document.module,
        "title": document.title,
        "summary": document.summary,
        "content": document.content,
        "preview": preview,
        "format": document.format,
        "status": document.status,
        "tags": document.tags or [],
        "related_objects": related_objects if related_objects is not None else (document.related_objects or []),
        "author": parse_actor(document.author_id),
        "author_id": document.author_id,
        "author_user_id": document.author_user_id,
        "last_editor": parse_actor(document.last_editor_id),
        "last_editor_id": document.last_editor_id,
        "last_editor_user_id": document.last_editor_user_id,
        "version_no": document.version_no,
        "comment_count": document.comment_count,
        "published_at": _to_iso(document.published_at),
        "archived_at": _to_iso(document.archived_at),
        "meta_payload": document.meta_payload or {},
        "created_at": _to_iso(document.created_at),
        "updated_at": _to_iso(document.updated_at),
    }


def _version_to_row(version: KnowledgeDocumentVersion) -> dict[str, Any]:
    return {
        "id": version.id,
        "document_id": version.document_id,
        "project_id": version.project_id,
        "version_no": version.version_no,
        "action": version.action,
        "title": version.title,
        "summary": version.summary,
        "content": version.content,
        "tags": version.tags or [],
        "related_objects": version.related_objects or [],
        "editor": parse_actor(version.editor_id),
        "editor_id": version.editor_id,
        "editor_user_id": version.editor_user_id,
        "change_note": version.change_note,
        "snapshot": version.snapshot or {},
        "created_at": _to_iso(version.created_at),
    }


def _comment_to_row(comment: KnowledgeDocumentComment) -> dict[str, Any]:
    return {
        "id": comment.id,
        "document_id": comment.document_id,
        "author": parse_actor(comment.author_id),
        "author_id": comment.author_id,
        "author_user_id": comment.author_user_id,
        "content": comment.content,
        "mentions": comment.mentions or [],
        "created_at": _to_iso(comment.created_at),
    }


async def _write_audit(
    db: AsyncSession,
    context: RequestContext,
    action: str,
    document: KnowledgeDocument,
    details: dict[str, Any],
) -> None:
    serialized_details = _json_safe(details)
    await BaseRepository(AuditLog, db).create(
        {
            "action": action,
            "entity_type": "KNOWLEDGE_DOC",
            "entity_id": str(document.id),
            "user_id": context.actor_id,
            "details": json.dumps(serialized_details, ensure_ascii=True),
        }
    )


async def _create_version_snapshot(
    db: AsyncSession,
    document: KnowledgeDocument,
    *,
    action: str,
    editor_id: str,
    editor_user_id: int | None,
    change_note: str | None,
    snapshot: dict[str, Any] | None = None,
) -> KnowledgeDocumentVersion:
    version_repo = BaseRepository(KnowledgeDocumentVersion, db)
    return await version_repo.create(
        {
            "document_id": document.id,
            "project_id": document.project_id,
            "version_no": document.version_no,
            "action": action,
            "title": document.title,
            "summary": document.summary,
            "content": document.content,
            "tags": document.tags or [],
            "related_objects": document.related_objects or [],
            "editor_id": editor_id,
            "editor_user_id": editor_user_id,
            "change_note": change_note,
            "snapshot": _json_safe(snapshot or {}),
        }
    )


async def _load_document_detail(
    db: AsyncSession,
    document: KnowledgeDocument,
) -> dict[str, Any]:
    related_objects = await _enrich_related_objects(db, document.project_id, document.related_objects or [])
    version_result = await db.execute(
        select(KnowledgeDocumentVersion)
        .where(KnowledgeDocumentVersion.document_id == document.id)
        .order_by(KnowledgeDocumentVersion.version_no.desc(), KnowledgeDocumentVersion.id.desc())
    )
    comment_result = await db.execute(
        select(KnowledgeDocumentComment)
        .where(KnowledgeDocumentComment.document_id == document.id)
        .order_by(KnowledgeDocumentComment.created_at.asc())
    )
    related_doc_result = await db.execute(
        select(KnowledgeDocument)
        .where(
            KnowledgeDocument.project_id == document.project_id,
            KnowledgeDocument.id != document.id,
            KnowledgeDocument.status != "ARCHIVED",
        )
        .order_by(KnowledgeDocument.updated_at.desc())
    )

    versions = list(version_result.scalars().all())
    comments = list(comment_result.scalars().all())
    related_docs = list(related_doc_result.scalars().all())

    shared_docs: list[dict[str, Any]] = []
    source_keys = {
        (str(item.get("source_type", "")).upper(), str(item.get("source_id", "")))
        for item in (document.related_objects or [])
    }
    tag_set = set(document.tags or [])
    for candidate in related_docs:
        candidate_source_keys = {
            (str(item.get("source_type", "")).upper(), str(item.get("source_id", "")))
            for item in (candidate.related_objects or [])
        }
        candidate_tags = set(candidate.tags or [])
        if source_keys.intersection(candidate_source_keys) or tag_set.intersection(candidate_tags):
            shared_docs.append(_document_to_row(candidate))
        if len(shared_docs) >= 10:
            break

    return {
        "document": _document_to_row(document, related_objects=related_objects),
        "version_history": [_version_to_row(item) for item in versions],
        "comments": [_comment_to_row(item) for item in comments],
        "related_documents": shared_docs,
    }


def _resolve_template_payload(template_key: str | None) -> dict[str, str] | None:
    if not template_key:
        return None
    template = _knowledge_templates().get(template_key.strip().upper())
    if template is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown template_key: {template_key}")
    return template


@router.get("/overview")
async def get_knowledge_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    docs_result = await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.project_id == context.project.id))
    docs = list(docs_result.scalars().all())

    comments_result = await db.execute(
        select(KnowledgeDocumentComment).where(KnowledgeDocumentComment.project_id == context.project.id)
    )
    comments = list(comments_result.scalars().all())

    now = datetime.now(timezone.utc)
    updated_cutoff = now - timedelta(days=7)
    comments_cutoff = now - timedelta(days=7)

    module_counts: dict[str, int] = {}
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    for item in docs:
        module_counts[item.module] = module_counts.get(item.module, 0) + 1
        type_counts[item.doc_type] = type_counts.get(item.doc_type, 0) + 1
        status_counts[item.status] = status_counts.get(item.status, 0) + 1
        for tag in (item.tags or []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    updated_recent = [
        item
        for item in docs
        if (
            item.updated_at
            and (item.updated_at if item.updated_at.tzinfo else item.updated_at.replace(tzinfo=timezone.utc)) >= updated_cutoff
        )
    ]
    comments_recent = [
        item
        for item in comments
        if (
            item.created_at
            and (item.created_at if item.created_at.tzinfo else item.created_at.replace(tzinfo=timezone.utc)) >= comments_cutoff
        )
    ]

    recent_docs = sorted(docs, key=lambda item: item.updated_at or item.created_at, reverse=True)[:20]
    my_docs = [
        item
        for item in docs
        if item.author_id == context.actor_id or (context.user and item.author_user_id == context.user.id)
    ]

    templates = [
        {
            "key": key,
            "doc_type": value["doc_type"],
            "module": value["module"],
            "title": value["title"],
            "summary": value["summary"],
        }
        for key, value in _knowledge_templates().items()
    ]

    data = {
        "summary": {
            "total_docs": len(docs),
            "published_docs": status_counts.get("PUBLISHED", 0),
            "draft_docs": status_counts.get("DRAFT", 0),
            "archived_docs": status_counts.get("ARCHIVED", 0),
            "updated_docs_7d": len(updated_recent),
            "comments_7d": len(comments_recent),
        },
        "directory": {
            "modules": module_counts,
            "doc_types": type_counts,
            "statuses": status_counts,
            "top_tags": sorted(tag_counts.items(), key=lambda item: item[1], reverse=True)[:20],
        },
        "recent_documents": [_document_to_row(item) for item in recent_docs],
        "my_documents": [_document_to_row(item) for item in sorted(my_docs, key=lambda item: item.updated_at, reverse=True)[:20]],
        "templates": templates,
    }
    return success_response(data)


@router.get("/templates")
async def get_knowledge_templates(
    context: RequestContext = Depends(get_request_context),
):
    _require_user_context(context)
    rows = []
    for key, value in _knowledge_templates().items():
        rows.append(
            {
                "key": key,
                "doc_type": value["doc_type"],
                "module": value["module"],
                "title": value["title"],
                "summary": value["summary"],
                "content": value["content"],
            }
        )
    return success_response(rows)


@router.get("/documents")
async def list_knowledge_documents(
    q: str | None = Query(default=None),
    module: str | None = Query(default=None),
    doc_type: str | None = Query(default=None),
    status_filter: str | None = Query(default=None, alias="status"),
    tag: str | None = Query(default=None),
    updated_by_me: bool = Query(default=False),
    related_source_type: str | None = Query(default=None),
    related_source_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    offset: int = Query(default=0, ge=0),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    query = select(KnowledgeDocument).where(KnowledgeDocument.project_id == context.project.id)
    filters = []
    if module:
        filters.append(KnowledgeDocument.module == _normalize_text_token(module, "module"))
    if doc_type:
        filters.append(KnowledgeDocument.doc_type == _normalize_text_token(doc_type, "doc_type"))
    if status_filter:
        filters.append(KnowledgeDocument.status == _normalize_status(status_filter))
    if q:
        keyword = f"%{q.strip()}%"
        filters.append(
            or_(
                KnowledgeDocument.title.ilike(keyword),
                KnowledgeDocument.summary.ilike(keyword),
                KnowledgeDocument.content.ilike(keyword),
            )
        )
    if filters:
        query = query.where(and_(*filters))

    result = await db.execute(query.order_by(KnowledgeDocument.updated_at.desc()))
    docs = list(result.scalars().all())

    if updated_by_me:
        docs = [
            item
            for item in docs
            if item.last_editor_id == context.actor_id or (context.user and item.last_editor_user_id == context.user.id)
        ]
    if tag:
        normalized_tag = tag.strip()
        docs = [item for item in docs if normalized_tag in (item.tags or [])]
    if related_source_type and related_source_id:
        source_type = _normalize_text_token(related_source_type, "related_source_type")
        source_id = related_source_id.strip()
        docs = [
            item
            for item in docs
            if any(
                str(rel.get("source_type", "")).upper() == source_type and str(rel.get("source_id", "")) == source_id
                for rel in (item.related_objects or [])
            )
        ]

    total = len(docs)
    paginated_docs = docs[offset : offset + limit]

    modules = sorted({item.module for item in docs})
    doc_types = sorted({item.doc_type for item in docs})
    statuses = sorted({item.status for item in docs})
    tags = sorted({tag_item for item in docs for tag_item in (item.tags or [])})

    data = {
        "items": [_document_to_row(item) for item in paginated_docs],
        "total": total,
        "limit": limit,
        "offset": offset,
        "facets": {
            "modules": modules,
            "doc_types": doc_types,
            "statuses": statuses,
            "tags": tags,
        },
    }
    return success_response(data)


@router.get("/documents/related")
async def list_related_documents(
    source_type: str = Query(...),
    source_id: str = Query(...),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    normalized_type = _normalize_text_token(source_type, "source_type")
    normalized_id = source_id.strip()
    if not normalized_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_id cannot be empty")

    result = await db.execute(
        select(KnowledgeDocument)
        .where(KnowledgeDocument.project_id == context.project.id)
        .order_by(KnowledgeDocument.updated_at.desc())
    )
    docs = list(result.scalars().all())
    if not include_archived:
        docs = [item for item in docs if item.status != "ARCHIVED"]
    related = [
        item
        for item in docs
        if any(
            str(rel.get("source_type", "")).upper() == normalized_type
            and str(rel.get("source_id", "")) == normalized_id
            for rel in (item.related_objects or [])
        )
    ][:limit]
    return success_response(
        {
            "source_type": normalized_type,
            "source_id": normalized_id,
            "items": [_document_to_row(item) for item in related],
            "total": len(related),
        }
    )


@router.post("/documents")
async def create_knowledge_document(
    request: KnowledgeCreateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)

    template_payload = _resolve_template_payload(request.template_key)
    doc_type = _normalize_text_token(request.doc_type, "doc_type")
    module = _normalize_text_token(request.module, "module")
    title = request.title.strip()
    summary = request.summary.strip() if request.summary else None
    content = request.content.strip() if request.content else ""
    if template_payload is not None:
        if not content:
            content = template_payload["content"]
        if not title:
            title = template_payload["title"]
        if not summary:
            summary = template_payload["summary"]
        if doc_type == "TEMPLATE":
            doc_type = template_payload["doc_type"]
        if module == "TEMPLATE":
            module = template_payload["module"]
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content is required")

    status_value = _normalize_status(request.status)
    format_value = _normalize_format(request.format)
    tags = _normalize_tags(request.tags)
    related_objects = _normalize_related_objects(request.related_objects)
    now = datetime.now(timezone.utc)

    document_repo = BaseRepository(KnowledgeDocument, db)
    document = await document_repo.create(
        {
            "project_id": context.project.id,
            "tenant_id": context.project.tenant_id,
            "doc_type": doc_type,
            "module": module,
            "title": title,
            "summary": summary,
            "content": content,
            "format": format_value,
            "status": status_value,
            "tags": tags,
            "related_objects": related_objects,
            "author_id": context.actor_id,
            "author_user_id": context.user.id if context.user else None,
            "last_editor_id": context.actor_id,
            "last_editor_user_id": context.user.id if context.user else None,
            "version_no": 1,
            "comment_count": 0,
            "published_at": now if status_value == "PUBLISHED" else None,
            "archived_at": now if status_value == "ARCHIVED" else None,
            "meta_payload": request.meta_payload or {},
        }
    )

    await _create_version_snapshot(
        db,
        document,
        action="PUBLISH" if status_value == "PUBLISHED" else "CREATE",
        editor_id=context.actor_id,
        editor_user_id=context.user.id if context.user else None,
        change_note=request.change_note,
        snapshot={"status": status_value, "template_key": request.template_key},
    )
    await _write_audit(
        db,
        context,
        "KNOWLEDGE_DOC_CREATE",
        document,
        {
            "doc_type": document.doc_type,
            "module": document.module,
            "status": document.status,
            "version_no": document.version_no,
        },
    )

    detail = await _load_document_detail(db, document)
    return success_response(detail, message="Document created", code="KNOWLEDGE_DOC_CREATED")


@router.get("/documents/{document_id}")
async def get_knowledge_document_detail(
    document_id: int,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == context.project.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    detail = await _load_document_detail(db, document)
    return success_response(detail)


@router.patch("/documents/{document_id}")
async def update_knowledge_document(
    document_id: int,
    request: KnowledgeUpdateRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == context.project.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    patch: dict[str, Any] = {}
    if request.doc_type is not None:
        patch["doc_type"] = _normalize_text_token(request.doc_type, "doc_type")
    if request.module is not None:
        patch["module"] = _normalize_text_token(request.module, "module")
    if request.title is not None:
        title = request.title.strip()
        if not title:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="title cannot be empty")
        patch["title"] = title
    if request.summary is not None:
        patch["summary"] = request.summary.strip() or None
    if request.content is not None:
        content = request.content.strip()
        if not content:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="content cannot be empty")
        patch["content"] = content
    if request.format is not None:
        patch["format"] = _normalize_format(request.format)
    if request.tags is not None:
        patch["tags"] = _normalize_tags(request.tags)
    if request.related_objects is not None:
        patch["related_objects"] = _normalize_related_objects(request.related_objects)
    if request.meta_payload is not None:
        patch["meta_payload"] = request.meta_payload

    if not patch:
        detail = await _load_document_detail(db, document)
        return success_response(detail, message="No changes", code="KNOWLEDGE_DOC_UNCHANGED")

    patch["last_editor_id"] = context.actor_id
    patch["last_editor_user_id"] = context.user.id if context.user else None
    patch["version_no"] = document.version_no + 1

    previous_state = {
        "title": document.title,
        "summary": document.summary,
        "status": document.status,
        "version_no": document.version_no,
    }
    document = await BaseRepository(KnowledgeDocument, db).update(document, patch)

    await _create_version_snapshot(
        db,
        document,
        action="UPDATE",
        editor_id=context.actor_id,
        editor_user_id=context.user.id if context.user else None,
        change_note=request.change_note,
        snapshot={"before": previous_state},
    )
    await _write_audit(
        db,
        context,
        "KNOWLEDGE_DOC_UPDATE",
        document,
        {
            "changed_fields": sorted(list(patch.keys())),
            "version_no": document.version_no,
        },
    )

    detail = await _load_document_detail(db, document)
    return success_response(detail, message="Document updated", code="KNOWLEDGE_DOC_UPDATED")


@router.post("/documents/{document_id}/comments")
async def add_knowledge_document_comment(
    document_id: int,
    request: KnowledgeCommentRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == context.project.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    mentions = _mentions_from_text(request.content)
    comment = await BaseRepository(KnowledgeDocumentComment, db).create(
        {
            "document_id": document.id,
            "project_id": context.project.id,
            "author_id": context.actor_id,
            "author_user_id": context.user.id if context.user else None,
            "content": request.content.strip(),
            "mentions": mentions,
        }
    )
    await BaseRepository(KnowledgeDocument, db).update(
        document,
        {
            "comment_count": (document.comment_count or 0) + 1,
            "last_editor_id": context.actor_id,
            "last_editor_user_id": context.user.id if context.user else None,
        },
    )
    await _write_audit(
        db,
        context,
        "KNOWLEDGE_DOC_COMMENT",
        document,
        {
            "comment_id": comment.id,
            "mentions": mentions,
        },
    )
    return success_response(_comment_to_row(comment), message="Comment added", code="KNOWLEDGE_DOC_COMMENTED")


@router.post("/documents/{document_id}/actions")
async def operate_knowledge_document(
    document_id: int,
    request: KnowledgeActionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    action = request.action.strip().upper()
    if action not in DOC_ACTIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported action: {request.action}")

    result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == context.project.id,
        )
    )
    document = result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    now = datetime.now(timezone.utc)
    patch: dict[str, Any] = {
        "last_editor_id": context.actor_id,
        "last_editor_user_id": context.user.id if context.user else None,
        "version_no": document.version_no + 1,
    }
    if action == "PUBLISH":
        patch.update({"status": "PUBLISHED", "published_at": now, "archived_at": None})
    elif action == "ARCHIVE":
        patch.update({"status": "ARCHIVED", "archived_at": now})
    elif action == "UNARCHIVE":
        patch.update({"status": "DRAFT", "archived_at": None})

    previous_status = document.status
    document = await BaseRepository(KnowledgeDocument, db).update(document, patch)
    await _create_version_snapshot(
        db,
        document,
        action=action,
        editor_id=context.actor_id,
        editor_user_id=context.user.id if context.user else None,
        change_note=request.change_note,
        snapshot={"from_status": previous_status, "to_status": document.status},
    )
    await _write_audit(
        db,
        context,
        f"KNOWLEDGE_DOC_{action}",
        document,
        {
            "from_status": previous_status,
            "to_status": document.status,
            "version_no": document.version_no,
        },
    )

    detail = await _load_document_detail(db, document)
    return success_response(detail, message="Document action applied", code="KNOWLEDGE_DOC_ACTION_OK")


@router.post("/documents/{document_id}/versions/{version_id}/restore")
async def restore_knowledge_document_version(
    document_id: int,
    version_id: int,
    request: KnowledgeRestoreVersionRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    _require_user_context(context)
    doc_result = await db.execute(
        select(KnowledgeDocument).where(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == context.project.id,
        )
    )
    document = doc_result.scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")

    version_result = await db.execute(
        select(KnowledgeDocumentVersion).where(
            KnowledgeDocumentVersion.id == version_id,
            KnowledgeDocumentVersion.document_id == document.id,
            KnowledgeDocumentVersion.project_id == context.project.id,
        )
    )
    target_version = version_result.scalar_one_or_none()
    if not target_version:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Version not found")

    version_snapshot = target_version.snapshot if isinstance(target_version.snapshot, dict) else {}
    restore_status = str(version_snapshot.get("to_status", document.status)).upper()
    if restore_status not in DOC_STATUSES:
        restore_status = document.status

    patch = {
        "title": target_version.title,
        "summary": target_version.summary,
        "content": target_version.content,
        "tags": target_version.tags or [],
        "related_objects": target_version.related_objects or [],
        "status": restore_status,
        "version_no": document.version_no + 1,
        "last_editor_id": context.actor_id,
        "last_editor_user_id": context.user.id if context.user else None,
        "archived_at": datetime.now(timezone.utc) if restore_status == "ARCHIVED" else None,
    }
    document = await BaseRepository(KnowledgeDocument, db).update(document, patch)
    await _create_version_snapshot(
        db,
        document,
        action="RESTORE",
        editor_id=context.actor_id,
        editor_user_id=context.user.id if context.user else None,
        change_note=request.change_note or f"restore from version {target_version.version_no}",
        snapshot={"restored_from_version": target_version.version_no, "version_id": target_version.id},
    )
    await _write_audit(
        db,
        context,
        "KNOWLEDGE_DOC_RESTORE",
        document,
        {
            "restored_from_version": target_version.version_no,
            "restored_from_version_id": target_version.id,
            "status": restore_status,
            "version_no": document.version_no,
        },
    )

    detail = await _load_document_detail(db, document)
    detail["restored_from"] = _version_to_row(target_version)
    return success_response(detail, message="Document restored", code="KNOWLEDGE_DOC_RESTORED")
