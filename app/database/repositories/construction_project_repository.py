"""Repository for the ``construction_projects`` table."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.construction_project import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    ConstructionProject,
)


class ConstructionProjectRepository:
    """All database operations for construction projects."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, project_id: int) -> ConstructionProject | None:
        return await self._session.get(ConstructionProject, project_id)

    async def get_active_by_land(self, land_id: int) -> ConstructionProject | None:
        statement = select(ConstructionProject).where(
            ConstructionProject.land_id == land_id,
            ConstructionProject.status == STATUS_IN_PROGRESS,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_by_owner(
        self, player_id: int, limit: int = 10
    ) -> list[ConstructionProject]:
        statement = (
            select(ConstructionProject)
            .where(ConstructionProject.owner_player_id == player_id)
            .order_by(ConstructionProject.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_in_progress(self) -> int:
        """How many constructions are currently running (admin dashboard)."""
        result = await self._session.execute(
            select(func.count(ConstructionProject.id)).where(
                ConstructionProject.status == STATUS_IN_PROGRESS
            )
        )
        return int(result.scalar_one())

    async def list_due(self, now: datetime) -> list[ConstructionProject]:
        statement = select(ConstructionProject).where(
            ConstructionProject.status == STATUS_IN_PROGRESS,
            ConstructionProject.completes_at <= now,
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        land_id: int,
        owner_player_id: int,
        building_type: str,
        floors: int,
        area_sqm: int,
        bedrooms: int,
        bathrooms: int,
        living_rooms: int,
        quality: str,
        kitchen_type: str,
        parking: bool,
        elevator: bool,
        storage: bool,
        cost_total: int,
        started_at: datetime,
        duration_seconds: int,
        completes_at: datetime,
    ) -> ConstructionProject:
        project = ConstructionProject(
            land_id=land_id,
            owner_player_id=owner_player_id,
            building_type=building_type,
            floors=floors,
            area_sqm=area_sqm,
            bedrooms=bedrooms,
            bathrooms=bathrooms,
            living_rooms=living_rooms,
            quality=quality,
            kitchen_type=kitchen_type,
            parking=parking,
            elevator=elevator,
            storage=storage,
            cost_total=cost_total,
            status=STATUS_IN_PROGRESS,
            started_at=started_at,
            duration_seconds=duration_seconds,
            completes_at=completes_at,
        )
        self._session.add(project)
        await self._session.flush()
        return project

    async def claim_completion(self, project_id: int, when: datetime) -> bool:
        """Atomically mark an in-progress project completed.

        Returns ``True`` only for the single caller that wins the claim, so
        concurrent settlers can never double-create the house.
        """
        statement = (
            update(ConstructionProject)
            .where(
                ConstructionProject.id == project_id,
                ConstructionProject.status == STATUS_IN_PROGRESS,
            )
            .values(status=STATUS_COMPLETED, completed_at=when)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def mark_cancelled(self, project_id: int, when: datetime) -> bool:
        statement = (
            update(ConstructionProject)
            .where(
                ConstructionProject.id == project_id,
                ConstructionProject.status == STATUS_IN_PROGRESS,
            )
            .values(status="cancelled", completed_at=when)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def set_house(self, project_id: int, house_id: int) -> bool:
        """Link the produced house to its project (on completion)."""
        statement = (
            update(ConstructionProject)
            .where(ConstructionProject.id == project_id)
            .values(house_id=house_id)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
