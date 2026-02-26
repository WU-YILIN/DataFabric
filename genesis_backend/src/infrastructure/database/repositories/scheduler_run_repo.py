from sqlalchemy import select

from src.infrastructure.database.models.scheduler_run import SchedulerRun
from src.infrastructure.database.repositories.base import BaseRepository


class SchedulerRunRepository(BaseRepository[SchedulerRun]):
    def __init__(self, session):
        super().__init__(SchedulerRun, session)

    async def get_by_dag(self, dag_id: int, limit: int = 50) -> list[SchedulerRun]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.dag_id == dag_id)
            .order_by(self.model.started_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_last_by_dag(self, dag_id: int) -> SchedulerRun | None:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.dag_id == dag_id)
            .order_by(self.model.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
