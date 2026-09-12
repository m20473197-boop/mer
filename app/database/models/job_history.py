"""JobHistory model — tracks income from job work actions."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class JobHistory(Base):
    """Records each successful job work for statistics and future features.

    Fields:
        id: Primary key
        player_id: FK to players.id
        job_id: FK to jobs.id
        income: Income received (Toman) — also exposed as amount for compatibility
        amount: Alias for income (per spec)
        created_at: When work happened
    """

    __tablename__ = "job_history"

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
    income: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # amount field per spec — same as income, for compatibility
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<JobHistory id={self.id} player_id={self.player_id} job_id={self.job_id} income={self.income}>"

    def __init__(self, **kwargs):
        # Ensure amount and income stay in sync
        if "income" in kwargs and "amount" not in kwargs:
            kwargs["amount"] = kwargs["income"]
        elif "amount" in kwargs and "income" not in kwargs:
            kwargs["income"] = kwargs["amount"]
        super().__init__(**kwargs)
