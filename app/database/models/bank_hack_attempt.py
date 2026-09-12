"""Fictional attempts to hack another player's L.I.R bank account."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

BANK_HACK_COMPLETED = "completed"
BANK_HACK_FAILED = "failed"
BANK_HACK_PENDING = "pending"


class BankHackAttempt(Base):
    __tablename__ = "bank_hack_attempts"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_bank_hack_attempts_status",
        ),
        CheckConstraint("configured_amount > 0", name="ck_bank_hack_configured_positive"),
        CheckConstraint("transferred_amount >= 0", name="ck_bank_hack_transferred_nonnegative"),
        Index("ix_bank_hack_attacker_created", "attacker_player_id", "created_at"),
        Index("ix_bank_hack_target_created", "target_player_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("crime_activities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    attacker_player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_bank_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("bank_accounts.id", ondelete="SET NULL"), nullable=True
    )
    configured_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transferred_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BANK_HACK_PENDING, server_default=text("'pending'")
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
