"""Repository for immutable Iranian-market history rows."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.iran_market_price_history import IranMarketPriceHistory


class IranMarketPriceHistoryRepository:
    """Database access for price history."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        *,
        asset_id: int,
        previous_price: int | None,
        new_price: int,
        change_amount: int,
        direction: str,
        source: str,
        update_type: str,
        cycle_id: str,
    ) -> IranMarketPriceHistory:
        history = IranMarketPriceHistory(
            asset_id=asset_id,
            previous_price=previous_price,
            new_price=new_price,
            change_amount=change_amount,
            direction=direction,
            source=source,
            update_type=update_type,
            cycle_id=cycle_id,
        )
        self._session.add(history)
        await self._session.flush()
        return history

    async def list_by_asset(
        self, asset_id: int, *, limit: int = 20
    ) -> list[IranMarketPriceHistory]:
        safe_limit = max(1, min(limit, 100))
        statement = (
            select(IranMarketPriceHistory)
            .where(IranMarketPriceHistory.asset_id == asset_id)
            .order_by(IranMarketPriceHistory.recorded_at.desc(), IranMarketPriceHistory.id.desc())
            .limit(safe_limit)
        )
        return list((await self._session.execute(statement)).scalars().all())
