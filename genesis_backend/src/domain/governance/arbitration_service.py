from typing import List
import json

from src.domain.governance.prompts import get_arbitration_prompt
from src.domain.search.engine import SearchEngine
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.repositories.base import BaseRepository
from src.infrastructure.database.repositories.event_repo import EventRepository
from src.infrastructure.llm.client import LLMAdapter


class ArbitrationService:
    def __init__(
        self,
        llm_adapter: LLMAdapter,
        search_engine: SearchEngine,
        event_repo: EventRepository,
        audit_repo: BaseRepository[AuditLog],
        governance_repo: BaseRepository[GovernanceCheck],
    ):
        self.llm_adapter = llm_adapter
        self.search_engine = search_engine
        self.event_repo = event_repo
        self.audit_repo = audit_repo
        self.governance_repo = governance_repo

    async def check_governance(
        self,
        project_id: int,
        event_request: dict,
        query_vector: List[float],
        actor_id: str,
    ):
        similar_events = await self.search_engine.hybrid_search(
            query_text=event_request["description"],
            query_vector=query_vector,
            limit=5,
        )
        existing_context = [e["payload"] for e in similar_events]
        verdict = await self.llm_adapter.arbitrate(
            get_arbitration_prompt(existing_context, event_request)
        )

        verdict_action = {
            "APPROVE": "GOVERNANCE_APPROVE",
            "REJECT": "GOVERNANCE_REJECT",
            "NEEDS_REVISION": "GOVERNANCE_NEEDS_REVISION",
        }.get(verdict.verdict, "GOVERNANCE_CHECK")

        event_id = event_request.get("event_id")
        event = None
        if event_id is not None:
            event = await self.event_repo.get(event_id)
            if event and event.project_id != project_id:
                event = None

        governance_record = await self.governance_repo.create(
            {
                "project_id": project_id,
                "event_id": event.id if event else None,
                "event_name": event_request.get("name", "unknown"),
                "verdict": verdict.verdict,
                "score": verdict.score,
                "reasoning": verdict.reasoning,
                "recommended_code": verdict.recommended_code,
                "model_name": verdict.model_name,
                "request_payload": event_request,
                "result_payload": {
                    "risks": verdict.risks,
                    "suggestions": [item.model_dump() for item in verdict.suggestions],
                },
                "actor_id": actor_id,
            }
        )

        if event:
            mapped_status = {
                "APPROVE": "APPROVED",
                "REJECT": "REJECTED",
                "NEEDS_REVISION": "NEEDS_REVISION",
            }.get(verdict.verdict, "NOT_CHECKED")
            await self.event_repo.update(
                event,
                {"governance_status": mapped_status},
            )

        await self.audit_repo.create(
            {
                "action": verdict_action,
                "entity_type": "EVENT_REQUEST",
                "entity_id": event_request.get("name", "unknown"),
                "user_id": actor_id,
                "details": json.dumps(
                    {
                        "event_id": event.id if event else None,
                        "verdict": verdict.verdict,
                        "score": verdict.score,
                    },
                    ensure_ascii=True,
                ),
            }
        )

        return {
            "check_id": governance_record.id,
            "event_id": event.id if event else None,
            "verdict": verdict.verdict,
            "score": verdict.score,
            "reasoning": verdict.reasoning,
            "recommended_code": verdict.recommended_code,
            "risks": verdict.risks,
            "suggestions": [item.model_dump() for item in verdict.suggestions],
            "model_name": verdict.model_name,
            "similar_events": similar_events,
        }
