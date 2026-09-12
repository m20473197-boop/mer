"""Persistence operations for bank history rows."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.bank_transaction import (
    BANK_TRANSACTION_DEPOSIT,
    BANK_TRANSACTION_INTEREST,
    BANK_TRANSACTION_TRANSFER_RECEIVED,
    BANK_TRANSACTION_TRANSFER_SENT,
    BANK_TRANSACTION_WITHDRAWAL,
    BankTransaction,
)


class BankTransactionRepository:
    """All database access for ``bank_transactions``."""

    @staticmethod
    def _history_condition(account_id: int):
        # A transfer has two rows with the same sender/receiver pair. The
        # transaction type gives each account only its own directional row.
        return or_(
            and_(
                BankTransaction.transaction_type.in_(
                    (BANK_TRANSACTION_DEPOSIT, BANK_TRANSACTION_INTEREST, BANK_TRANSACTION_TRANSFER_RECEIVED)
                ),
                BankTransaction.receiver_account_id == account_id,
            ),
            and_(
                BankTransaction.transaction_type.in_(
                    (BANK_TRANSACTION_WITHDRAWAL, BANK_TRANSACTION_TRANSFER_SENT)
                ),
                BankTransaction.sender_account_id == account_id,
            ),
        )

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, transaction: BankTransaction) -> None:
        self._session.add(transaction)

    async def create(
        self,
        *,
        transaction_type: str,
        amount: int,
        status: str,
        sender_account_id: int | None,
        receiver_account_id: int | None,
        sender_player_id: int | None,
        receiver_player_id: int | None,
        reference_id: str | None,
        description: str,
        created_at: datetime | None = None,
    ) -> BankTransaction:
        transaction = BankTransaction(
            transaction_type=transaction_type,
            amount=amount,
            status=status,
            sender_account_id=sender_account_id,
            receiver_account_id=receiver_account_id,
            sender_player_id=sender_player_id,
            receiver_player_id=receiver_player_id,
            reference_id=reference_id,
            description=description,
            created_at=created_at,
        )
        self._session.add(transaction)
        await self._session.flush()
        return transaction

    async def get_by_reference_and_type(
        self, reference_id: str, transaction_type: str
    ) -> BankTransaction | None:
        statement = select(BankTransaction).where(
            BankTransaction.reference_id == reference_id,
            BankTransaction.transaction_type == transaction_type,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_for_account_page(
        self, account_id: int, *, offset: int, limit: int
    ) -> list[BankTransaction]:
        statement = (
            select(BankTransaction)
            .where(self._history_condition(account_id))
            .order_by(BankTransaction.created_at.desc(), BankTransaction.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(statement)
        return list(result.scalars().all())

    async def count_for_account(self, account_id: int) -> int:
        result = await self._session.execute(
            select(func.count(BankTransaction.id)).where(
                self._history_condition(account_id)
            )
        )
        return int(result.scalar_one())
