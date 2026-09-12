"""Repository for the four ``iran_market_assets`` rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import insert, select, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.iran_market_asset import IranMarketAsset


class IranMarketAssetRepository:
    """Database access for player-facing Iranian market assets."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_code(self, code: str) -> IranMarketAsset | None:
        statement = select(IranMarketAsset).where(IranMarketAsset.code == code)
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_by_codes(self, codes: tuple[str, ...]) -> list[IranMarketAsset]:
        statement = (
            select(IranMarketAsset)
            .where(IranMarketAsset.code.in_(codes), IranMarketAsset.is_active.is_(True))
            .order_by(IranMarketAsset.id)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def create(
        self,
        *,
        code: str,
        display_name: str,
        category: str,
        base_value: int | None,
        current_price: int | None,
        is_active: bool,
    ) -> IranMarketAsset:
        asset, _ = await self.create_if_missing(
            code=code,
            display_name=display_name,
            category=category,
            base_value=base_value,
            current_price=current_price,
            is_active=is_active,
        )
        return asset

    async def create_if_missing(
        self,
        *,
        code: str,
        display_name: str,
        category: str,
        base_value: int | None,
        current_price: int | None,
        is_active: bool,
    ) -> tuple[IranMarketAsset, bool]:
        """Insert one catalog row without racing another startup worker."""
        values = {
            "code": code,
            "display_name": display_name,
            "category": category,
            "base_value": base_value,
            "current_price": current_price,
            "is_active": is_active,
        }
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "sqlite":
            statement = sqlite_insert(IranMarketAsset).values(**values).prefix_with(
                "OR IGNORE"
            )
        elif dialect_name == "postgresql":
            statement = postgres_insert(IranMarketAsset).values(**values).on_conflict_do_nothing(
                index_elements=["code"]
            )
        else:  # pragma: no cover - project supports SQLite/PostgreSQL
            statement = insert(IranMarketAsset).values(**values)
        result = await self._session.execute(statement)
        asset = await self.get_by_code(code)
        if asset is None:  # pragma: no cover - defensive guard
            raise RuntimeError(f"Iran market asset {code} could not be initialized")
        return asset, bool(result.rowcount)

    async def mark_attempted(
        self, codes: tuple[str, ...], attempted_at: datetime
    ) -> int:
        statement = (
            update(IranMarketAsset)
            .where(IranMarketAsset.code.in_(codes))
            .values(last_attempted_update=attempted_at)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return int(result.rowcount or 0)

    async def update_quote(
        self,
        asset: IranMarketAsset,
        *,
        new_price: int,
        updated_at: datetime,
    ) -> IranMarketAsset:
        """Move current→previous and store a validated new price."""
        asset.previous_price = asset.current_price
        asset.current_price = new_price
        asset.last_successful_update = updated_at
        self._session.add(asset)
        await self._session.flush()
        return asset
