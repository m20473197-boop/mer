"""Repository for the ``land_transactions`` table (land market audit)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.land_transaction import LandTransaction


class LandTransactionRepository:
    """All database operations for land money transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, transaction_id: int) -> LandTransaction | None:
        return await self._session.get(LandTransaction, transaction_id)

    async def list_by_payer(
        self, player_id: int, limit: int = 50
    ) -> list[LandTransaction]:
        statement = (
            select(LandTransaction)
            .where(LandTransaction.payer_player_id == player_id)
            .order_by(LandTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 20) -> list[LandTransaction]:
        """Most recent land money movements (admin / trading views)."""
        statement = (
            select(LandTransaction)
            .order_by(LandTransaction.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_land(self, land_id: int, limit: int = 50) -> list[LandTransaction]:
        statement = (
            select(LandTransaction)
            .where(LandTransaction.land_id == land_id)
            .order_by(LandTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    # --- Writes -----------------------------------------------------------

    async def create(
        self,
        *,
        payer_player_id: int,
        amount: int,
        transaction_type: str,
        land_id: int,
        payee_player_id: int | None = None,
        note: str = "",
    ) -> LandTransaction:
        transaction = LandTransaction(
            payer_player_id=payer_player_id,
            payee_player_id=payee_player_id,
            amount=amount,
            transaction_type=transaction_type,
            land_id=land_id,
            note=note,
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction
