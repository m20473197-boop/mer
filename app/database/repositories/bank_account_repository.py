"""Persistence operations for one-to-one bank accounts."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.bank_account import BANK_ACCOUNT_ACTIVE, BankAccount

_CARD_PREFIX = "621986"
_CARD_SUFFIX_MODULUS = 10_000_000_000


def card_number_for_player(player_id: int) -> str:
    """Return the stable 16-digit card seed for a player.

    A player's internal id is immutable, so this seed is deterministic and
    means account provisioning can be retried without regenerating a card.
    The repository still checks the unique database constraint before insert.
    """

    suffix = abs(int(player_id)) % _CARD_SUFFIX_MODULUS
    return f"{_CARD_PREFIX}{suffix:010d}"


class BankAccountRepository:
    """All database access for ``bank_accounts``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, account_id: int, *, for_update: bool = False) -> BankAccount | None:
        statement = select(BankAccount).where(BankAccount.id == account_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_player_id(
        self, player_id: int, *, for_update: bool = False
    ) -> BankAccount | None:
        statement = select(BankAccount).where(BankAccount.player_id == player_id)
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def get_by_card_number(
        self, card_number: str, *, for_update: bool = False
    ) -> BankAccount | None:
        statement = select(BankAccount).where(
            BankAccount.card_number == card_number,
            BankAccount.status == BANK_ACCOUNT_ACTIVE,
        )
        if for_update:
            statement = statement.with_for_update()
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_all(self) -> list[BankAccount]:
        result = await self._session.execute(
            select(BankAccount).where(BankAccount.status == BANK_ACCOUNT_ACTIVE).order_by(BankAccount.id)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        from sqlalchemy import func

        result = await self._session.execute(select(func.count(BankAccount.id)))
        return int(result.scalar_one())

    async def ensure_for_player(self, player_id: int) -> tuple[BankAccount, bool]:
        """Return the account, creating it once when absent.

        The unique ``player_id`` and ``card_number`` constraints are the final
        concurrency guard. Normal provisioning is idempotent because the
        existing row is returned unchanged, including its original card.
        """

        existing = await self.get_by_player_id(player_id)
        if existing is not None:
            return existing, False
        # The normal seed is deterministic. If an extremely large player id
        # collides after the ten-digit suffix wrap (or a legacy row already
        # occupies it), advance the numeric suffix before the first insert.
        seed = abs(int(player_id)) % _CARD_SUFFIX_MODULUS
        card_number = card_number_for_player(player_id)
        for offset in range(_CARD_SUFFIX_MODULUS):
            candidate = f"{_CARD_PREFIX}{(seed + offset) % _CARD_SUFFIX_MODULUS:010d}"
            taken = await self._session.execute(
                select(BankAccount.id).where(BankAccount.card_number == candidate).limit(1)
            )
            if taken.scalar_one_or_none() is None:
                card_number = candidate
                break
        account = BankAccount(
            player_id=player_id,
            balance=0,
            card_number=card_number,
            status=BANK_ACCOUNT_ACTIVE,
        )
        self._session.add(account)
        await self._session.flush()
        return account, True

    async def add_balance(self, account_id: int, amount: int) -> bool:
        """Increase an account's bank balance atomically."""

        statement = (
            update(BankAccount)
            .where(BankAccount.id == account_id, BankAccount.status == BANK_ACCOUNT_ACTIVE)
            .values(balance=BankAccount.balance + amount, updated_at=func.now())
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def remove_balance_if_enough(self, account_id: int, amount: int) -> bool:
        """Debit only when the bank balance covers the amount."""

        statement = (
            update(BankAccount)
            .where(
                BankAccount.id == account_id,
                BankAccount.status == BANK_ACCOUNT_ACTIVE,
                BankAccount.balance >= amount,
            )
            .values(balance=BankAccount.balance - amount, updated_at=func.now())
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def claim_interest_processing(
        self,
        account_id: int,
        previous_last_processed_at: datetime | None,
        processed_at: datetime,
    ) -> bool:
        """Claim an account's interest work with a compare-and-set update.

        The update locks the account row on databases that support row locks;
        the old timestamp predicate also makes a second worker harmless after
        the first worker commits. The caller must keep this transaction open
        while applying the interest and inserting its ledger rows.
        """

        timestamp_condition = (
            BankAccount.last_interest_processed_at.is_(None)
            if previous_last_processed_at is None
            else BankAccount.last_interest_processed_at == previous_last_processed_at
        )
        statement = (
            update(BankAccount)
            .where(
                BankAccount.id == account_id,
                BankAccount.status == BANK_ACCOUNT_ACTIVE,
                timestamp_condition,
            )
            .values(last_interest_processed_at=processed_at, updated_at=func.now())
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def set_balance_and_last_interest(
        self, account_id: int, balance: int, processed_at: datetime
    ) -> bool:
        """Store the final balance after a claimed interest run."""

        statement = (
            update(BankAccount)
            .where(BankAccount.id == account_id, BankAccount.status == BANK_ACCOUNT_ACTIVE)
            .values(
                balance=balance,
                last_interest_processed_at=processed_at,
                updated_at=func.now(),
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)
