from sqlalchemy import delete, select

from src.infrastructure.database.models.data_asset_lineage import DataAssetLineage
from src.infrastructure.database.repositories.base import BaseRepository


class DataAssetLineageRepository(BaseRepository[DataAssetLineage]):
    def __init__(self, session):
        super().__init__(DataAssetLineage, session)

    async def get_upstream(self, project_id: int, asset_id: int) -> list[DataAssetLineage]:
        query = select(self.model).where(
            self.model.project_id == project_id,
            self.model.downstream_asset_id == asset_id,
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_downstream(self, project_id: int, asset_id: int) -> list[DataAssetLineage]:
        query = select(self.model).where(
            self.model.project_id == project_id,
            self.model.upstream_asset_id == asset_id,
        )
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def replace_upstream(self, project_id: int, asset_id: int, upstream_asset_ids: list[int]) -> None:
        await self.session.execute(
            delete(self.model).where(
                self.model.project_id == project_id,
                self.model.downstream_asset_id == asset_id,
            )
        )
        for upstream_id in sorted(set(upstream_asset_ids)):
            if upstream_id == asset_id:
                continue
            await self.create(
                {
                    "project_id": project_id,
                    "upstream_asset_id": upstream_id,
                    "downstream_asset_id": asset_id,
                    "relation_type": "DERIVED_FROM",
                }
            )

    async def replace_downstream(self, project_id: int, asset_id: int, downstream_asset_ids: list[int]) -> None:
        await self.session.execute(
            delete(self.model).where(
                self.model.project_id == project_id,
                self.model.upstream_asset_id == asset_id,
            )
        )
        for downstream_id in sorted(set(downstream_asset_ids)):
            if downstream_id == asset_id:
                continue
            await self.create(
                {
                    "project_id": project_id,
                    "upstream_asset_id": asset_id,
                    "downstream_asset_id": downstream_id,
                    "relation_type": "DERIVED_FROM",
                }
            )
