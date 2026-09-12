"""Repository for persistent player holdings of USD, gold and coin."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.iran_market_asset import IranMarketAsset
from app.database.models.iran_market_holding import IranMarketHolding


class IranMarketHoldingRepository:
    """Atomic aggregate holding operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_player(self, player_id: int) -> list[tuple[IranMarketHolding, IranMarketAsset]]:
        statement = (
            select(IranMarketHolding, IranMarketAsset)
            .join(IranMarketAsset, IranMarketAsset.id == IranMarketHolding.asset_id)
            .where(IranMarketHolding.owner_player_id == player_id)
            .order_by(IranMarketHolding.id)
        )
        return list((await self._session.execute(statement)).all())

    async def get_by_player_and_asset(
        self, player_id: int, asset_id: int
    ) -> IranMarketHolding | None:
        statement = select(IranMarketHolding).where(
            IranMarketHolding.owner_player_id == player_id,
            IranMarketHolding.asset_id == asset_id,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def add_quantity(
        self, *, player_id: int, asset_id: int, quantity: int
    ) -> IranMarketHolding:
        """Increase a holding with a database-side upsert.

        The arithmetic happens in SQL, so two workers cannot overwrite one
        another's quantity. The caller owns the surrounding transaction.
        """
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("quantity must be a positive integer")
        values = {
            "owner_player_id": player_id,
            "asset_id": asset_id,
            "quantity": quantity,
        }
        dialect = self._session.get_bind().dialect.name
        if dialect == "sqlite":
            statement = sqlite_insert(IranMarketHolding).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["owner_player_id", "asset_id"],
                set_={
                    "quantity": IranMarketHolding.quantity + statement.excluded.quantity,
                    "updated_at": func.now(),
                },
            )
        elif dialect == "postgresql":
            statement = postgres_insert(IranMarketHolding).values(**values)
            statement = statement.on_conflict_do_update(
                index_elements=["owner_player_id", "asset_id"],
                set_={
                    "quantity": IranMarketHolding.quantity + statement.excluded.quantity,
                    "updated_at": func.now(),
                },
            )
        else:  # pragma: no cover - SQLite/PostgreSQL are the supported backends
            holding = await self.get_by_player_and_asset(player_id, asset_id)
            if holding is None:
                holding = IranMarketHolding(**values)
                self._session.add(holding)
            else:
                holding.quantity += quantity
            await self._session.flush()
            return holding

        await self._session.execute(statement)
        holding = await self.get_by_player_and_asset(player_id, asset_id)
        if holding is None:  # pragma: no cover - defensive guard
            raise RuntimeError("market holding upsert did not return a row")
        # The row may already be present in this session's identity map (for
        # example, a caller inspected it before buying again). Refresh it so
        # the returned DTO always contains the database-side increment.
        await self._session.refresh(holding)
        return holding
