"""Repository for the ``market_assets`` table (economy assets)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.market_asset import MarketAsset


class MarketAssetRepository:
    """All database operations for market assets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_code(self, code: str) -> MarketAsset | None:
        statement = select(MarketAsset).where(MarketAsset.code == code)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> list[MarketAsset]:
        statement = select(MarketAsset).order_by(MarketAsset.id)
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes ------------------------------------------------------------

    async def create(
        self, *, code: str, name: str, category: str, price: int
    ) -> MarketAsset:
        asset = MarketAsset(code=code, name=name, category=category, price=price)
        self._session.add(asset)
        await self._session.flush()
        return asset

    async def update_price(self, code: str, price: int) -> MarketAsset | None:
        """Set a new live price; ``None`` when the asset does not exist."""
        asset = await self.get_by_code(code)
        if asset is None:
            return None
        asset.price = price
        self._session.add(asset)
        await self._session.flush()
        return asset
