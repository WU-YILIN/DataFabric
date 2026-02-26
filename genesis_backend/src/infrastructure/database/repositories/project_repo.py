from typing import Optional
from sqlalchemy import select
from src.infrastructure.database.models.project import Project
from src.infrastructure.database.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    def __init__(self, session):
        super().__init__(Project, session)

    async def get_by_api_key(self, api_key: str) -> Optional[Project]:
        query = select(self.model).where(self.model.api_key == api_key)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Project]:
        query = select(self.model).where(self.model.name == name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_tenant(self, tenant_id: int) -> list[Project]:
        query = select(self.model).where(self.model.tenant_id == tenant_id).order_by(self.model.name.asc())
        result = await self.session.execute(query)
        return list(result.scalars().all())
