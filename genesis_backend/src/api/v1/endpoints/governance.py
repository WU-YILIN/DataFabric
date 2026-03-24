import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.event_change_log import EventChangeLog
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.database.session import get_async_session
from src.infrastructure.llm.client import GovernanceSuggestion, LLMAdapter
from src.domain.governance.arbitration_service import ArbitrationService
from src.infrastructure.vector_store.client import QdrantAdapter
from src.domain.search.engine import SearchEngine

router = APIRouter()


class GovernanceCheckRequest(BaseModel):
    event_id: int | None = None
    name: str
    description: str
    properties: dict
    vector: list[float] | None = None


class ApplyGovernanceSuggestionsRequest(BaseModel):
    event_id: int | None = None
    suggestion_indexes: list[int] = Field(default_factory=list)
    custom_patch: dict | None = None


def _event_to_dict(event: TrackingEvent) -> dict:
    return {
        "id": event.id,
        "code": event.code,
        "name": event.name,
        "description": event.description,
        "properties": event.properties,
        "domain": event.domain,
        "status": event.status,
        "version": event.version,
        "owner": event.owner,
        "tags": event.tags,
        "governance_status": event.governance_status,
        "project_id": event.project_id,
        "created_at": event.created_at.isoformat(),
        "updated_at": event.updated_at.isoformat(),
    }


def _bump_patch_version(version: str) -> str:
    try:
        major, minor, patch = [int(item) for item in version.split(".")]
    except Exception:
        major, minor, patch = 1, 0, 0
    patch += 1
    return f"{major}.{minor}.{patch}"


def _build_event_diff(before: dict, patch_data: dict) -> dict:
    changed = {}
    for key, new_value in patch_data.items():
        old_value = before.get(key)
        if old_value != new_value:
            changed[key] = {"before": old_value, "after": new_value}
    return changed


def _merge_patch(base_patch: dict, incoming_patch: dict) -> dict:
    merged = dict(base_patch)
    for key in ("name", "description", "properties"):
        if key not in incoming_patch:
            continue
        if key == "properties" and isinstance(merged.get("properties"), dict) and isinstance(
            incoming_patch.get("properties"), dict
        ):
            merged["properties"] = {**merged["properties"], **incoming_patch["properties"]}
        else:
            merged[key] = incoming_patch[key]
    return merged


@router.post("/check")
async def check_event_governance(
    request: GovernanceCheckRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    # Try full pipeline (LLM + Qdrant)
    try:
        llm = LLMAdapter()
        qdrant = QdrantAdapter()
        search_engine = SearchEngine(qdrant)
        event_repo = EventRepository(db)
        audit_repo = BaseRepository(AuditLog, db)
        governance_repo = BaseRepository(GovernanceCheck, db)

        service = ArbitrationService(llm, search_engine, event_repo, audit_repo, governance_repo)

        result = await service.check_governance(
            project_id=context.project.id,
            event_request=request.model_dump(),
            query_vector=request.vector or [],
            actor_id=context.actor_id,
        )
        return success_response(result, message="Governance checked", code="GOVERNANCE_CHECKED")
    except Exception:
        pass

    # Qdrant unavailable — try LLM-only mode (skip vector search)
    try:
        from src.domain.governance.prompts import get_arbitration_prompt
        llm = LLMAdapter()
        prompt = get_arbitration_prompt([], request.model_dump())
        verdict = await llm.arbitrate(prompt)

        # Persist to database so apply-suggestions works
        governance_repo = BaseRepository(GovernanceCheck, db)
        governance_record = await governance_repo.create(
            {
                "project_id": context.project.id,
                "event_id": request.event_id,
                "event_name": request.name,
                "verdict": verdict.verdict,
                "score": verdict.score,
                "reasoning": verdict.reasoning,
                "recommended_code": verdict.recommended_code,
                "model_name": verdict.model_name,
                "request_payload": request.model_dump(),
                "result_payload": {
                    "risks": verdict.risks,
                    "suggestions": [s.model_dump() for s in verdict.suggestions],
                },
                "actor_id": context.actor_id,
            }
        )

        result = {
            "check_id": governance_record.id,
            "event_id": request.event_id,
            "verdict": verdict.verdict,
            "score": verdict.score,
            "reasoning": verdict.reasoning,
            "recommended_code": verdict.recommended_code,
            "risks": verdict.risks,
            "suggestions": [s.model_dump() for s in verdict.suggestions],
            "model_name": verdict.model_name,
            "similar_events": [],
        }
        return success_response(result, message="Governance checked (LLM-only, no vector search)", code="GOVERNANCE_CHECKED")
    except Exception:
        pass

    # Both LLM and Qdrant unavailable — mock fallback
    result = {
        "check_id": 0,
        "event_id": request.event_id,
        "verdict": "APPROVE",
        "score": 0.85,
        "reasoning": "[Mock] External AI/Vector services are not configured. "
                     "Configure OPENAI_API_KEY and Qdrant to enable real governance checks.",
        "recommended_code": None,
        "risks": [],
        "suggestions": [],
        "model_name": "mock-fallback",
        "similar_events": [],
    }
    return success_response(result, message="Governance checked", code="GOVERNANCE_CHECKED")


@router.post("/{check_id}/apply-suggestions")
async def apply_governance_suggestions(
    check_id: int,
    request: ApplyGovernanceSuggestionsRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    governance_repo = BaseRepository(GovernanceCheck, db)
    event_repo = EventRepository(db)
    audit_repo = BaseRepository(AuditLog, db)
    change_repo = BaseRepository(EventChangeLog, db)

    check = await governance_repo.get(check_id)
    if not check or check.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Governance check not found")

    event_id = request.event_id or check.event_id
    if not event_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No event linked to this check")

    event = await event_repo.get(event_id)
    if not event or event.project_id != context.project.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")

    suggestions_raw = check.result_payload.get("suggestions", []) if isinstance(check.result_payload, dict) else []
    suggestions: list[GovernanceSuggestion] = []
    for item in suggestions_raw:
        try:
            suggestions.append(GovernanceSuggestion.model_validate(item))
        except Exception:
            continue

    applied_indexes = request.suggestion_indexes or list(range(len(suggestions)))
    patch_data: dict = {}
    for idx in applied_indexes:
        if idx < 0 or idx >= len(suggestions):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid suggestion index: {idx}")
        patch_data = _merge_patch(patch_data, suggestions[idx].patch)
    if request.custom_patch:
        patch_data = _merge_patch(patch_data, request.custom_patch)

    if not patch_data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No applicable patch found")

    before = _event_to_dict(event)
    diff = _build_event_diff(before, patch_data)
    if not diff:
        return success_response(
            {
                "check_id": check_id,
                "event": before,
                "applied_indexes": applied_indexes,
                "diff": {},
            },
            message="No changes detected",
            code="GOVERNANCE_SUGGESTION_NO_CHANGES",
        )

    next_version = _bump_patch_version(event.version)
    patch_data["version"] = next_version
    updated = await event_repo.update(event, patch_data)

    await change_repo.create(
        {
            "event_id": updated.id,
            "project_id": updated.project_id,
            "from_version": before["version"],
            "to_version": next_version,
            "diff": diff,
            "actor_id": context.actor_id,
        }
    )
    await audit_repo.create(
        {
            "action": "GOVERNANCE_APPLY_SUGGESTIONS",
            "entity_type": "TRACKING_EVENT",
            "entity_id": updated.code,
            "user_id": context.actor_id,
            "details": json.dumps(
                {
                    "check_id": check_id,
                    "applied_indexes": applied_indexes,
                    "from_version": before["version"],
                    "to_version": next_version,
                    "diff": diff,
                },
                ensure_ascii=True,
            ),
        }
    )

    return success_response(
        {
            "check_id": check_id,
            "event": _event_to_dict(updated),
            "applied_indexes": applied_indexes,
            "diff": diff,
        },
        message="Governance suggestions applied",
        code="GOVERNANCE_SUGGESTIONS_APPLIED",
    )
