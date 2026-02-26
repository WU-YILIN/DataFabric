from sqlalchemy import select

from src.infrastructure.database.models.event_change_log import EventChangeLog
from src.infrastructure.database.repositories.base import BaseRepository


class EventChangeLogRepository(BaseRepository[EventChangeLog]):
    def __init__(self, session):
        super().__init__(EventChangeLog, session)

    async def get_by_event(self, event_id: int) -> list[EventChangeLog]:
        query = (
            select(self.model)
            .where(self.model.event_id == event_id)
            .order_by(self.model.created_at.desc())
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
