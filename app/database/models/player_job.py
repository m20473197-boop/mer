"""PlayerJob model — relationship between players and their current job."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class PlayerJob(Base):
    """Tracks a player's active job.

    Fields:
        id: Primary key
        player_id: FK to players.id, unique (one active job per player)
        job_id: FK to jobs.id
        started_at / start_time: When player started this job
        last_work_time: Last time player worked (for cooldown)
        total_earnings / total_income: Total earnings from this job
        created_at: Record creation
        updated_at: Record update

    Constraint: One player can have only one active job at a time (unique player_id).
    """

    __tablename__ = "player_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    job_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_work_time: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    total_earnings: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
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

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PlayerJob id={self.id} player_id={self.player_id} job_id={self.job_id}>"

    # Compatibility aliases per spec
    @property
    def start_time(self) -> datetime:
        return self.started_at

    @property
    def total_income(self) -> int:
        return self.total_earnings
