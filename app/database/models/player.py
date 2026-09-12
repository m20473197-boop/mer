"""The Player ORM model — exactly one row per Telegram user."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import constants
from app.database.models.base import Base


class Player(Base):
    """A game profile, linked 1:1 to a Telegram user.

    Notes:
        * ``telegram_user_id`` is unique — the database itself guarantees
          that one Telegram user can never own two profiles.
        * ``money`` is an exact integer amount of Toman (no floats, ever).
        * The game intentionally has NO age attribute; progression is
          expressed purely through ``level`` and ``xp``.
        * ``spouse_player_id`` / ``marriage_id`` / ``married_since`` /
          ``children_count`` are denormalized family pointers — the real
          record lives in ``marriages`` and ``children``; these only let the
          profile screen render without a join.
    """

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, index=True, nullable=False
    )
    username: Mapped[str | None] = mapped_column(
        String(constants.MAX_USERNAME_LENGTH), nullable=True
    )
    display_name: Mapped[str] = mapped_column(
        String(constants.MAX_DISPLAY_NAME_LENGTH), nullable=False
    )

    level: Mapped[int] = mapped_column(nullable=False, default=constants.STARTING_LEVEL)
    xp: Mapped[int] = mapped_column(nullable=False, default=constants.STARTING_XP)
    money: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=constants.STARTING_MONEY
    )

    is_banned: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    # --- Family (denormalized pointers into ``marriages``) ------------------
    # The truth lives in the ``marriages`` row; these columns exist only so the
    # profile screen is a single lookup instead of a join. ``FamilyService``
    # writes both sides of every change atomically with the marriage row.
    spouse_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
        index=True,
    )
    # Plain integer on purpose: a FK here would close a marriages ↔ players
    # cycle and make the schema unorderable for ``create_all``. The enforcing
    # link is ``marriages.husband_player_id`` / ``marriages.wife_player_id``.
    marriage_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    # Marriage date — what the profile shows as «تاریخ ازدواج».
    married_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    children_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
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

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<Player id={self.id} telegram_user_id={self.telegram_user_id} "
            f"level={self.level}>"
        )
