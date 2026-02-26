from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.session import get_async_session

router = APIRouter()


@router.get("/summary")
async def get_summary_stats(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    event_count_result = await db.execute(
        select(func.count(TrackingEvent.id)).where(TrackingEvent.project_id == context.project.id)
    )
    governance_check_result = await db.execute(
        select(func.count(AuditLog.id)).where(
            build_project_audit_filter(context.project.id),
            AuditLog.action.like("GOVERNANCE_%"),
        )
    )
    running_pipeline_result = await db.execute(
        select(func.count(Pipeline.id)).where(
            Pipeline.project_id == context.project.id,
            Pipeline.status == "RUNNING",
        )
    )

    total_events = int(event_count_result.scalar_one() or 0)
    total_governance_checks = int(governance_check_result.scalar_one() or 0)
    active_workers = int(running_pipeline_result.scalar_one() or 0)

    data = {
        "total": total_events,
        "governance_checks": total_governance_checks,
        "avg_latency": "N/A",
        "active_workers": active_workers,
    }
    return success_response(data)
