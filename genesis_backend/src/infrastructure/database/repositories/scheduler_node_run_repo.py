from sqlalchemy import select

from src.infrastructure.database.models.scheduler_node_run import SchedulerNodeRun
from src.infrastructure.database.repositories.base import BaseRepository


class SchedulerNodeRunRepository(BaseRepository[SchedulerNodeRun]):
    def __init__(self, session):
        super().__init__(SchedulerNodeRun, session)

    async def get_by_run(self, run_id: int) -> list[SchedulerNodeRun]:
        result = await self.session.execute(
            select(self.model).where(self.model.run_id == run_id).order_by(self.model.id.asc())
        )
        return list(result.scalars().all())
