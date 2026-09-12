"""Database access for divorce history (``divorce_records``)."""

from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.divorce_record import DivorceRecord


class DivorceRecordRepository:
    """All database operations for the ``divorce_records`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_marriage(self, marriage_id: int) -> DivorceRecord | None:
        statement = (
            select(DivorceRecord)
            .where(DivorceRecord.marriage_id == marriage_id)
            .order_by(DivorceRecord.id.desc())
            .limit(1)
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_by_player(
        self, player_id: int, limit: int = 20, offset: int = 0
    ) -> list[DivorceRecord]:
        statement = (
            select(DivorceRecord)
            .where(
                or_(
                    DivorceRecord.husband_player_id == player_id,
                    DivorceRecord.wife_player_id == player_id,
                )
            )
            .order_by(DivorceRecord.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(statement)).scalars().all())

    def add(self, record: DivorceRecord) -> None:
        self._session.add(record)


__all__ = ["DivorceRecordRepository"]
