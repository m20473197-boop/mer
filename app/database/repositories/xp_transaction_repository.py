"""Repository for XPTransaction history."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.xp_transaction import XPTransaction


class XPTransactionRepository:
    """Database access for ``xp_transactions`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, player_id: int, amount: int, reason: str) -> XPTransaction:
        """Stage a new XP transaction; caller commits."""
        tx = XPTransaction(player_id=player_id, amount=amount, reason=reason)
        self._session.add(tx)
        return tx

    async def list_by_player(
        self, player_id: int, limit: int = 50, offset: int = 0
    ) -> list[XPTransaction]:
        stmt = (
            select(XPTransaction)
            .where(XPTransaction.player_id == player_id)
            .order_by(XPTransaction.created_at.desc(), XPTransaction.id.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_by_player(self, player_id: int) -> int:
        stmt = select(XPTransaction.id).where(XPTransaction.player_id == player_id)
        result = await self._session.execute(stmt)
        return len(result.scalars().all())

    async def get_all_by_player(self, player_id: int) -> list[XPTransaction]:
        stmt = (
            select(XPTransaction)
            .where(XPTransaction.player_id == player_id)
            .order_by(XPTransaction.created_at.asc(), XPTransaction.id.asc())
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())
