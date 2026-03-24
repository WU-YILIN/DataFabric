from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.dependencies import RequestContext, get_request_context
from src.domain.assistant.chat_service import AssistantChatService
from src.domain.fabric_execution_service import FabricExecutionService
from src.infrastructure.database.session import get_async_session

router = APIRouter()


class AssistantChatMessage(BaseModel):
    role: Literal["user", "assistant"] = Field(...)
    content: str = Field(..., min_length=1, max_length=12000)


class AssistantRuntimeConfig(BaseModel):
    api_key: str | None = Field(default=None, max_length=512)
    base_url: str | None = Field(default=None, max_length=1000)
    model: str | None = Field(default=None, max_length=255)


class AssistantChatRequest(BaseModel):
    messages: list[AssistantChatMessage] = Field(..., min_length=1, max_length=30)
    include_knowledge: bool = True
    include_sources: bool = True
    runtime_config: AssistantRuntimeConfig | None = None


@router.post("/chat")
async def assistant_chat(
    request: AssistantChatRequest,
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    if context.user is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Assistant chat requires bearer user context",
        )

    latest_question = next(
        (item.content.strip() for item in reversed(request.messages) if item.role == "user" and item.content.strip()),
        "",
    )
    trace_payload: dict | None = None
    if latest_question:
        execution_service = FabricExecutionService(db)
        trace = await execution_service.submit_query(
            project_id=context.project.id,
            tenant_id=context.project.tenant_id,
            actor_id=context.actor_id,
            actor_user_id=context.user.id if context.user else None,
            question=latest_question,
            latency_target_ms=800,
        )
        trace_payload = {
            "trace_id": trace["trace_id"],
            "intent": trace["intent"],
            "plan": trace["plan"],
            "run": trace["run"],
            "artifacts": trace["artifacts"],
        }

    service = AssistantChatService(db)
    result = await service.chat(
        project_id=context.project.id,
        tenant_id=context.project.tenant_id,
        messages=[item.model_dump() for item in request.messages],
        include_knowledge=request.include_knowledge,
        include_sources=request.include_sources,
        runtime_config=request.runtime_config.model_dump(exclude_none=True) if request.runtime_config else None,
        query_trace=trace_payload,
    )
    if trace_payload is not None:
        result["query_trace"] = trace_payload
    return success_response(result)
