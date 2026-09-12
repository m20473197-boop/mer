"""Immutable completed ledger entries for the Iranian bank."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

BANK_TRANSACTION_DEPOSIT: str = "deposit"
BANK_TRANSACTION_WITHDRAWAL: str = "withdrawal"
BANK_TRANSACTION_TRANSFER_SENT: str = "transfer_sent"
BANK_TRANSACTION_TRANSFER_RECEIVED: str = "transfer_received"
BANK_TRANSACTION_INTEREST: str = "interest"

BANK_TRANSACTION_COMPLETED: str = "completed"
BANK_TRANSACTION_FAILED: str = "failed"


class BankTransaction(Base):
    """An audit/history row for a completed bank operation.

    Transfers deliberately create two rows, one for each account, while
    sharing ``reference_id``. That makes account history inexpensive and
    preserves a clear sender and receiver entry even if a user only sees one
    side of a transfer.
    """

    __tablename__ = "bank_transactions"
    __table_args__ = (
        UniqueConstraint(
            "reference_id",
            "transaction_type",
            name="uq_bank_transactions_reference_type",
        ),
        CheckConstraint("amount >= 0", name="ck_bank_transactions_non_negative_amount"),
        CheckConstraint(
            "transaction_type IN ('deposit', 'withdrawal', 'transfer_sent', "
            "'transfer_received', 'interest')",
            name="ck_bank_transactions_type",
        ),
        CheckConstraint(
            "status IN ('completed', 'failed')",
            name="ck_bank_transactions_status",
        ),
        Index("ix_bank_transactions_sender_account", "sender_account_id", "created_at"),
        Index("ix_bank_transactions_receiver_account", "receiver_account_id", "created_at"),
        Index("ix_bank_transactions_reference", "reference_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    transaction_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=BANK_TRANSACTION_COMPLETED,
        server_default=text("'completed'"),
    )
    sender_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    receiver_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sender_player_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    receiver_player_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=text("''")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<BankTransaction id={self.id} type={self.transaction_type!r} "
            f"amount={self.amount} status={self.status!r}>"
        )
