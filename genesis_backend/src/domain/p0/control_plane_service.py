from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.contract_artifact import ContractArtifact
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.models.governance_decision_record import GovernanceDecisionRecord
from src.infrastructure.database.models.inference_candidate import InferenceCandidate
from src.infrastructure.database.models.ingestion_event_log import IngestionEventLog
from src.infrastructure.database.models.observation_source_profile import ObservationSourceProfile
from src.infrastructure.database.models.schema_field_mapping import (
    FieldMappingStatus,
    SchemaFieldMapping,
)


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _recommended_action(mapping: SchemaFieldMapping) -> str:
    if mapping.status != FieldMappingStatus.PENDING:
        return "NONE"
    if mapping.target_field.startswith("_unmapped_"):
        return "MANUAL_MODELING"
    if mapping.confidence_score >= 0.85:
        return "FAST_REVIEW"
    return "REVIEW"


def _contract_name(event_code: str) -> str:
    return f"contract.{event_code}"


class P0ControlPlaneService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_source_profile_detail(
        self,
        project_id: int,
        source_profile_id: int,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(ObservationSourceProfile).where(
                ObservationSourceProfile.project_id == project_id,
                ObservationSourceProfile.id == source_profile_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        return {
            "id": item.id,
            "channel_id": item.channel_id,
            "event_name": item.event_name,
            "heat": item.heat,
            "total_events": item.total_events,
            "accepted_events": item.accepted_events,
            "sdk_version": item.sdk_version,
            "last_seen_at": _to_iso(item.last_seen_at),
            "updated_at": _to_iso(item.updated_at),
            "profile_payload": item.profile_payload,
        }

    async def list_source_profiles(
        self,
        project_id: int,
        limit: int = 20,
        offset: int = 0,
        heat: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(ObservationSourceProfile).where(
            ObservationSourceProfile.project_id == project_id
        )
        if heat:
            stmt = stmt.where(ObservationSourceProfile.heat == heat.upper())
        if q and q.strip():
            keyword = f"%{q.strip()}%"
            stmt = stmt.where(ObservationSourceProfile.event_name.ilike(keyword))

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(total_stmt)
        total = int(total_result.scalar_one() or 0)

        result = await self.db.execute(
            stmt.order_by(
                ObservationSourceProfile.total_events.desc(),
                ObservationSourceProfile.last_seen_at.desc(),
                ObservationSourceProfile.event_name.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = [
            {
                "id": item.id,
                "channel_id": item.channel_id,
                "event_name": item.event_name,
                "heat": item.heat,
                "total_events": item.total_events,
                "accepted_events": item.accepted_events,
                "sdk_version": item.sdk_version,
                "last_seen_at": _to_iso(item.last_seen_at),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in result.scalars().all()
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_inference_candidate_detail(
        self,
        project_id: int,
        candidate_id: int,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(InferenceCandidate).where(
                InferenceCandidate.project_id == project_id,
                InferenceCandidate.id == candidate_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        return {
            "id": item.id,
            "mapping_id": item.mapping_id,
            "candidate_type": item.candidate_type,
            "event_id": item.event_id,
            "target_field": item.target_field,
            "source_paths": item.source_paths,
            "status": item.status,
            "confidence_score": item.confidence_score,
            "field_frequency": item.field_frequency,
            "proposed_by": item.proposed_by,
            "reasoning": item.reasoning,
            "recommended_action": item.recommended_action,
            "last_observed_at": _to_iso(item.last_observed_at),
            "updated_at": _to_iso(item.updated_at),
        }

    async def list_inference_candidates(
        self,
        project_id: int,
        limit: int = 20,
        offset: int = 0,
        candidate_type: str | None = None,
        status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(InferenceCandidate).where(InferenceCandidate.project_id == project_id)
        if candidate_type:
            stmt = stmt.where(InferenceCandidate.candidate_type == candidate_type.upper())
        if status:
            stmt = stmt.where(InferenceCandidate.status == status.upper())
        if q and q.strip():
            keyword = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    InferenceCandidate.target_field.ilike(keyword),
                    InferenceCandidate.candidate_type.ilike(keyword),
                    InferenceCandidate.recommended_action.ilike(keyword),
                )
            )

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(total_stmt)
        total = int(total_result.scalar_one() or 0)

        result = await self.db.execute(
            stmt.order_by(
                InferenceCandidate.status.asc(),
                InferenceCandidate.confidence_score.desc(),
                InferenceCandidate.field_frequency.desc(),
                InferenceCandidate.updated_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = [
            {
                "id": item.id,
                "mapping_id": item.mapping_id,
                "candidate_type": item.candidate_type,
                "event_id": item.event_id,
                "target_field": item.target_field,
                "source_paths": item.source_paths,
                "status": item.status,
                "confidence_score": item.confidence_score,
                "field_frequency": item.field_frequency,
                "proposed_by": item.proposed_by,
                "reasoning": item.reasoning,
                "recommended_action": item.recommended_action,
                "last_observed_at": _to_iso(item.last_observed_at),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in result.scalars().all()
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_governance_record_detail(
        self,
        project_id: int,
        record_id: int,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(GovernanceDecisionRecord).where(
                GovernanceDecisionRecord.project_id == project_id,
                GovernanceDecisionRecord.id == record_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        return {
            "id": item.id,
            "mapping_id": item.mapping_id,
            "event_id": item.event_id,
            "target_field": item.target_field,
            "decision_status": item.decision_status,
            "queue_status": item.queue_status,
            "confidence_score": item.confidence_score,
            "field_frequency": item.field_frequency,
            "recommended_action": item.recommended_action,
            "actor": item.actor,
            "note": item.note,
            "decided_at": _to_iso(item.decided_at),
            "updated_at": _to_iso(item.updated_at),
        }

    async def list_governance_records(
        self,
        project_id: int,
        limit: int = 20,
        offset: int = 0,
        queue_status: str | None = None,
        decision_status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(GovernanceDecisionRecord).where(
            GovernanceDecisionRecord.project_id == project_id
        )
        if queue_status:
            stmt = stmt.where(GovernanceDecisionRecord.queue_status == queue_status.upper())
        if decision_status:
            stmt = stmt.where(GovernanceDecisionRecord.decision_status == decision_status.upper())
        if q and q.strip():
            keyword = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    GovernanceDecisionRecord.target_field.ilike(keyword),
                    GovernanceDecisionRecord.decision_status.ilike(keyword),
                    GovernanceDecisionRecord.queue_status.ilike(keyword),
                    GovernanceDecisionRecord.recommended_action.ilike(keyword),
                )
            )

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(total_stmt)
        total = int(total_result.scalar_one() or 0)

        result = await self.db.execute(
            stmt.order_by(
                GovernanceDecisionRecord.queue_status.asc(),
                GovernanceDecisionRecord.decided_at.desc(),
                GovernanceDecisionRecord.updated_at.desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = [
            {
                "id": item.id,
                "mapping_id": item.mapping_id,
                "event_id": item.event_id,
                "target_field": item.target_field,
                "decision_status": item.decision_status,
                "queue_status": item.queue_status,
                "confidence_score": item.confidence_score,
                "field_frequency": item.field_frequency,
                "recommended_action": item.recommended_action,
                "actor": item.actor,
                "note": item.note,
                "decided_at": _to_iso(item.decided_at),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in result.scalars().all()
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_contract_artifact_detail(
        self,
        project_id: int,
        artifact_id: int,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(ContractArtifact).where(
                ContractArtifact.project_id == project_id,
                ContractArtifact.id == artifact_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            return None
        return {
            "id": item.id,
            "event_id": item.event_id,
            "event_code": item.event_code,
            "contract_name": item.contract_name,
            "serving_status": item.serving_status,
            "approved_rule_count": item.approved_rule_count,
            "published_at": _to_iso(item.published_at),
            "updated_at": _to_iso(item.updated_at),
        }

    async def list_contract_artifacts(
        self,
        project_id: int,
        limit: int = 20,
        offset: int = 0,
        serving_status: str | None = None,
        q: str | None = None,
    ) -> dict[str, Any]:
        stmt = select(ContractArtifact).where(ContractArtifact.project_id == project_id)
        if serving_status:
            stmt = stmt.where(ContractArtifact.serving_status == serving_status.upper())
        if q and q.strip():
            keyword = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    ContractArtifact.event_code.ilike(keyword),
                    ContractArtifact.contract_name.ilike(keyword),
                    ContractArtifact.serving_status.ilike(keyword),
                )
            )

        total_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.db.execute(total_stmt)
        total = int(total_result.scalar_one() or 0)

        result = await self.db.execute(
            stmt.order_by(
                ContractArtifact.published_at.desc(),
                ContractArtifact.updated_at.desc(),
                ContractArtifact.event_code.asc(),
            )
            .offset(offset)
            .limit(limit)
        )
        items = [
            {
                "id": item.id,
                "event_id": item.event_id,
                "event_code": item.event_code,
                "contract_name": item.contract_name,
                "serving_status": item.serving_status,
                "approved_rule_count": item.approved_rule_count,
                "published_at": _to_iso(item.published_at),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in result.scalars().all()
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset}

    async def get_overview(self, project_id: int) -> dict[str, Any]:
        cutoff_7d = datetime.now(timezone.utc) - timedelta(days=7)

        total_logs_result = await self.db.execute(
            select(func.count(IngestionEventLog.id)).where(IngestionEventLog.project_id == project_id)
        )
        total_logs = int(total_logs_result.scalar_one() or 0)

        active_channels_result = await self.db.execute(
            select(func.count(func.distinct(IngestionEventLog.channel_id))).where(
                IngestionEventLog.project_id == project_id
            )
        )
        active_channels = int(active_channels_result.scalar_one() or 0)

        events_7d_result = await self.db.execute(
            select(func.count(IngestionEventLog.id)).where(
                IngestionEventLog.project_id == project_id,
                IngestionEventLog.created_at >= cutoff_7d,
            )
        )
        events_7d = int(events_7d_result.scalar_one() or 0)

        top_sources_result = await self.db.execute(
            select(
                IngestionEventLog.event_name,
                func.count(IngestionEventLog.id).label("event_count"),
            )
            .where(IngestionEventLog.project_id == project_id)
            .group_by(IngestionEventLog.event_name)
            .order_by(func.count(IngestionEventLog.id).desc(), IngestionEventLog.event_name.asc())
            .limit(5)
        )
        top_sources = [
            {"event_name": row.event_name, "event_count": int(row.event_count or 0)}
            for row in top_sources_result.all()
        ]

        source_profiles_result = await self.db.execute(
            select(
                IngestionEventLog.channel_id,
                IngestionEventLog.event_name,
                func.count(IngestionEventLog.id).label("total_events"),
                func.sum(case((IngestionEventLog.status == "ACCEPTED", 1), else_=0)).label(
                    "accepted_events"
                ),
                func.max(IngestionEventLog.created_at).label("last_seen_at"),
                func.max(IngestionEventLog.sdk_version).label("sdk_version"),
            )
            .where(IngestionEventLog.project_id == project_id)
            .group_by(IngestionEventLog.channel_id, IngestionEventLog.event_name)
            .order_by(func.count(IngestionEventLog.id).desc(), IngestionEventLog.event_name.asc())
            .limit(8)
        )
        source_profiles = []
        for row in source_profiles_result.all():
            total_events_for_source = int(row.total_events or 0)
            if total_events_for_source >= 1000:
                heat = "HOT"
            elif total_events_for_source >= 100:
                heat = "WARM"
            else:
                heat = "COLD"
            source_profiles.append(
                {
                    "channel_id": row.channel_id,
                    "event_name": row.event_name,
                    "total_events": total_events_for_source,
                    "accepted_events": int(row.accepted_events or 0),
                    "last_seen_at": _to_iso(row.last_seen_at),
                    "sdk_version": row.sdk_version,
                    "heat": heat,
                }
            )
        await self._sync_source_profiles(project_id, source_profiles)

        mapping_counts_result = await self.db.execute(
            select(
                func.count(SchemaFieldMapping.id),
                func.sum(case((SchemaFieldMapping.status == FieldMappingStatus.PENDING, 1), else_=0)),
                func.sum(case((SchemaFieldMapping.status == FieldMappingStatus.APPROVED, 1), else_=0)),
                func.sum(case((SchemaFieldMapping.status == FieldMappingStatus.REJECTED, 1), else_=0)),
                func.avg(SchemaFieldMapping.confidence_score),
            ).where(SchemaFieldMapping.project_id == project_id)
        )
        total_mappings, pending_mappings, approved_mappings, rejected_mappings, avg_confidence = (
            mapping_counts_result.one()
        )
        total_mappings = int(total_mappings or 0)
        pending_mappings = int(pending_mappings or 0)
        approved_mappings = int(approved_mappings or 0)
        rejected_mappings = int(rejected_mappings or 0)
        avg_confidence = float(avg_confidence or 0.0)

        high_confidence_pending_result = await self.db.execute(
            select(func.count(SchemaFieldMapping.id)).where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.PENDING,
                SchemaFieldMapping.confidence_score >= 0.7,
            )
        )
        high_confidence_pending = int(high_confidence_pending_result.scalar_one() or 0)

        top_proposals_result = await self.db.execute(
            select(SchemaFieldMapping)
            .where(SchemaFieldMapping.project_id == project_id)
            .order_by(
                SchemaFieldMapping.field_frequency.desc(),
                SchemaFieldMapping.confidence_score.desc(),
                SchemaFieldMapping.updated_at.desc(),
            )
            .limit(8)
        )
        top_proposals = [
            {
                "id": item.id,
                "event_id": item.event_id,
                "target_field": item.target_field,
                "source_paths": item.source_paths,
                "status": item.status,
                "confidence_score": item.confidence_score,
                "field_frequency": item.field_frequency,
                "proposed_by": item.proposed_by,
                "ai_reasoning": item.ai_reasoning,
                "recommended_action": _recommended_action(item),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in top_proposals_result.scalars().all()
        ]

        inference_candidates_result = await self.db.execute(
            select(SchemaFieldMapping)
            .where(SchemaFieldMapping.project_id == project_id)
            .order_by(
                SchemaFieldMapping.status.asc(),
                SchemaFieldMapping.confidence_score.desc(),
                SchemaFieldMapping.field_frequency.desc(),
                SchemaFieldMapping.updated_at.desc(),
            )
            .limit(12)
        )
        inference_candidates = [
            {
                "id": item.id,
                "candidate_type": (
                    "UNMAPPED_SIGNAL"
                    if item.target_field.startswith("_unmapped_")
                    else "SEMANTIC_MAPPING"
                ),
                "event_id": item.event_id,
                "target_field": item.target_field,
                "source_paths": item.source_paths,
                "status": item.status,
                "confidence_score": item.confidence_score,
                "field_frequency": item.field_frequency,
                "proposed_by": item.proposed_by,
                "reasoning": item.ai_reasoning,
                "recommended_action": _recommended_action(item),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in inference_candidates_result.scalars().all()
        ]
        await self._sync_inference_candidates(project_id, inference_candidates)

        unmapped_pending_count_result = await self.db.execute(
            select(func.count(SchemaFieldMapping.id)).where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.PENDING,
                SchemaFieldMapping.target_field.like(r"\_unmapped\_%", escape="\\"),
            )
        )
        unmapped_pending = int(unmapped_pending_count_result.scalar_one() or 0)

        ai_generated_pending_result = await self.db.execute(
            select(func.count(SchemaFieldMapping.id)).where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.PENDING,
                SchemaFieldMapping.proposed_by == "ai",
            )
        )
        ai_generated_pending = int(ai_generated_pending_result.scalar_one() or 0)

        unknown_signals_result = await self.db.execute(
            select(SchemaFieldMapping)
            .where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.PENDING,
                SchemaFieldMapping.target_field.like(r"\_unmapped\_%", escape="\\"),
            )
            .order_by(
                SchemaFieldMapping.field_frequency.desc(),
                SchemaFieldMapping.updated_at.desc(),
            )
            .limit(8)
        )
        unknown_signals = [
            {
                "id": item.id,
                "event_id": item.event_id,
                "target_field": item.target_field,
                "source_paths": item.source_paths,
                "field_frequency": item.field_frequency,
                "updated_at": _to_iso(item.updated_at),
            }
            for item in unknown_signals_result.scalars().all()
        ]

        contract_count_result = await self.db.execute(
            select(func.count(func.distinct(SchemaFieldMapping.event_id))).where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.APPROVED,
            )
        )
        active_contracts = int(contract_count_result.scalar_one() or 0)

        contract_rows_result = await self.db.execute(
            select(SchemaFieldMapping, TrackingEvent.code)
            .join(TrackingEvent, TrackingEvent.id == SchemaFieldMapping.event_id)
            .where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.APPROVED,
            )
            .order_by(SchemaFieldMapping.updated_at.desc())
            .limit(8)
        )
        recent_contracts = [
            {
                "mapping_id": mapping.id,
                "event_id": mapping.event_id,
                "event_code": event_code,
                "contract_name": _contract_name(event_code),
                "target_field": mapping.target_field,
                "cast_type": mapping.cast_type,
                "approved_by": mapping.approved_by,
                "updated_at": _to_iso(mapping.updated_at),
            }
            for mapping, event_code in contract_rows_result.all()
        ]

        contract_artifacts_result = await self.db.execute(
            select(
                TrackingEvent.id,
                TrackingEvent.code,
                func.count(SchemaFieldMapping.id).label("approved_rule_count"),
                func.max(SchemaFieldMapping.updated_at).label("published_at"),
            )
            .join(SchemaFieldMapping, SchemaFieldMapping.event_id == TrackingEvent.id)
            .where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.APPROVED,
            )
            .group_by(TrackingEvent.id, TrackingEvent.code)
            .order_by(func.max(SchemaFieldMapping.updated_at).desc(), TrackingEvent.code.asc())
            .limit(8)
        )
        contract_artifacts = [
            {
                "event_id": event_id,
                "event_code": event_code,
                "contract_name": _contract_name(event_code),
                "approved_rule_count": int(approved_rule_count or 0),
                "published_at": _to_iso(published_at),
                "serving_status": "PUBLISHED",
            }
            for event_id, event_code, approved_rule_count, published_at in contract_artifacts_result.all()
        ]
        await self._sync_contract_artifacts(project_id, contract_artifacts)

        recent_decisions_result = await self.db.execute(
            select(SchemaFieldMapping)
            .where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status.in_(
                    [FieldMappingStatus.APPROVED, FieldMappingStatus.REJECTED]
                ),
            )
            .order_by(SchemaFieldMapping.updated_at.desc())
            .limit(8)
        )
        recent_decisions = [
            {
                "id": item.id,
                "event_id": item.event_id,
                "target_field": item.target_field,
                "status": item.status,
                "actor": item.approved_by,
                "note": item.note,
                "updated_at": _to_iso(item.updated_at),
            }
            for item in recent_decisions_result.scalars().all()
        ]

        governance_queue_result = await self.db.execute(
            select(SchemaFieldMapping)
            .where(
                SchemaFieldMapping.project_id == project_id,
                SchemaFieldMapping.status == FieldMappingStatus.PENDING,
            )
            .order_by(
                SchemaFieldMapping.confidence_score.desc(),
                SchemaFieldMapping.field_frequency.desc(),
                SchemaFieldMapping.updated_at.desc(),
            )
            .limit(10)
        )
        governance_queue = [
            {
                "id": item.id,
                "event_id": item.event_id,
                "target_field": item.target_field,
                "status": item.status,
                "confidence_score": item.confidence_score,
                "field_frequency": item.field_frequency,
                "recommended_action": _recommended_action(item),
                "updated_at": _to_iso(item.updated_at),
            }
            for item in governance_queue_result.scalars().all()
        ]
        await self._sync_governance_records(
            project_id=project_id,
            queue=governance_queue,
            recent_decisions=recent_decisions,
        )

        return {
            "summary": {
                "observation_sources": active_channels,
                "observed_events": total_logs,
                "inference_queue": pending_mappings,
                "published_contracts": active_contracts,
            },
            "observation": {
                "total_logs": total_logs,
                "events_7d": events_7d,
                "active_channels": active_channels,
                "top_sources": top_sources,
                "source_profiles": source_profiles,
                "unknown_signals": unknown_signals,
            },
            "inference": {
                "total_proposals": total_mappings,
                "pending_proposals": pending_mappings,
                "high_confidence_pending": high_confidence_pending,
                "ai_generated_pending": ai_generated_pending,
                "unmapped_pending": unmapped_pending,
                "avg_confidence": avg_confidence,
                "top_proposals": top_proposals,
                "candidates": inference_candidates,
            },
            "governance": {
                "pending_reviews": pending_mappings,
                "approved_rules": approved_mappings,
                "rejected_rules": rejected_mappings,
                "decision_summary": {
                    "pending": pending_mappings,
                    "approved": approved_mappings,
                    "rejected": rejected_mappings,
                },
                "queue": governance_queue,
                "recent_decisions": recent_decisions,
            },
            "contract": {
                "active_contracts": active_contracts,
                "approved_rules": approved_mappings,
                "artifacts": contract_artifacts,
                "recent_contracts": recent_contracts,
            },
        }

    async def _sync_source_profiles(
        self,
        project_id: int,
        profiles: list[dict[str, Any]],
    ) -> None:
        if not profiles:
            return

        existing_result = await self.db.execute(
            select(ObservationSourceProfile).where(ObservationSourceProfile.project_id == project_id)
        )
        existing_items = list(existing_result.scalars().all())
        existing_map = {
            (item.channel_id, item.event_name): item
            for item in existing_items
        }

        for profile in profiles:
            key = (profile["channel_id"], profile["event_name"])
            record = existing_map.get(key)
            if record is None:
                record = ObservationSourceProfile(
                    project_id=project_id,
                    channel_id=profile["channel_id"],
                    event_name=profile["event_name"],
                )
                self.db.add(record)

            record.heat = profile["heat"]
            record.total_events = profile["total_events"]
            record.accepted_events = profile["accepted_events"]
            record.sdk_version = profile["sdk_version"]
            record.last_seen_at = (
                datetime.fromisoformat(profile["last_seen_at"].replace("Z", "+00:00"))
                if profile["last_seen_at"]
                else None
            )
            record.profile_payload = profile

        await self.db.commit()

    async def _sync_inference_candidates(
        self,
        project_id: int,
        candidates: list[dict[str, Any]],
    ) -> None:
        if not candidates:
            return

        existing_result = await self.db.execute(
            select(InferenceCandidate).where(InferenceCandidate.project_id == project_id)
        )
        existing_items = list(existing_result.scalars().all())
        existing_map = {
            item.mapping_id: item
            for item in existing_items
            if item.mapping_id is not None
        }

        for candidate in candidates:
            mapping_id = candidate["id"]
            record = existing_map.get(mapping_id)
            if record is None:
                record = InferenceCandidate(
                    project_id=project_id,
                    mapping_id=mapping_id,
                )
                self.db.add(record)

            record.event_id = candidate["event_id"]
            record.candidate_type = candidate["candidate_type"]
            record.status = candidate["status"]
            record.target_field = candidate["target_field"]
            record.source_paths = candidate["source_paths"]
            record.confidence_score = candidate["confidence_score"]
            record.field_frequency = candidate["field_frequency"]
            record.proposed_by = candidate["proposed_by"]
            record.reasoning = candidate["reasoning"]
            record.recommended_action = candidate["recommended_action"]
            record.last_observed_at = (
                datetime.fromisoformat(candidate["updated_at"].replace("Z", "+00:00"))
                if candidate["updated_at"]
                else None
            )

        await self.db.commit()

    async def _sync_governance_records(
        self,
        project_id: int,
        queue: list[dict[str, Any]],
        recent_decisions: list[dict[str, Any]],
    ) -> None:
        if not queue and not recent_decisions:
            return

        existing_result = await self.db.execute(
            select(GovernanceDecisionRecord).where(
                GovernanceDecisionRecord.project_id == project_id
            )
        )
        existing_items = list(existing_result.scalars().all())
        existing_map = {
            item.mapping_id: item
            for item in existing_items
            if item.mapping_id is not None
        }

        for item in queue:
            mapping_id = item["id"]
            record = existing_map.get(mapping_id)
            if record is None:
                record = GovernanceDecisionRecord(
                    project_id=project_id,
                    mapping_id=mapping_id,
                )
                self.db.add(record)

            record.event_id = item["event_id"]
            record.target_field = item["target_field"]
            record.decision_status = item["status"]
            record.queue_status = "OPEN"
            record.confidence_score = item["confidence_score"]
            record.field_frequency = item["field_frequency"]
            record.recommended_action = item["recommended_action"]

        for item in recent_decisions:
            mapping_id = item["id"]
            record = existing_map.get(mapping_id)
            if record is None:
                record = GovernanceDecisionRecord(
                    project_id=project_id,
                    mapping_id=mapping_id,
                )
                self.db.add(record)

            record.event_id = item["event_id"]
            record.target_field = item["target_field"]
            record.decision_status = item["status"]
            record.queue_status = "CLOSED"
            record.actor = item["actor"]
            record.note = item["note"]
            record.decided_at = (
                datetime.fromisoformat(item["updated_at"].replace("Z", "+00:00"))
                if item["updated_at"]
                else None
            )

        await self.db.commit()

    async def _sync_contract_artifacts(
        self,
        project_id: int,
        artifacts: list[dict[str, Any]],
    ) -> None:
        if not artifacts:
            return

        existing_result = await self.db.execute(
            select(ContractArtifact).where(ContractArtifact.project_id == project_id)
        )
        existing_items = list(existing_result.scalars().all())
        existing_map = {
            item.event_id: item
            for item in existing_items
            if item.event_id is not None
        }

        for item in artifacts:
            event_id = item["event_id"]
            record = existing_map.get(event_id)
            if record is None:
                record = ContractArtifact(
                    project_id=project_id,
                    event_id=event_id,
                )
                self.db.add(record)

            record.event_code = item["event_code"]
            record.contract_name = item["contract_name"]
            record.serving_status = item["serving_status"]
            record.approved_rule_count = item["approved_rule_count"]
            record.published_at = (
                datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                if item["published_at"]
                else None
            )

        await self.db.commit()
