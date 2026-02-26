from sqlalchemy import select

from src.infrastructure.database.models.data_quality_rule_change_log import DataQualityRuleChangeLog
from src.infrastructure.database.repositories.base import BaseRepository


class DataQualityRuleChangeLogRepository(BaseRepository[DataQualityRuleChangeLog]):
    def __init__(self, session):
        super().__init__(DataQualityRuleChangeLog, session)

    async def get_by_rule(self, rule_id: int, limit: int = 100) -> list[DataQualityRuleChangeLog]:
        query = (
            select(self.model)
            .where(self.model.rule_id == rule_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
