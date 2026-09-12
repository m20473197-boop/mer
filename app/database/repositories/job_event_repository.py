"""Repository for the JobEvent model (settlement audit trail)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.job_event import JobEvent


class JobEventRepository:
    """Database access for ``job_events`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, **kwargs) -> JobEvent:
        record = JobEvent(**kwargs)
        self._session.add(record)
        return record

    async def list_by_player(
        self, player_id: int, limit: int = 50, offset: int = 0
    ) -> list[JobEvent]:
        stmt = (
            select(JobEvent)
            .where(JobEvent.player_id == player_id)
            .order_by(JobEvent.created_at.desc(), JobEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_player(self, player_id: int) -> int:
        stmt = select(JobEvent.id).where(JobEvent.player_id == player_id)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())
