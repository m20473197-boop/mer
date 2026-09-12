"""LevelUpHistory model — records every level up event."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class LevelUpHistory(Base):
    """Stores level-up events for future rewards and analytics.

    When a player levels up, we store old_level, new_level and timestamp.
    This prepares the system for future reward logic without implementing
    random rewards yet.
    """

    __tablename__ = "level_up_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    old_level: Mapped[int] = mapped_column(Integer, nullable=False)
    new_level: Mapped[int] = mapped_column(Integer, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<LevelUpHistory id={self.id} player_id={self.player_id} "
            f"{self.old_level}->{self.new_level}>"
        )
