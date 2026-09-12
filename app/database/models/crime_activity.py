"""Generic audit rows for every fictional خلاف activity."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

CRIME_ACTIVITY_INFORMATION_SELLING = "information_selling"
CRIME_ACTIVITY_MONEY_LAUNDERING = "money_laundering"
CRIME_ACTIVITY_FAKE_DOCUMENT = "fake_document"
CRIME_ACTIVITY_SHOTI = "shoti"
CRIME_ACTIVITY_BANK_HACK = "bank_hack"

CRIME_STATUS_PENDING = "pending"
CRIME_STATUS_PROCESSING = "processing"
CRIME_STATUS_COMPLETED = "completed"
CRIME_STATUS_FAILED = "failed"
CRIME_STATUS_CANCELLED = "cancelled"


class CrimeActivity(Base):
    """One immutable-at-history activity attempt and its final outcome."""

    __tablename__ = "crime_activities"
    __table_args__ = (
        UniqueConstraint("operation_key", name="uq_crime_activities_operation_key"),
        CheckConstraint(
            "activity_type IN ('information_selling', 'money_laundering', "
            "'fake_document', 'shoti', 'bank_hack')",
            name="ck_crime_activities_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')",
            name="ck_crime_activities_status",
        ),
        CheckConstraint("reward_amount >= 0", name="ck_crime_activities_reward_nonnegative"),
        CheckConstraint("fee_amount >= 0", name="ck_crime_activities_fee_nonnegative"),
        Index("ix_crime_activities_actor_created", "actor_player_id", "created_at"),
        Index("ix_crime_activities_type_status", "activity_type", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    activity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    actor_player_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_player_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("players.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=CRIME_STATUS_COMPLETED, server_default=text("'completed'")
    )
    success: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reward_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    fee_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default=text("0"))
    operation_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    details: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CrimeActivity id={self.id} type={self.activity_type!r} status={self.status!r}>"
