from sqlalchemy import Select, select

from src.infrastructure.database.models.data_quality_rule import DataQualityRule
from src.infrastructure.database.repositories.base import BaseRepository


class DataQualityRuleRepository(BaseRepository[DataQualityRule]):
    def __init__(self, session):
        super().__init__(DataQualityRule, session)

    async def get_by_event(self, project_id: int, event_id: int) -> list[DataQualityRule]:
        query = (
            select(self.model)
            .where(
                self.model.project_id == project_id,
                self.model.event_id == event_id,
            )
            .order_by(self.model.updated_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_project_filtered(
        self,
        project_id: int,
        q: str | None = None,
        asset_id: int | None = None,
        event_id: int | None = None,
        rule_type: str | None = None,
        severity: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[DataQualityRule]:
        query: Select = select(self.model).where(self.model.project_id == project_id)
        if q:
            q_like = f"%{q.strip()}%"
            query = query.where(
                self.model.name.ilike(q_like)
                | self.model.rule_type.ilike(q_like)
                | self.model.target_field.ilike(q_like)
            )
        if asset_id is not None:
            query = query.where(self.model.asset_id == asset_id)
        if event_id is not None:
            query = query.where(self.model.event_id == event_id)
        if rule_type:
            query = query.where(self.model.rule_type == rule_type)
        if severity:
            query = query.where(self.model.severity == severity)
        if status:
            query = query.where(self.model.status == status)
        query = query.order_by(self.model.updated_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
