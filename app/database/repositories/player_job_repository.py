"""Repository for PlayerJob model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.player_job import PlayerJob


class PlayerJobRepository:
    """Database access for ``player_jobs`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads -----------------------------------------------------------

    async def get_by_player_id(self, player_id: int) -> PlayerJob | None:
        stmt = select(PlayerJob).where(PlayerJob.player_id == player_id)
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, record_id: int) -> PlayerJob | None:
        return await self._session.get(PlayerJob, record_id)

    async def has_job(self, player_id: int) -> bool:
        stmt = select(PlayerJob.id).where(PlayerJob.player_id == player_id).limit(1)
        return (await self._session.execute(stmt)).scalar() is not None

    async def list_page(self, offset: int, limit: int) -> list[PlayerJob]:
        """One page of active workers for the admin panel."""
        stmt = select(PlayerJob).order_by(PlayerJob.id).offset(offset).limit(limit)
        return list((await self._session.execute(stmt)).scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(PlayerJob.id)))
        return int(result.scalar_one())

    async def count_by_job(self, job_id: int) -> int:
        result = await self._session.execute(
            select(func.count(PlayerJob.id)).where(PlayerJob.job_id == job_id)
        )
        return int(result.scalar_one())

    # --- Writes ----------------------------------------------------------

    def add(self, player_job: PlayerJob) -> None:
        self._session.add(player_job)

    async def create(
        self,
        player_id: int,
        job_id: int,
        total_earnings: int = 0,
        started_at: datetime | None = None,
    ) -> PlayerJob:
        record = PlayerJob(
            player_id=player_id,
            job_id=job_id,
            total_earnings=total_earnings,
            started_at=started_at,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def settle(
        self, player_id: int, timestamp: datetime, earnings_to_add: int = 0
    ) -> bool:
        """Reset the work timer after a settlement and accrue paid earnings."""
        stmt = (
            update(PlayerJob)
            .where(PlayerJob.player_id == player_id)
            .values(
                started_at=timestamp,
                last_work_time=timestamp,
                total_earnings=PlayerJob.total_earnings + earnings_to_add,
            )
        )
        result = await self._session.execute(
            stmt, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def update_last_work_time(
        self, player_id: int, timestamp: datetime, earnings_to_add: int = 0
    ) -> bool:
        """Update last work time and total earnings."""
        if earnings_to_add:
            stmt = (
                update(PlayerJob)
                .where(PlayerJob.player_id == player_id)
                .values(
                    last_work_time=timestamp,
                    total_earnings=PlayerJob.total_earnings + earnings_to_add,
                )
            )
        else:
            stmt = (
                update(PlayerJob)
                .where(PlayerJob.player_id == player_id)
                .values(last_work_time=timestamp)
            )
        result = await self._session.execute(
            stmt, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def delete_by_player_id(self, player_id: int) -> bool:
        stmt = delete(PlayerJob).where(PlayerJob.player_id == player_id)
        result = await self._session.execute(
            stmt, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
