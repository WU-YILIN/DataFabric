from sqlalchemy import select

from src.infrastructure.database.models.data_quality_execution_log import DataQualityExecutionLog
from src.infrastructure.database.repositories.base import BaseRepository


class DataQualityExecutionLogRepository(BaseRepository[DataQualityExecutionLog]):
    def __init__(self, session):
        super().__init__(DataQualityExecutionLog, session)

    async def get_by_rule(self, rule_id: int, limit: int = 100) -> list[DataQualityExecutionLog]:
        query = (
            select(self.model)
            .where(self.model.rule_id == rule_id)
            .order_by(self.model.executed_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
