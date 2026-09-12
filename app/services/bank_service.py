"""Service layer for the separate 🏦 بانک ایران ledger.

The bank balance is not the player's personal wallet. Deposits and withdrawals
bridge the two ledgers by calling ``MoneyService``'s transaction-scoped
methods; transfers and interest only touch bank accounts. All changes and
history rows commit together in one database transaction.

Interest policy: the nominal rate is exactly 3 percent per UTC calendar day
and is computed as ``balance * 3 // 100``. The integer division deliberately rounds
fractions down to the nearest whole Toman. A zero-Toman result marks the day
processed without creating a misleading zero-value payment row, so no day can
be applied twice.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.database.models.bank_account import BANK_ACCOUNT_ACTIVE, BankAccount
from app.database.models.bank_transaction import (
    BANK_TRANSACTION_COMPLETED,
    BANK_TRANSACTION_DEPOSIT,
    BANK_TRANSACTION_INTEREST,
    BANK_TRANSACTION_TRANSFER_RECEIVED,
    BANK_TRANSACTION_TRANSFER_SENT,
    BANK_TRANSACTION_WITHDRAWAL,
    BankTransaction,
)
from app.database.repositories.bank_account_repository import (
    BankAccountRepository,
)
from app.database.repositories.bank_transaction_repository import (
    BankTransactionRepository,
)
from app.database.repositories.player_repository import PlayerRepository
from app.game.bank.catalog import BANK_HISTORY_PAGE_SIZE, BANK_INTEREST_RATE_PERCENT
from app.game.bank.dto import (
    BankAccountData,
    BankDepositResult,
    BankInterestResult,
    BankTransactionData,
    BankTransferPreview,
    BankTransferResult,
    BankWithdrawalResult,
)
from app.game.shared.errors import DomainError, PlayerNotFoundError
from app.services.money_service import MoneyService

logger = logging.getLogger(__name__)

# Multiple ServiceRegistry instances may share one async_sessionmaker during a
# restart test or an in-process worker. A shared mutex prevents SQLite's
# StaticPool from interleaving two transactions on one connection; database
# conditional updates remain the safety net for separate processes.
_BANK_LOCKS: dict[int, asyncio.Lock] = {}


def _shared_bank_lock(session_factory: async_sessionmaker[AsyncSession]) -> asyncio.Lock:
    key = id(session_factory)
    lock = _BANK_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _BANK_LOCKS[key] = lock
    return lock


BANK_CARD_PATTERN = re.compile(r"^\d{16}$")


class BankError(DomainError):
    """Base error for bank-specific validation and business rules."""


class BankAccountNotFoundError(BankError):
    """The target player has no active bank account."""


class BankInvalidAmountError(BankError):
    """The bank amount is not a positive exact integer."""


class BankInsufficientBalanceError(BankError):
    """The bank account cannot cover the requested amount."""


class BankInvalidCardError(BankError):
    """The supplied card number is malformed or not registered."""


class BankSelfTransferError(BankError):
    """A player attempted to transfer to their own card."""


class BankRecipientNotFoundError(BankError):
    """A well-formed card does not belong to a player."""


class BankConcurrencyError(BankError):
    """A bank account disappeared or changed during an atomic operation."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


_CARD_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2
)


def _normalize_card(card_number: str) -> str:
    if not isinstance(card_number, str):
        return ""
    return (
        card_number.strip()
        .translate(_CARD_DIGIT_TRANSLATION)
        .replace(" ", "")
        .replace("-", "")
    )


class BankService:
    """Use cases and transaction boundaries for the Iranian bank."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        money_service: MoneyService | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._money_service = money_service or MoneyService(session_factory)
        shared_lock = _shared_bank_lock(session_factory)
        self._interest_lock = shared_lock
        # Serialize local bank mutations as an extra SQLite/process guard;
        # SQL conditional updates remain the cross-process safety net.
        self._operation_lock = shared_lock
        self._scheduler_task: asyncio.Task[None] | None = None
        self._scheduler_stop: asyncio.Event | None = None

    # ------------------------------------------------------------------
    # Account provisioning and reads
    # ------------------------------------------------------------------

    async def ensure_account(self, player_id: int) -> BankAccountData:
        """Create the player's account once, or return the existing account."""

        async with self._session_factory() as session:
            player = await PlayerRepository(session).get_by_id(player_id)
            if player is None:
                raise PlayerNotFoundError(f"player_id={player_id} not found")
            repository = BankAccountRepository(session)
            try:
                account, _created = await repository.ensure_for_player(player_id)
                await session.commit()
            except IntegrityError:
                # A concurrent registration may have won the unique player
                # constraint. Its account is the authoritative one; never
                # generate a replacement card for this player.
                await session.rollback()
                account = await repository.get_by_player_id(player_id)
                if account is None:
                    raise
        return self._account_data(account)

    async def ensure_all_accounts(self) -> int:
        """Backfill the one-account invariant for players from older installs."""

        created = 0
        async with self._session_factory() as session:
            player_repository = PlayerRepository(session)
            account_repository = BankAccountRepository(session)
            offset = 0
            while True:
                players = await player_repository.list_page(offset, 500)
                if not players:
                    break
                for player in players:
                    _, was_created = await account_repository.ensure_for_player(player.id)
                    created += int(was_created)
                offset += len(players)
            await session.commit()
        return created

    async def get_account(self, player_id: int, *, process_interest: bool = True) -> BankAccountData:
        """Return current account data, applying any due daily interest first."""

        await self.ensure_account(player_id)
        if process_interest:
            await self.process_interest_for_player(player_id)
        async with self._session_factory() as session:
            account = await BankAccountRepository(session).get_by_player_id(player_id)
            if account is None or account.status != BANK_ACCOUNT_ACTIVE:
                raise BankAccountNotFoundError(f"player_id={player_id} has no active account")
            return self._account_data(account)

    async def get_balance(self, player_id: int) -> int:
        return (await self.get_account(player_id)).balance

    async def get_card_number(self, player_id: int) -> str:
        return (await self.get_account(player_id)).card_number

    async def preview_transfer(
        self, sender_player_id: int, card_number: str
    ) -> BankTransferPreview:
        """Resolve a card without changing money, for the confirmation UI."""

        await self.ensure_account(sender_player_id)
        normalized = self._validate_card(card_number)
        async with self._session_factory() as session:
            recipient_account = await BankAccountRepository(session).get_by_card_number(normalized)
            if recipient_account is None:
                raise BankRecipientNotFoundError("recipient card was not found")
            if recipient_account.player_id == sender_player_id:
                raise BankSelfTransferError("sender and recipient must differ")
            recipient = await PlayerRepository(session).get_by_id(recipient_account.player_id)
            if recipient is None:
                raise BankRecipientNotFoundError("recipient player was not found")
            return BankTransferPreview(
                recipient_player_id=recipient.id,
                recipient_name=recipient.display_name,
                recipient_card_number=recipient_account.card_number,
            )

    async def get_history(
        self,
        player_id: int,
        *,
        page: int = 0,
        page_size: int = BANK_HISTORY_PAGE_SIZE,
    ) -> tuple[tuple[BankTransactionData, ...], int, int, int]:
        """Return one page of account history and pagination metadata."""

        if page < 0:
            page = 0
        page_size = max(1, min(int(page_size), 50))
        account = await self.get_account(player_id)
        async with self._session_factory() as session:
            transaction_repository = BankTransactionRepository(session)
            total = await transaction_repository.count_for_account(account.account_id)
            rows = await transaction_repository.get_for_account_page(
                account.account_id,
                offset=page * page_size,
                limit=page_size,
            )
            return (
                tuple(self._transaction_data(row) for row in rows),
                total,
                page,
                page_size,
            )

    # ------------------------------------------------------------------
    # Wallet ↔ bank operations
    # ------------------------------------------------------------------

    async def deposit(
        self,
        player_id: int,
        amount: int,
        *,
        operation_id: str | None = None,
    ) -> BankDepositResult:
        """Debit the wallet and credit the bank atomically."""

        amount = self._validate_amount(amount)
        await self.ensure_account(player_id)
        await self.process_interest_for_player(player_id)
        async with self._operation_lock:
            async with self._session_factory() as session:
                account_repository = BankAccountRepository(session)
                transaction_repository = BankTransactionRepository(session)
                account = await account_repository.get_by_player_id(player_id, for_update=True)
                if account is None:
                    raise BankAccountNotFoundError("bank account was not found")
                wallet_result = await self._money_service.remove_money_in_transaction(
                    session, player_id, amount
                )
                if not await account_repository.add_balance(account.id, amount):
                    raise BankConcurrencyError("bank account could not be credited")
                transaction = await transaction_repository.create(
                    transaction_type=BANK_TRANSACTION_DEPOSIT,
                    amount=amount,
                    status=BANK_TRANSACTION_COMPLETED,
                    sender_account_id=None,
                    receiver_account_id=account.id,
                    sender_player_id=None,
                    receiver_player_id=player_id,
                    reference_id=self._reference_id("DEP", operation_id),
                    description="سپرده‌گذاری از کیف پول",
                )
                await session.commit()
                transaction_data = self._transaction_data(transaction)
        account_data = await self.get_account(player_id, process_interest=False)
        return BankDepositResult(
            account=account_data,
            amount=amount,
            wallet_balance_after=wallet_result.balance_after,
            transaction=transaction_data,
        )

    async def withdraw(
        self,
        player_id: int,
        amount: int,
        *,
        operation_id: str | None = None,
    ) -> BankWithdrawalResult:
        """Debit the bank and credit the wallet atomically."""

        amount = self._validate_amount(amount)
        await self.ensure_account(player_id)
        await self.process_interest_for_player(player_id)
        async with self._operation_lock:
            async with self._session_factory() as session:
                account_repository = BankAccountRepository(session)
                transaction_repository = BankTransactionRepository(session)
                account = await account_repository.get_by_player_id(player_id, for_update=True)
                if account is None:
                    raise BankAccountNotFoundError("bank account was not found")
                if not await account_repository.remove_balance_if_enough(account.id, amount):
                    raise BankInsufficientBalanceError("bank balance is insufficient")
                wallet_result = await self._money_service.add_money_in_transaction(
                    session, player_id, amount
                )
                transaction = await transaction_repository.create(
                    transaction_type=BANK_TRANSACTION_WITHDRAWAL,
                    amount=amount,
                    status=BANK_TRANSACTION_COMPLETED,
                    sender_account_id=account.id,
                    receiver_account_id=None,
                    sender_player_id=player_id,
                    receiver_player_id=None,
                    reference_id=self._reference_id("WDR", operation_id),
                    description="برداشت به کیف پول",
                )
                await session.commit()
                transaction_data = self._transaction_data(transaction)
        account_data = await self.get_account(player_id, process_interest=False)
        return BankWithdrawalResult(
            account=account_data,
            amount=amount,
            wallet_balance_after=wallet_result.balance_after,
            transaction=transaction_data,
        )

    # ------------------------------------------------------------------
    # Bank-to-bank transfer
    # ------------------------------------------------------------------

    async def transfer(
        self,
        sender_player_id: int,
        card_number: str,
        amount: int,
        *,
        operation_id: str | None = None,
    ) -> BankTransferResult:
        """Atomically transfer bank money and append both history entries."""

        amount = self._validate_amount(amount)
        normalized = self._validate_card(card_number)
        await self.ensure_account(sender_player_id)
        await self.process_interest_for_player(sender_player_id)
        async with self._operation_lock:
            async with self._session_factory() as session:
                account_repository = BankAccountRepository(session)
                transaction_repository = BankTransactionRepository(session)
                # Resolve first, then acquire row locks in deterministic account-id
                # order. This avoids a lock-order deadlock for opposite transfers.
                sender_lookup = await account_repository.get_by_player_id(sender_player_id)
                recipient_lookup = await account_repository.get_by_card_number(normalized)
                if sender_lookup is None:
                    raise BankAccountNotFoundError("sender account was not found")
                if recipient_lookup is None:
                    raise BankRecipientNotFoundError("recipient card was not found")
                if recipient_lookup.player_id == sender_player_id:
                    raise BankSelfTransferError("sender and recipient must differ")
                await self._lock_accounts_in_order(
                    account_repository, (sender_lookup.id, recipient_lookup.id)
                )
                sender = await account_repository.get_by_id(sender_lookup.id, for_update=True)
                recipient = await account_repository.get_by_id(recipient_lookup.id, for_update=True)
                if sender is None or recipient is None:
                    raise BankConcurrencyError("an account disappeared during transfer")
                if not await account_repository.remove_balance_if_enough(sender.id, amount):
                    raise BankInsufficientBalanceError("bank balance is insufficient")
                if not await account_repository.add_balance(recipient.id, amount):
                    raise BankConcurrencyError("recipient account could not be credited")
                recipient_player = await PlayerRepository(session).get_by_id(recipient.player_id)
                if recipient_player is None:
                    raise BankRecipientNotFoundError("recipient player was not found")
                reference_id = self._reference_id("TRF", operation_id)
                sent = await transaction_repository.create(
                    transaction_type=BANK_TRANSACTION_TRANSFER_SENT,
                    amount=amount,
                    status=BANK_TRANSACTION_COMPLETED,
                    sender_account_id=sender.id,
                    receiver_account_id=recipient.id,
                    sender_player_id=sender.player_id,
                    receiver_player_id=recipient.player_id,
                    reference_id=reference_id,
                    description="انتقال وجه به کارت مقصد",
                )
                received = await transaction_repository.create(
                    transaction_type=BANK_TRANSACTION_TRANSFER_RECEIVED,
                    amount=amount,
                    status=BANK_TRANSACTION_COMPLETED,
                    sender_account_id=sender.id,
                    receiver_account_id=recipient.id,
                    sender_player_id=sender.player_id,
                    receiver_player_id=recipient.player_id,
                    reference_id=reference_id,
                    description="دریافت انتقال وجه",
                )
                await session.commit()
                sent_data = self._transaction_data(sent)
                received_data = self._transaction_data(received)
        sender_data = await self.get_account(sender_player_id, process_interest=False)
        recipient_data = await self.get_account(recipient_player.id, process_interest=False)
        return BankTransferResult(
            sender_account=sender_data,
            recipient_account=recipient_data,
            amount=amount,
            transaction=sent_data,
            recipient_transaction=received_data,
        )

    # ------------------------------------------------------------------
    # Daily interest
    # ------------------------------------------------------------------

    async def process_interest_for_player(
        self, player_id: int, *, now: datetime | None = None
    ) -> BankInterestResult:
        """Apply each unprocessed calendar day for one account at most once."""

        await self.ensure_account(player_id)
        current = _as_utc(now) or _utc_now()
        async with self._interest_lock:
            async with self._session_factory() as session:
                account_repository = BankAccountRepository(session)
                transaction_repository = BankTransactionRepository(session)
                account = await account_repository.get_by_player_id(player_id)
                if account is None:
                    raise BankAccountNotFoundError("bank account was not found")
                work = await self._process_interest_account(
                    session,
                    account_repository,
                    transaction_repository,
                    account,
                    current,
                )
                await session.commit()
        return work

    async def process_daily_interest(
        self, *, now: datetime | None = None
    ) -> tuple[BankInterestResult, ...]:
        """Process due interest for all active accounts.

        The compare-and-set timestamp claim remains the cross-process guard;
        the in-process lock simply avoids needless contention in one bot.
        """

        current = _as_utc(now) or _utc_now()
        results: list[BankInterestResult] = []
        async with self._interest_lock:
            async with self._session_factory() as session:
                account_repository = BankAccountRepository(session)
                transaction_repository = BankTransactionRepository(session)
                accounts = await account_repository.list_all()
                for account in accounts:
                    work = await self._process_interest_account(
                        session,
                        account_repository,
                        transaction_repository,
                        account,
                        current,
                    )
                    results.append(work)
                await session.commit()
        return tuple(results)

    async def _process_interest_account(
        self,
        session: AsyncSession,
        account_repository: BankAccountRepository,
        transaction_repository: BankTransactionRepository,
        account: BankAccount,
        current: datetime,
    ) -> BankInterestResult:
        previous_raw = account.last_interest_processed_at
        previous = _as_utc(previous_raw)
        if previous is not None and previous.date() >= current.date():
            return BankInterestResult(
                account=self._account_data(account),
                interest_amount=0,
                processed_days=0,
                transactions=(),
            )

        if not await account_repository.claim_interest_processing(
            account.id, previous_raw, current
        ):
            # Another worker already claimed this timestamp. Return a fresh
            # snapshot without applying anything in this transaction.
            fresh = await account_repository.get_by_id(account.id)
            if fresh is None:
                raise BankAccountNotFoundError("bank account was not found")
            return BankInterestResult(
                account=self._account_data(fresh),
                interest_amount=0,
                processed_days=0,
                transactions=(),
            )

        # The claim locks the row, but the account object may have been loaded
        # before a just-committed deposit. Read the current balance after the
        # claim so interest is never calculated from a stale ORM object.
        balance = await self._current_balance(session, account.id)
        first_day = previous.date() + timedelta(days=1) if previous else current.date()
        transactions: list[BankTransactionData] = []
        total_interest = 0
        processed_days = 0
        day = first_day
        while day <= current.date():
            interest = balance * BANK_INTEREST_RATE_PERCENT // 100
            balance += interest
            total_interest += interest
            processed_days += 1
            # A zero result is still a processed day, but it is not a
            # payment and therefore does not create misleading zero-value
            # history noise. Every positive interest payment gets its own row.
            if interest > 0:
                transaction = await transaction_repository.create(
                    transaction_type=BANK_TRANSACTION_INTEREST,
                    amount=interest,
                    status=BANK_TRANSACTION_COMPLETED,
                    sender_account_id=None,
                    receiver_account_id=account.id,
                    sender_player_id=None,
                    receiver_player_id=account.player_id,
                    reference_id=self._reference_id("INT"),
                    description=f"سود روزانه {BANK_INTEREST_RATE_PERCENT} درصد؛ روز {day.isoformat()}",
                    created_at=current,
                )
                transactions.append(self._transaction_data(transaction))
            day += timedelta(days=1)

        if not await account_repository.set_balance_and_last_interest(
            account.id, balance, current
        ):
            raise BankConcurrencyError("interest balance could not be saved")
        account.balance = balance
        account.last_interest_processed_at = current
        return BankInterestResult(
            account=self._account_data(account),
            interest_amount=total_interest,
            processed_days=processed_days,
            transactions=tuple(transactions),
        )

    async def _current_balance(self, session: AsyncSession, account_id: int) -> int:
        from sqlalchemy import select

        result = await session.execute(
            select(BankAccount.balance).where(BankAccount.id == account_id)
        )
        balance = result.scalar_one_or_none()
        if balance is None:
            raise BankAccountNotFoundError("bank account was not found")
        return int(balance)

    # ------------------------------------------------------------------
    # Background scheduler
    # ------------------------------------------------------------------

    async def start_interest_scheduler(self, interval_seconds: int = 3600) -> None:
        """Start an idempotent lightweight daily-interest worker."""

        if self._scheduler_task is not None and not self._scheduler_task.done():
            return
        self._scheduler_stop = asyncio.Event()
        self._scheduler_task = asyncio.create_task(
            self._interest_scheduler_loop(max(60, int(interval_seconds)))
        )

    async def stop_interest_scheduler(self) -> None:
        task = self._scheduler_task
        if task is None:
            return
        if self._scheduler_stop is not None:
            self._scheduler_stop.set()
        try:
            await task
        finally:
            self._scheduler_task = None
            self._scheduler_stop = None

    async def _interest_scheduler_loop(self, interval_seconds: int) -> None:
        stop = self._scheduler_stop
        if stop is None:
            return
        while not stop.is_set():
            try:
                await self.process_daily_interest()
            except Exception:  # pragma: no cover - defensive background guard
                logger.exception("Bank daily-interest processing failed")
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval_seconds)
            except asyncio.TimeoutError:
                continue

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_amount(amount: int) -> int:
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise BankInvalidAmountError("amount must be a positive integer")
        return amount

    @staticmethod
    def _validate_card(card_number: str) -> str:
        normalized = _normalize_card(card_number)
        if not BANK_CARD_PATTERN.fullmatch(normalized):
            raise BankInvalidCardError("card number must contain 16 digits")
        return normalized

    @staticmethod
    async def _lock_accounts_in_order(
        repository: BankAccountRepository, account_ids: Iterable[int]
    ) -> None:
        for account_id in sorted(set(account_ids)):
            account = await repository.get_by_id(account_id, for_update=True)
            if account is None:
                raise BankConcurrencyError("an account disappeared during transfer")

    @staticmethod
    def _reference_id(prefix: str, operation_id: str | None = None) -> str:
        if operation_id:
            # The UI-generated key is persisted in history; cap it to the
            # database column while keeping it stable for duplicate retries.
            return operation_id[:64]
        return f"{prefix}-{token_hex(12)}"

    @staticmethod
    def _account_data(account: BankAccount) -> BankAccountData:
        created = account.created_at or _utc_now()
        updated = account.updated_at or created
        return BankAccountData(
            account_id=account.id,
            player_id=account.player_id,
            balance=int(account.balance),
            card_number=account.card_number,
            created_at=created,
            updated_at=updated,
            last_interest_processed_at=_as_utc(account.last_interest_processed_at),
        )

    @staticmethod
    def _transaction_data(transaction: BankTransaction) -> BankTransactionData:
        return BankTransactionData(
            transaction_id=transaction.id,
            transaction_type=transaction.transaction_type,
            status=transaction.status,
            sender_player_id=transaction.sender_player_id,
            receiver_player_id=transaction.receiver_player_id,
            amount=int(transaction.amount),
            reference_id=transaction.reference_id,
            description=transaction.description,
            created_at=transaction.created_at or _utc_now(),
            sender_account_id=transaction.sender_account_id,
            receiver_account_id=transaction.receiver_account_id,
        )
