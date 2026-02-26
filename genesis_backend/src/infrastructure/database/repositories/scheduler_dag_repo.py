from sqlalchemy import Select, select

from src.infrastructure.database.models.scheduler_dag import SchedulerDag
from src.infrastructure.database.repositories.base import BaseRepository


class SchedulerDagRepository(BaseRepository[SchedulerDag]):
    def __init__(self, session):
        super().__init__(SchedulerDag, session)

    async def list_by_project_filtered(
        self,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        trigger_mode: str | None = None,
        limit: int = 200,
    ) -> list[SchedulerDag]:
        query: Select = select(self.model).where(self.model.project_id == project_id)
        if q:
            q_like = f"%{q.strip()}%"
            query = query.where(
                self.model.name.ilike(q_like) | self.model.description.ilike(q_like)
            )
        if status:
            query = query.where(self.model.status == status)
        if trigger_mode:
            query = query.where(self.model.trigger_mode == trigger_mode)
        query = query.order_by(self.model.updated_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
