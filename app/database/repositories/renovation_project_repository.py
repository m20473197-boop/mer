"""Repository for the ``renovation_projects`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.renovation_project import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    RenovationProject,
)


class RenovationProjectRepository:
    """All database operations for renovation projects."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, project_id: int) -> RenovationProject | None:
        return await self._session.get(RenovationProject, project_id)

    async def count_in_progress(self) -> int:
        """How many renovations are currently running (admin dashboard)."""
        result = await self._session.execute(
            select(func.count(RenovationProject.id)).where(
                RenovationProject.status == STATUS_IN_PROGRESS
            )
        )
        return int(result.scalar_one())

    async def get_active_by_house(self, house_id: int) -> RenovationProject | None:
        statement = select(RenovationProject).where(
            RenovationProject.house_id == house_id,
            RenovationProject.status == STATUS_IN_PROGRESS,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_by_owner(
        self, player_id: int, limit: int = 10
    ) -> list[RenovationProject]:
        statement = (
            select(RenovationProject)
            .where(RenovationProject.owner_player_id == player_id)
            .order_by(RenovationProject.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_house(
        self, house_id: int, limit: int = 10
    ) -> list[RenovationProject]:
        statement = (
            select(RenovationProject)
            .where(RenovationProject.house_id == house_id)
            .order_by(RenovationProject.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_due(self, now: datetime) -> list[RenovationProject]:
        statement = select(RenovationProject).where(
            RenovationProject.status == STATUS_IN_PROGRESS,
            RenovationProject.completes_at <= now,
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        house_id: int,
        owner_player_id: int,
        renovation_type: str,
        title: str,
        description: str,
        cost: int,
        started_at: datetime,
        duration_seconds: int,
        completes_at: datetime,
    ) -> RenovationProject:
        project = RenovationProject(
            house_id=house_id,
            owner_player_id=owner_player_id,
            renovation_type=renovation_type,
            title=title,
            description=description,
            cost=cost,
            status=STATUS_IN_PROGRESS,
            started_at=started_at,
            duration_seconds=duration_seconds,
            completes_at=completes_at,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def claim_completion(self, project_id: int, when: datetime) -> bool:
        """Atomically mark an in-progress renovation completed."""
        statement = (
            update(RenovationProject)
            .where(
                RenovationProject.id == project_id,
                RenovationProject.status == STATUS_IN_PROGRESS,
            )
            .values(status=STATUS_COMPLETED, completed_at=when)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
