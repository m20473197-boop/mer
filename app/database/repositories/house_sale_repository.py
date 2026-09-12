"""Repository for the ``house_sales`` table (completed purchases audit)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.house_sale import HouseSale


class HouseSaleRepository:
    """All database operations for completed house sales."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, sale_id: int) -> HouseSale | None:
        return await self._session.get(HouseSale, sale_id)

    async def list_by_buyer(self, player_id: int, limit: int = 50) -> list[HouseSale]:
        statement = (
            select(HouseSale)
            .where(HouseSale.buyer_player_id == player_id)
            .order_by(HouseSale.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_seller(self, player_id: int, limit: int = 50) -> list[HouseSale]:
        statement = (
            select(HouseSale)
            .where(HouseSale.seller_player_id == player_id)
            .order_by(HouseSale.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_recent(self, offset: int = 0, limit: int = 20) -> list[HouseSale]:
        """Most recent completed sales (admin / trading views)."""
        statement = (
            select(HouseSale)
            .order_by(HouseSale.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self._session.execute(select(func.count(HouseSale.id)))
        return int(result.scalar_one())

    async def list_by_house(self, house_id: int, limit: int = 50) -> list[HouseSale]:
        statement = (
            select(HouseSale)
            .where(HouseSale.house_id == house_id)
            .order_by(HouseSale.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        house_id: int,
        buyer_player_id: int,
        price: int,
        seller_player_id: int | None = None,
        listing_id: int | None = None,
    ) -> HouseSale:
        sale = HouseSale(
            house_id=house_id,
            seller_player_id=seller_player_id,
            buyer_player_id=buyer_player_id,
            price=price,
            listing_id=listing_id,
        )
        self._session.add(sale)
        await self._session.flush()
        return sale
