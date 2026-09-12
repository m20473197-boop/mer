"""Immutable DTOs for the Iranian bank system."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class BankAccountData:
    """One player's persistent bank account and current balance."""

    account_id: int
    player_id: int
    balance: int
    card_number: str
    created_at: datetime
    updated_at: datetime
    last_interest_processed_at: datetime | None


@dataclass(frozen=True, slots=True)
class BankTransactionData:
    """One completed bank ledger entry."""

    transaction_id: int
    transaction_type: str
    status: str
    sender_player_id: int | None
    receiver_player_id: int | None
    amount: int
    reference_id: str | None
    description: str
    created_at: datetime
    sender_account_id: int | None = None
    receiver_account_id: int | None = None


@dataclass(frozen=True, slots=True)
class BankDepositResult:
    account: BankAccountData
    amount: int
    wallet_balance_after: int
    transaction: BankTransactionData


@dataclass(frozen=True, slots=True)
class BankWithdrawalResult:
    account: BankAccountData
    amount: int
    wallet_balance_after: int
    transaction: BankTransactionData


@dataclass(frozen=True, slots=True)
class BankTransferPreview:
    recipient_player_id: int
    recipient_name: str
    recipient_card_number: str


@dataclass(frozen=True, slots=True)
class BankTransferResult:
    sender_account: BankAccountData
    recipient_account: BankAccountData
    amount: int
    transaction: BankTransactionData
    recipient_transaction: BankTransactionData


@dataclass(frozen=True, slots=True)
class BankInterestResult:
    account: BankAccountData
    interest_amount: int
    processed_days: int
    transactions: tuple[BankTransactionData, ...]
