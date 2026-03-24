from collections.abc import Iterable

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models.analysis_plan import AnalysisPlan
from src.infrastructure.database.repositories.base import BaseRepository


class AnalysisPlanRepository(BaseRepository[AnalysisPlan]):
    def __init__(self, session: AsyncSession):
        super().__init__(AnalysisPlan, session)

    async def list_by_project(self, project_id: int) -> list[AnalysisPlan]:
        result = await self.session.execute(
            select(AnalysisPlan)
            .where(AnalysisPlan.project_id == project_id)
            .order_by(AnalysisPlan.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_by_project(self, plan_id: int, project_id: int) -> AnalysisPlan | None:
        result = await self.session.execute(
            select(AnalysisPlan).where(
                AnalysisPlan.id == plan_id,
                AnalysisPlan.project_id == project_id,
            )
        )
        return result.scalar_one_or_none()

    async def transition_status_if_current_in(
        self,
        *,
        plan_id: int,
        project_id: int,
        allowed_current_statuses: Iterable[str],
        next_status: str,
    ) -> bool:
        result = await self.session.execute(
            update(AnalysisPlan)
            .where(
                AnalysisPlan.id == plan_id,
                AnalysisPlan.project_id == project_id,
                AnalysisPlan.status.in_(tuple(allowed_current_statuses)),
            )
            .values(status=next_status, updated_at=func.now())
        )
        return bool(result.rowcount)
