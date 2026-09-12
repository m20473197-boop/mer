"""Persistent one-to-one bank accounts for players."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

BANK_ACCOUNT_ACTIVE: str = "active"
BANK_ACCOUNT_CLOSED: str = "closed"


class BankAccount(Base):
    """One persistent Iranian bank account per player.

    The balance is deliberately separate from ``players.money``. Wallet
    changes are made through ``MoneyService``; bank balance changes stay in
    this table and are committed in the same transaction by ``BankService``.
    """

    __tablename__ = "bank_accounts"
    __table_args__ = (
        UniqueConstraint("player_id", name="uq_bank_accounts_player"),
        UniqueConstraint("card_number", name="uq_bank_accounts_card"),
        CheckConstraint("balance >= 0", name="ck_bank_accounts_non_negative_balance"),
        CheckConstraint(
            "status IN ('active', 'closed')",
            name="ck_bank_accounts_status",
        ),
        Index("ix_bank_accounts_status", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    balance: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    card_number: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default=BANK_ACCOUNT_ACTIVE,
        server_default=text("'active'"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    last_interest_processed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<BankAccount id={self.id} player={self.player_id} "
            f"card={self.card_number!r} balance={self.balance}>"
        )
