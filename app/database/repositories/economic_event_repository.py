"""Repository for the ``economic_events`` table (market events / crises)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.economic_event import EconomicEvent


class EconomicEventRepository:
    """All database operations for economic events."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, event_id: int) -> EconomicEvent | None:
        return await self._session.get(EconomicEvent, event_id)

    async def list_live(self, now: datetime) -> list[EconomicEvent]:
        """Events that affect prices right now (active + inside window)."""
        statement = (
            select(EconomicEvent)
            .where(
                EconomicEvent.is_active.is_(True),
                EconomicEvent.starts_at <= now,
                EconomicEvent.ends_at > now,
            )
            .order_by(EconomicEvent.id)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_live(self, now: datetime) -> int:
        result = await self._session.execute(
            select(func.count(EconomicEvent.id)).where(
                EconomicEvent.is_active.is_(True),
                EconomicEvent.starts_at <= now,
                EconomicEvent.ends_at > now,
            )
        )
        return int(result.scalar_one())

    async def list_page(self, offset: int, limit: int) -> list[EconomicEvent]:
        """All events, newest first (admin panel)."""
        statement = (
            select(EconomicEvent)
            .order_by(EconomicEvent.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(EconomicEvent.id)))
        return int(result.scalar_one())

    # --- Writes ------------------------------------------------------------

    async def create(
        self,
        *,
        name: str,
        description: str,
        multiplier: float,
        starts_at: datetime,
        ends_at: datetime,
        created_by: int,
    ) -> EconomicEvent:
        event = EconomicEvent(
            name=name,
            description=description,
            multiplier=multiplier,
            starts_at=starts_at,
            ends_at=ends_at,
            is_active=True,
            created_by=created_by,
        )
        self._session.add(event)
        await self._session.flush()
        return event

    async def deactivate(self, event_id: int) -> bool:
        """End an event early. Returns ``False`` when missing/already off."""
        statement = (
            update(EconomicEvent)
            .where(
                EconomicEvent.id == event_id,
                EconomicEvent.is_active.is_(True),
            )
            .values(is_active=False)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def deactivate_expired(self, now: datetime) -> int:
        """Switch off every event whose window has passed; returns the count."""
        statement = (
            update(EconomicEvent)
            .where(
                EconomicEvent.is_active.is_(True),
                EconomicEvent.ends_at <= now,
            )
            .values(is_active=False)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return int(result.rowcount or 0)
