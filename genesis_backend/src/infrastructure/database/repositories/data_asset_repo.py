from sqlalchemy import Select, select

from src.infrastructure.database.models.data_asset import DataAsset
from src.infrastructure.database.repositories.base import BaseRepository


class DataAssetRepository(BaseRepository[DataAsset]):
    def __init__(self, session):
        super().__init__(DataAsset, session)

    async def get_by_project_filtered(
        self,
        project_id: int,
        q: str | None = None,
        asset_type: str | None = None,
        domain: str | None = None,
        source_system: str | None = None,
        owner: str | None = None,
        status: str | None = None,
        limit: int = 500,
    ) -> list[DataAsset]:
        query: Select = select(self.model).where(self.model.project_id == project_id)
        if q:
            q_like = f"%{q.strip()}%"
            query = query.where(
                (self.model.name.ilike(q_like))
                | (self.model.object_name.ilike(q_like))
                | (self.model.domain.ilike(q_like))
            )
        if asset_type:
            query = query.where(self.model.asset_type == asset_type)
        if domain:
            query = query.where(self.model.domain == domain)
        if source_system:
            query = query.where(self.model.source_system == source_system)
        if owner:
            query = query.where(self.model.owner == owner)
        if status:
            query = query.where(self.model.status == status)
        query = query.order_by(self.model.updated_at.desc()).limit(limit)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_by_project_and_object(
        self,
        project_id: int,
        asset_type: str,
        object_name: str,
    ) -> DataAsset | None:
        query = select(self.model).where(
            self.model.project_id == project_id,
            self.model.asset_type == asset_type,
            self.model.object_name == object_name,
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
