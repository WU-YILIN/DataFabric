from typing import List, Optional
from sqlalchemy import Select, select
from src.infrastructure.database.models.event import TrackingEvent
from src.infrastructure.database.repositories.base import BaseRepository


class EventRepository(BaseRepository[TrackingEvent]):
    def __init__(self, session):
        super().__init__(TrackingEvent, session)

    async def get_by_code(self, code: str) -> Optional[TrackingEvent]:
        query = select(self.model).where(self.model.code == code)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_domain(self, domain: str) -> List[TrackingEvent]:
        query = select(self.model).where(self.model.domain == domain)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_project(self, project_id: int) -> List[TrackingEvent]:
        query = select(self.model).where(self.model.project_id == project_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def list_by_project_filtered(
        self,
        project_id: int,
        q: str | None = None,
        domain: str | None = None,
        owner: str | None = None,
        status: str | None = None,
        governance_status: str | None = None,
        limit: int = 200,
    ) -> List[TrackingEvent]:
        query: Select = select(self.model).where(self.model.project_id == project_id)

        if q:
            q_like = f"%{q.strip()}%"
            query = query.where(
                (self.model.code.ilike(q_like))
                | (self.model.name.ilike(q_like))
                | (self.model.domain.ilike(q_like))
            )
        if domain:
            query = query.where(self.model.domain == domain)
        if owner:
            query = query.where(self.model.owner == owner)
        if status:
            query = query.where(self.model.status == status)
        if governance_status:
            query = query.where(self.model.governance_status == governance_status)

        query = query.order_by(self.model.updated_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())
