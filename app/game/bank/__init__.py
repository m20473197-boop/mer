"""Pure types for the player-facing 🏦 بانک ایران system."""

from app.game.bank.catalog import (
    BANK_HISTORY_PAGE_SIZE,
    BANK_INTEREST_RATE_PERCENT,
    BANK_INTEREST_ROUNDING_POLICY,
)
from app.game.bank.dto import (
    BankAccountData,
    BankDepositResult,
    BankInterestResult,
    BankTransactionData,
    BankTransferPreview,
    BankTransferResult,
    BankWithdrawalResult,
)

__all__ = [
    "BANK_HISTORY_PAGE_SIZE",
    "BANK_INTEREST_RATE_PERCENT",
    "BANK_INTEREST_ROUNDING_POLICY",
    "BankAccountData",
    "BankDepositResult",
    "BankInterestResult",
    "BankTransactionData",
    "BankTransferPreview",
    "BankTransferResult",
    "BankWithdrawalResult",
]
