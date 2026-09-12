"""Repository for the ``market_price_ticks`` table (price history)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.market_price_tick import MarketPriceTick


class MarketPriceTickRepository:
    """All database operations for asset price history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def list_by_asset(
        self, asset_id: int, limit: int = 20
    ) -> list[MarketPriceTick]:
        """Most recent ticks of one asset, newest first."""
        statement = (
            select(MarketPriceTick)
            .where(MarketPriceTick.asset_id == asset_id)
            .order_by(MarketPriceTick.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes ------------------------------------------------------------

    async def add(self, asset_id: int, price: int) -> MarketPriceTick:
        tick = MarketPriceTick(asset_id=asset_id, price=price)
        self._session.add(tick)
        await self._session.flush()
        return tick

    async def prune_older_than(self, cutoff: datetime) -> int:
        """Delete ticks recorded before ``cutoff``; returns rows removed."""
        statement = delete(MarketPriceTick).where(
            MarketPriceTick.created_at < cutoff
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return int(result.rowcount or 0)
