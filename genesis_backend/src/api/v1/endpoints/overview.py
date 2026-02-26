from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.response import success_response
from src.api.v1.audit_utils import build_project_audit_filter, parse_actor
from src.api.v1.dependencies import RequestContext, get_request_context
from src.infrastructure.database.models.alert import Alert
from src.infrastructure.database.models.audit import AuditLog
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.governance_check import GovernanceCheck
from src.infrastructure.database.models.pipeline import Pipeline
from src.infrastructure.database.session import get_async_session

router = APIRouter()


def _activity_status(action: str) -> str:
    if "REJECT" in action or "FAILED" in action:
        return "FAILURE"
    return "SUCCESS"


def _priority_rank(priority: str) -> int:
    order = {
        "CRITICAL": 4,
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1,
    }
    return order.get(priority, 0)


@router.get("")
async def get_overview(
    context: RequestContext = Depends(get_request_context),
    db: AsyncSession = Depends(get_async_session),
):
    project = context.project
    cutoff_30d = datetime.now(timezone.utc) - timedelta(days=30)

    event_count_result = await db.execute(
        select(func.count(TrackingEvent.id)).where(TrackingEvent.project_id == project.id)
    )
    total_events = int(event_count_result.scalar_one() or 0)

    governance_counts_result = await db.execute(
        select(
            func.count(GovernanceCheck.id),
            func.sum(case((GovernanceCheck.verdict == "APPROVE", 1), else_=0)),
        ).where(
            GovernanceCheck.project_id == project.id,
            GovernanceCheck.created_at >= cutoff_30d,
        )
    )
    governance_checks_30d, governance_approvals_30d = governance_counts_result.one()
    governance_checks_30d = int(governance_checks_30d or 0)
    governance_approvals_30d = int(governance_approvals_30d or 0)
    approval_rate = (
        governance_approvals_30d / governance_checks_30d if governance_checks_30d else None
    )

    active_pipelines_result = await db.execute(
        select(func.count(Pipeline.id)).where(
            Pipeline.project_id == project.id,
            Pipeline.status == "RUNNING",
        )
    )
    active_pipelines = int(active_pipelines_result.scalar_one() or 0)

    failed_pipelines_result = await db.execute(
        select(func.count(Pipeline.id)).where(
            Pipeline.project_id == project.id,
            Pipeline.status.in_(["FAILED", "ROLLING_BACK"]),
        )
    )
    failed_pipelines = int(failed_pipelines_result.scalar_one() or 0)

    recent_query = (
        select(AuditLog)
        .where(build_project_audit_filter(project.id))
        .order_by(AuditLog.timestamp.desc())
        .limit(20)
    )
    recent_result = await db.execute(recent_query)
    recent_rows = list(recent_result.scalars().all())
    recent_activity = [
        {
            "id": row.id,
            "user": parse_actor(row.user_id),
            "action": row.action,
            "target": f"{row.entity_type}:{row.entity_id}",
            "timestamp": row.timestamp.isoformat(),
            "status": _activity_status(row.action),
        }
        for row in recent_rows
    ]

    high_risk_events_query = (
        select(GovernanceCheck)
        .where(
            GovernanceCheck.project_id == project.id,
            GovernanceCheck.verdict.in_(["REJECT", "NEEDS_REVISION"]),
        )
        .order_by(GovernanceCheck.created_at.desc())
        .limit(20)
    )
    high_risk_events_result = await db.execute(high_risk_events_query)
    high_risk_events_rows = list(high_risk_events_result.scalars().all())
    high_risk_events = [
        {
            "id": row.id,
            "event_name": row.event_name,
            "verdict": row.verdict,
            "score": row.score,
            "reasoning": row.reasoning,
            "actor": parse_actor(row.actor_id),
            "timestamp": row.created_at.isoformat(),
        }
        for row in high_risk_events_rows
    ]

    risky_pipelines_query = select(Pipeline).where(
        Pipeline.project_id == project.id,
        Pipeline.status.in_(["FAILED", "ROLLING_BACK"]),
    )
    risky_pipelines_result = await db.execute(risky_pipelines_query)
    risky_pipelines_rows = list(risky_pipelines_result.scalars().all())
    risky_pipelines = [
        {
            "id": row.id,
            "event_code": row.event_code,
            "topic_name": row.topic_name,
            "flink_job_name": row.flink_job_name,
            "status": row.status,
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "error_message": row.error_message,
        }
        for row in risky_pipelines_rows
    ]

    open_alerts_query = (
        select(Alert)
        .where(
            and_(
                Alert.project_id == project.id,
                Alert.status == "OPEN",
            )
        )
        .order_by(Alert.created_at.desc())
        .limit(20)
    )
    open_alerts_result = await db.execute(open_alerts_query)
    open_alert_rows = list(open_alerts_result.scalars().all())
    open_alerts = [
        {
            "id": row.id,
            "source_type": row.source_type,
            "source_id": row.source_id,
            "severity": row.severity,
            "title": row.title,
            "description": row.description,
            "status": row.status,
            "created_at": row.created_at.isoformat(),
        }
        for row in open_alert_rows
    ]

    todos = []
    for pipeline in risky_pipelines_rows:
        todos.append(
            {
                "id": f"pipeline-{pipeline.id}",
                "type": "PIPELINE",
                "priority": "HIGH",
                "status": "OPEN",
                "title": f"Pipeline {pipeline.id} requires intervention",
                "description": pipeline.error_message or "Pipeline status is not healthy",
                "target": {
                    "type": "PIPELINE",
                    "id": str(pipeline.id),
                    "label": pipeline.flink_job_name,
                },
                "created_at": pipeline.updated_at.isoformat(),
            }
        )

    for event in high_risk_events_rows:
        priority = "CRITICAL" if event.verdict == "REJECT" else "HIGH"
        todos.append(
            {
                "id": f"governance-{event.id}",
                "type": "GOVERNANCE",
                "priority": priority,
                "status": "OPEN",
                "title": f"Governance follow-up for {event.event_name}",
                "description": event.reasoning,
                "target": {
                    "type": "EVENT",
                    "id": event.event_name,
                    "label": event.event_name,
                },
                "created_at": event.created_at.isoformat(),
            }
        )

    for alert in open_alert_rows:
        todos.append(
            {
                "id": f"alert-{alert.id}",
                "type": "ALERT",
                "priority": alert.severity,
                "status": "OPEN",
                "title": alert.title,
                "description": alert.description,
                "target": {
                    "type": alert.source_type,
                    "id": alert.source_id,
                    "label": f"{alert.source_type}:{alert.source_id}",
                },
                "created_at": alert.created_at.isoformat(),
            }
        )

    todos = sorted(
        todos,
        key=lambda item: (_priority_rank(item["priority"]), item["created_at"]),
        reverse=True,
    )[:50]

    data = {
        "kpis": {
            "total_events": total_events,
            "governance_checks_30d": governance_checks_30d,
            "approval_rate": approval_rate,
            "active_pipelines": active_pipelines,
            "failed_pipelines": failed_pipelines,
        },
        "recent_activity": recent_activity,
        "risks": {
            "high_risk_events": high_risk_events,
            "pipelines": risky_pipelines,
            "unhandled_alerts": open_alerts,
        },
        "todos": todos,
    }
    return success_response(data)
