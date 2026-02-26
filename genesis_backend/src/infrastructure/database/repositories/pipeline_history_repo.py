from sqlalchemy import select

from src.infrastructure.database.models.pipeline_history import PipelineStatusHistory
from src.infrastructure.database.repositories.base import BaseRepository


class PipelineHistoryRepository(BaseRepository[PipelineStatusHistory]):
    def __init__(self, session):
        super().__init__(PipelineStatusHistory, session)

    async def get_by_pipeline(self, pipeline_id: int, limit: int = 200) -> list[PipelineStatusHistory]:
        query = (
            select(self.model)
            .where(self.model.pipeline_id == pipeline_id)
            .order_by(self.model.synced_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
