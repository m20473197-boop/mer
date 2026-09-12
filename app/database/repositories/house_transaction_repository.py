"""Repository for the ``house_transactions`` table (housing money audit)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.house_transaction import HouseTransaction


class HouseTransactionRepository:
    """All database operations for housing money transactions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ------------------------------------------------------------

    async def get_by_id(self, transaction_id: int) -> HouseTransaction | None:
        return await self._session.get(HouseTransaction, transaction_id)

    async def list_by_payer(
        self, player_id: int, limit: int = 50
    ) -> list[HouseTransaction]:
        statement = (
            select(HouseTransaction)
            .where(HouseTransaction.payer_player_id == player_id)
            .order_by(HouseTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_payee(
        self, player_id: int, limit: int = 50
    ) -> list[HouseTransaction]:
        statement = (
            select(HouseTransaction)
            .where(HouseTransaction.payee_player_id == player_id)
            .order_by(HouseTransaction.created_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_recent(self, limit: int = 20) -> list[HouseTransaction]:
        """Most recent housing money movements (admin / trading views)."""
        statement = (
            select(HouseTransaction)
            .order_by(HouseTransaction.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def list_by_house(
        self, house_id: int, limit: int = 50
    ) -> list[HouseTransaction]:
        statement = (
            select(HouseTransaction)
            .where(HouseTransaction.house_id == house_id)
            .order_by(HouseTransaction.created_at.desc())
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
        payee_player_id: int | None = None,
        house_id: int | None = None,
        contract_id: int | None = None,
        note: str = "",
    ) -> HouseTransaction:
        transaction = HouseTransaction(
            payer_player_id=payer_player_id,
            payee_player_id=payee_player_id,
            amount=amount,
            transaction_type=transaction_type,
            house_id=house_id,
            contract_id=contract_id,
            note=note,
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction
