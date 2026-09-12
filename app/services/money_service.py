"""Money/wallet service.

All balances are exact integers (Toman) — floating point is never used for
money. Handlers must not manipulate money values directly; everything goes
through this service so that future features (player transfers, transaction
history, banks, loans, investments, markets) can be built on one solid base.

Removals are atomic: the sufficiency check and the subtraction happen in a
single SQL statement, so the balance can never go below zero.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.repositories.player_repository import PlayerRepository
from app.game.player.dto import MoneyChangeResult
from app.game.shared.errors import (
    InsufficientFundsError,
    InvalidAmountError,
    PlayerNotFoundError,
)

logger = logging.getLogger(__name__)


class MoneyService:
    """Basic wallet operations on exact integer balances."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    # --- Use cases ---------------------------------------------------------

    async def get_balance(self, player_id: int) -> int:
        """Current balance in Toman.

        Raises:
            PlayerNotFoundError: If the player does not exist.
        """
        async with self._session_factory() as session:
            money = await PlayerRepository(session).get_money(player_id)
        if money is None:
            raise PlayerNotFoundError(f"player_id={player_id} not found")
        return money

    async def has_enough(self, player_id: int, amount: int) -> bool:
        """Whether the player can afford ``amount``.

        Raises:
            InvalidAmountError: If ``amount`` is negative.
            PlayerNotFoundError: If the player does not exist.
        """
        if amount < 0:
            raise InvalidAmountError("amount must be non-negative")
        return await self.get_balance(player_id) >= amount

    async def add_money(self, player_id: int, amount: int) -> MoneyChangeResult:
        """Credit the wallet.

        Raises:
            InvalidAmountError: If ``amount`` is not a positive integer.
            PlayerNotFoundError: If the player does not exist.
        """
        if amount <= 0:
            raise InvalidAmountError("amount must be a positive integer")

        async with self._session_factory() as session:
            repository = PlayerRepository(session)
            if not await repository.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            await repository.add_money(player_id, amount)
            balance_after = await repository.get_money(player_id)
            await session.commit()

        logger.debug("Money added: player=%s amount=%s", player_id, amount)
        return MoneyChangeResult(
            player_id=player_id,
            amount=amount,
            balance_after=self._require_balance(balance_after),
        )

    async def add_money_in_transaction(
        self, session: AsyncSession, player_id: int, amount: int
    ) -> MoneyChangeResult:
        """Credit a wallet inside a caller-owned atomic transaction."""
        if amount <= 0:
            raise InvalidAmountError("amount must be a positive integer")

        repository = PlayerRepository(session)
        if not await repository.exists(player_id):
            raise PlayerNotFoundError(f"player_id={player_id} not found")
        if not await repository.add_money(player_id, amount):
            raise PlayerNotFoundError(f"player_id={player_id} not found")
        balance_after = await repository.get_money(player_id)
        return MoneyChangeResult(
            player_id=player_id,
            amount=amount,
            balance_after=self._require_balance(balance_after),
        )

    async def remove_money_in_transaction(
        self, session: AsyncSession, player_id: int, amount: int
    ) -> MoneyChangeResult:
        """Debit a wallet inside a caller-owned transaction.

        Business purchases need the wallet debit and the new ownership row to
        commit atomically. This method reuses the same Wallet/Money service
        rules as :meth:`remove_money`, but deliberately leaves commit/rollback
        to the owning service.
        """
        if amount <= 0:
            raise InvalidAmountError("amount must be a positive integer")

        repository = PlayerRepository(session)
        if not await repository.exists(player_id):
            raise PlayerNotFoundError(f"player_id={player_id} not found")
        removed = await repository.remove_money_if_enough(player_id, amount)
        if not removed:
            if not await repository.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            raise InsufficientFundsError(
                f"player_id={player_id} cannot afford {amount}"
            )
        balance_after = await repository.get_money(player_id)
        return MoneyChangeResult(
            player_id=player_id,
            amount=amount,
            balance_after=self._require_balance(balance_after),
        )

    async def remove_money(self, player_id: int, amount: int) -> MoneyChangeResult:
        """Debit the wallet; refuses to overdraw it.

        Raises:
            InvalidAmountError: If ``amount`` is not a positive integer.
            PlayerNotFoundError: If the player does not exist.
            InsufficientFundsError: If the balance is lower than ``amount``.
        """
        if amount <= 0:
            raise InvalidAmountError("amount must be a positive integer")

        async with self._session_factory() as session:
            repository = PlayerRepository(session)
            if not await repository.exists(player_id):
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            removed = await repository.remove_money_if_enough(player_id, amount)
            if not removed:
                if not await repository.exists(player_id):
                    raise PlayerNotFoundError(f"player_id={player_id} not found")
                raise InsufficientFundsError(
                    f"player_id={player_id} cannot afford {amount}"
                )
            balance_after = await repository.get_money(player_id)
            await session.commit()

        logger.debug("Money removed: player=%s amount=%s", player_id, amount)
        return MoneyChangeResult(
            player_id=player_id,
            amount=amount,
            balance_after=self._require_balance(balance_after),
        )

    # --- Helpers -----------------------------------------------------------

    @staticmethod
    def _require_balance(balance: int | None) -> int:
        # The existence checks above make this unreachable; it keeps typing honest.
        assert balance is not None, "balance disappeared inside its own transaction"
        return balance
