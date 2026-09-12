"""XPTransaction model — history of every XP change."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core import constants
from app.database.models.base import Base


class XPTransaction(Base):
    """Records every XP addition or removal.

    Future game modules (jobs, skills, etc.) will call ``LevelService.add_xp``
    with a ``reason`` — this table keeps the full audit trail.

    Attributes:
        id: Primary key.
        player_id: FK to ``players.id``.
        amount: Signed XP change (positive = gain, negative = loss).
        reason: Human-readable reason, e.g. "Completed job", "admin_add".
        created_at: When the transaction happened.
    """

    __tablename__ = "xp_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(
        String(constants.MAX_XP_REASON_LENGTH), nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<XPTransaction id={self.id} player_id={self.player_id} "
            f"amount={self.amount} reason={self.reason!r}>"
        )
