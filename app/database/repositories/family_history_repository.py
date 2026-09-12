"""Database access for the family timeline (``family_history``).

Append-only audit trail of family milestones, written inside the same
transaction as the state change it describes.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.family_history import FamilyHistory


class FamilyHistoryRepository:
    """All database operations for the ``family_history`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_player(
        self, player_id: int, limit: int = 30, offset: int = 0
    ) -> list[FamilyHistory]:
        statement = (
            select(FamilyHistory)
            .where(FamilyHistory.player_id == player_id)
            .order_by(FamilyHistory.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def count_by_player(self, player_id: int, event_type: str | None = None) -> int:
        conditions = [FamilyHistory.player_id == player_id]
        if event_type is not None:
            conditions.append(FamilyHistory.event_type == event_type)
        statement = select(func.count(FamilyHistory.id)).where(*conditions)
        return int((await self._session.execute(statement)).scalar_one() or 0)

    async def add(
        self,
        *,
        player_id: int,
        event_type: str,
        marriage_id: int | None = None,
        other_player_id: int | None = None,
        amount: int = 0,
        quality_delta: int = 0,
        social_penalty: int = 0,
        note: str = "",
    ) -> FamilyHistory:
        row = FamilyHistory(
            player_id=player_id,
            event_type=event_type,
            marriage_id=marriage_id,
            other_player_id=other_player_id,
            amount=amount,
            quality_delta=quality_delta,
            social_penalty=social_penalty,
            note=note[:256],
        )
        self._session.add(row)
        await self._session.flush()
        return row


__all__ = ["FamilyHistoryRepository"]
