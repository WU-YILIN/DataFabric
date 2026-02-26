from typing import Optional

from sqlalchemy import select

from src.infrastructure.database.models.user import User
from src.infrastructure.database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    def __init__(self, session):
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        query = select(self.model).where(self.model.email == email)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()
