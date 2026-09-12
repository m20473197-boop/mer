"""Repository for JobHistory model."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.job_history import JobHistory


class JobHistoryRepository:
    """Database access for ``job_history`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, player_id: int, job_id: int, income: int) -> JobHistory:
        record = JobHistory(player_id=player_id, job_id=job_id, income=income, amount=income)
        self._session.add(record)
        return record

    async def list_by_player(
        self, player_id: int, limit: int = 50, offset: int = 0
    ) -> list[JobHistory]:
        stmt = (
            select(JobHistory)
            .where(JobHistory.player_id == player_id)
            .order_by(JobHistory.created_at.desc(), JobHistory.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_player(self, player_id: int) -> int:
        stmt = select(JobHistory.id).where(JobHistory.player_id == player_id)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
