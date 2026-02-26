from sqlalchemy import select

from src.infrastructure.database.models.scheduler_dag_edge import SchedulerDagEdge
from src.infrastructure.database.repositories.base import BaseRepository


class SchedulerDagEdgeRepository(BaseRepository[SchedulerDagEdge]):
    def __init__(self, session):
        super().__init__(SchedulerDagEdge, session)

    async def get_by_dag(self, dag_id: int) -> list[SchedulerDagEdge]:
        result = await self.session.execute(
            select(self.model).where(self.model.dag_id == dag_id).order_by(self.model.id.asc())
        )
        return list(result.scalars().all())
