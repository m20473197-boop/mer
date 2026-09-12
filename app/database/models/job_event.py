"""JobEvent model — the audit trail of the time-based salary system.

Every settlement with the employer produces one event, so payments, bonuses,
penalties and delayed payments are all saved and can be replayed later.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

# Event kinds produced by the employer-behaviour roll.
EVENT_NORMAL: str = "normal"
EVENT_BONUS: str = "bonus"
EVENT_MISTAKE: str = "mistake"
EVENT_DELAYED: str = "delayed"

# Payment status of a settlement event.
STATUS_PAID: str = "paid"
STATUS_DELAYED: str = "delayed"


class JobEvent(Base):
    """One settlement event between a player and their employer.

    Fields:
        id: Primary key
        player_id: FK to players.id
        job_id: FK to jobs.id
        employer: Snapshot of the employer name at settlement time
        event_type: ``normal`` | ``bonus`` | ``mistake`` | ``delayed``
        status: ``paid`` (money credited) | ``delayed`` (money withheld)
        worked_minutes: Whole minutes worked in this settlement period
        hourly_salary: The job's hourly salary at settlement time
        gross_salary: Earned salary before bonus/penalty
        bonus_percent / bonus_amount: Optional bonus applied
        penalty_percent / penalty_amount: Optional mistake penalty applied
        final_amount: Actual amount credited (0 when delayed)
        created_at: When the settlement happened
    """

    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employer: Mapped[str] = mapped_column(String(64), nullable=False, default="")

    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)

    worked_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hourly_salary: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    gross_salary: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    bonus_percent: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    bonus_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    penalty_percent: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    penalty_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    final_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<JobEvent id={self.id} player_id={self.player_id} job_id={self.job_id} "
            f"type={self.event_type!r} status={self.status!r} final={self.final_amount}>"
        )
