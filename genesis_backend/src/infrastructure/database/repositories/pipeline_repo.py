from typing import Optional

from sqlalchemy import Select, select

from src.infrastructure.database.models.pipeline import Pipeline, PipelineStatus
from src.infrastructure.database.repositories.base import BaseRepository


class PipelineRepository(BaseRepository[Pipeline]):
    def __init__(self, session):
        super().__init__(Pipeline, session)

    async def get_by_project(self, project_id: int) -> list[Pipeline]:
        query = select(self.model).where(self.model.project_id == project_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_project_and_event(self, project_id: int, event_code: str) -> Optional[Pipeline]:
        query = select(self.model).where(
            self.model.project_id == project_id,
            self.model.event_code == event_code,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_sync_candidates(self) -> list[Pipeline]:
        query = select(self.model).where(
            self.model.status.in_(
                [PipelineStatus.RUNNING.value, PipelineStatus.PROVISIONING.value]
            )
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_project_filtered(
        self,
        project_id: int,
        q: str | None = None,
        status: str | None = None,
        event_code: str | None = None,
        limit: int = 500,
    ) -> list[Pipeline]:
        query: Select = select(self.model).where(self.model.project_id == project_id)

        if event_code:
            query = query.where(self.model.event_code == event_code)
        if status:
            query = query.where(self.model.status == status)
        if q:
            q_like = f"%{q.strip()}%"
            query = query.where(
                (self.model.event_code.ilike(q_like))
                | (self.model.topic_name.ilike(q_like))
                | (self.model.flink_job_name.ilike(q_like))
            )

        query = query.order_by(self.model.updated_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
