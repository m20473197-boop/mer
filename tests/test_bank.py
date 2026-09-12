"""Focused coverage for the separate exact-integer Iranian bank ledger."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.services import ServiceRegistry
from app.services.bank_service import (
    BankInsufficientBalanceError,
    BankInvalidCardError,
    BankRecipientNotFoundError,
    BankSelfTransferError,
)
from app.game.shared.errors import InsufficientFundsError


async def _register(services: ServiceRegistry, telegram_id: int, name: str):
    return await services.players.register_or_get(
        telegram_user_id=telegram_id,
        username=f"user{telegram_id}",
        display_name=name,
    )


@pytest.mark.asyncio
async def test_every_player_gets_one_persistent_unique_card(services, db):
    first = await _register(services, 1001, "اول")
    second = await _register(services, 1002, "دوم")

    first_account = await services.bank.get_account(first.player_id, process_interest=False)
    same_account = await services.bank.ensure_account(first.player_id)
    second_account = await services.bank.get_account(second.player_id, process_interest=False)

    assert same_account.account_id == first_account.account_id
    assert same_account.card_number == first_account.card_number
    assert first_account.card_number != second_account.card_number
    assert len(first_account.card_number) == 16

    restarted = ServiceRegistry(db.session_factory)
    persisted = await restarted.bank.get_account(first.player_id, process_interest=False)
    assert persisted.account_id == first_account.account_id
    assert persisted.card_number == first_account.card_number


@pytest.mark.asyncio
async def test_deposit_and_withdraw_bridge_wallet_and_bank_atomically(services):
    player = await _register(services, 1010, "کیف پول")
    await services.money.add_money(player.player_id, 1_000)

    deposit = await services.bank.deposit(player.player_id, 600)
    assert deposit.account.balance == 600
    assert deposit.wallet_balance_after == 400

    withdrawal = await services.bank.withdraw(player.player_id, 250)
    assert withdrawal.account.balance == 350
    assert withdrawal.wallet_balance_after == 650

    transactions, total, _, _ = await services.bank.get_history(
        player.player_id, page_size=50
    )
    assert total == 2
    assert {transaction.transaction_type for transaction in transactions} == {
        "deposit",
        "withdrawal",
    }


@pytest.mark.asyncio
async def test_insufficient_wallet_or_bank_does_not_leave_partial_changes(services):
    player = await _register(services, 1020, "کمبود")

    with pytest.raises(InsufficientFundsError):
        await services.bank.deposit(player.player_id, 1)
    assert await services.bank.get_balance(player.player_id) == 0

    await services.money.add_money(player.player_id, 100)
    await services.bank.deposit(player.player_id, 100)
    with pytest.raises(BankInsufficientBalanceError):
        await services.bank.withdraw(player.player_id, 101)

    assert await services.bank.get_balance(player.player_id) == 100
    assert await services.money.get_balance(player.player_id) == 0
    transactions, total, _, _ = await services.bank.get_history(
        player.player_id, page_size=50
    )
    assert total == 1
    assert transactions[0].transaction_type == "deposit"


@pytest.mark.asyncio
async def test_transfer_resolves_card_rechecks_balance_and_writes_two_histories(services):
    sender = await _register(services, 1030, "فرستنده")
    receiver = await _register(services, 1031, "گیرنده")
    receiver_account = await services.bank.get_account(receiver.player_id, process_interest=False)
    await services.money.add_money(sender.player_id, 500)
    await services.bank.deposit(sender.player_id, 500)

    result = await services.bank.transfer(
        sender.player_id, receiver_account.card_number, 275
    )
    assert result.sender_account.balance == 225
    assert result.recipient_account.balance == 275

    sender_history, sender_total, _, _ = await services.bank.get_history(
        sender.player_id, page_size=50
    )
    receiver_history, receiver_total, _, _ = await services.bank.get_history(
        receiver.player_id, page_size=50
    )
    assert sender_total == 2
    assert [row.transaction_type for row in sender_history] == [
        "transfer_sent",
        "deposit",
    ]
    assert receiver_total >= 1
    assert "transfer_received" in [row.transaction_type for row in receiver_history]
    assert result.transaction.reference_id == result.recipient_transaction.reference_id

    with pytest.raises(BankSelfTransferError):
        await services.bank.transfer(sender.player_id, (await services.bank.get_card_number(sender.player_id)), 1)
    with pytest.raises(BankInvalidCardError):
        await services.bank.preview_transfer(sender.player_id, "۱۲۳")
    with pytest.raises(BankRecipientNotFoundError):
        await services.bank.preview_transfer(sender.player_id, "6219869999999999")
    with pytest.raises(BankInsufficientBalanceError):
        await services.bank.transfer(sender.player_id, receiver_account.card_number, 226)


@pytest.mark.asyncio
async def test_daily_interest_is_integer_calendar_once_and_survives_restart(services, db):
    player = await _register(services, 1040, "سود")
    await services.money.add_money(player.player_id, 10_001)
    await services.bank.deposit(player.player_id, 10_001)

    tomorrow = datetime.now(timezone.utc).replace(
        hour=12, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    first = await services.bank.process_interest_for_player(player.player_id, now=tomorrow)
    assert first.interest_amount == 300
    assert first.processed_days == 1
    assert first.account.balance == 10_301

    duplicate = await services.bank.process_interest_for_player(
        player.player_id, now=tomorrow
    )
    assert duplicate.interest_amount == 0
    assert duplicate.processed_days == 0

    restarted = ServiceRegistry(db.session_factory)
    after_restart = await restarted.bank.process_interest_for_player(
        player.player_id, now=tomorrow
    )
    assert after_restart.interest_amount == 0
    assert after_restart.account.balance == 10_301

    transactions, total, _, _ = await restarted.bank.get_history(
        player.player_id, page_size=50
    )
    assert total == 2
    assert [row.transaction_type for row in transactions].count("interest") == 1
    assert [row.amount for row in transactions if row.transaction_type == "interest"] == [300]


@pytest.mark.asyncio
async def test_concurrent_withdrawals_cannot_make_bank_balance_negative(services):
    player = await _register(services, 1050, "همزمان")
    await services.money.add_money(player.player_id, 100)
    await services.bank.deposit(player.player_id, 100)

    outcomes = await asyncio.gather(
        services.bank.withdraw(player.player_id, 75),
        services.bank.withdraw(player.player_id, 75),
        return_exceptions=True,
    )
    successes = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    failures = [outcome for outcome in outcomes if isinstance(outcome, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], BankInsufficientBalanceError)
    assert await services.bank.get_balance(player.player_id) == 25
