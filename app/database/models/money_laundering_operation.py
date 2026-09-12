"""Scheduled fictional money-laundering operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

LAUNDERING_PENDING = "pending"
LAUNDERING_PROCESSING = "processing"
LAUNDERING_COMPLETED = "completed"
LAUNDERING_FAILED = "failed"


class MoneyLaunderingOperation(Base):
    __tablename__ = "money_laundering_operations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_money_laundering_status",
        ),
        CheckConstraint("amount > 0", name="ck_money_laundering_amount_positive"),
        CheckConstraint("fee_amount >= 0", name="ck_money_laundering_fee_nonnegative"),
        CheckConstraint("final_amount > 0", name="ck_money_laundering_final_positive"),
        Index("ix_money_laundering_player_created", "player_id", "created_at"),
        Index("ix_money_laundering_due", "status", "process_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_id: Mapped[int] = mapped_column(
        ForeignKey("crime_activities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    final_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=LAUNDERING_PENDING, server_default=text("'pending'")
    )
    reward_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=text("0"))
    process_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
