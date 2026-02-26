from sqlalchemy import select

from src.infrastructure.database.models.data_asset_change_log import DataAssetChangeLog
from src.infrastructure.database.repositories.base import BaseRepository


class DataAssetChangeLogRepository(BaseRepository[DataAssetChangeLog]):
    def __init__(self, session):
        super().__init__(DataAssetChangeLog, session)

    async def get_by_asset(self, asset_id: int, limit: int = 100) -> list[DataAssetChangeLog]:
        query = (
            select(self.model)
            .where(self.model.asset_id == asset_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())
