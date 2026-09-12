"""Repository for LevelUpHistory."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.level_up_history import LevelUpHistory


class LevelUpRepository:
    """Database access for ``level_up_history`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, player_id: int, old_level: int, new_level: int) -> LevelUpHistory:
        """Stage a new level-up record; caller commits."""
        record = LevelUpHistory(
            player_id=player_id, old_level=old_level, new_level=new_level
        )
        self._session.add(record)
        return record

    async def list_by_player(
        self, player_id: int, limit: int = 50, offset: int = 0
    ) -> list[LevelUpHistory]:
        stmt = (
            select(LevelUpHistory)
            .where(LevelUpHistory.player_id == player_id)
            .order_by(LevelUpHistory.created_at.desc(), LevelUpHistory.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_all_by_player(self, player_id: int) -> list[LevelUpHistory]:
        stmt = (
            select(LevelUpHistory)
            .where(LevelUpHistory.player_id == player_id)
            .order_by(LevelUpHistory.created_at.asc(), LevelUpHistory.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
