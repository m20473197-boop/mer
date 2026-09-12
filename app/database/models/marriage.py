"""Marriage ORM model — one row per marriage (active or ended).

The marriage row is the *single source of truth* for a family: who is married
to whom, when it started, the stored Mahriyeh (مهریه), the live relationship
quality and the cheating record. ``players`` keeps a denormalized pointer
(``spouse_player_id`` / ``married_since`` / ``marriage_id``) only so the
profile screen stays a single lookup.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import constants
from app.database.models.base import Base

STATUS_ACTIVE: str = "active"
STATUS_DIVORCED: str = "divorced"


class Marriage(Base):
    """A marriage between two players.

    Fields:
        id: Primary key — the marriage ID.
        husband_player_id: The proposer (FK players). Pays the Mahriyeh by
            default, because Mahriyeh is the price of leaving the marriage.
        wife_player_id: The accepted partner (FK players).
        status: ``active`` | ``divorced`` (a marriage that ends is divorced —
            there is no annulment in the game).
        relationship_quality: Live 0…100 relationship health — driven by
            «رابطه» (up) and «خیانت» (down); never a random per-day value.
        cheating_strikes: How many times a cheating attempt was discovered.
        cheater_player_id: The spouse last caught cheating (drives the
            Mahriyeh waiver and who pays in a forced divorce).
        social_penalties: Reputation damage counter (badnamei) — every
            discovery and every forced divorce raises it. Used by the future
            reputation / society system.
        mahriyeh_amount: Stored at the wedding (never recomputed afterwards),
            so an economy change mid-marriage cannot rewrite a promise.
        mahriyeh_paid: Set when the Mahriyeh has actually been settled.
        pregnant_due_at / pregnancy_event_id: Pending pregnancy, if any — the
            child is created when ``pregnant_due_at`` passes (settled lazily,
            exactly like constructions). ``pregnancy_event_id`` points at the
            ``relationship_events`` row that started it; it is a plain integer
            rather than a FK on purpose, because a FK here would close a
            cycle with ``relationship_events.marriage_id`` and make the schema
            impossible to create.
        started_at / ended_at: Marriage date and divorce date (UTC).
    """

    __tablename__ = "marriages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    husband_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    wife_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_ACTIVE, index=True
    )

    relationship_quality: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=constants.RELATIONSHIP_QUALITY_START,
        server_default=text(str(constants.RELATIONSHIP_QUALITY_START)),
    )
    cheating_strikes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    social_penalties: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    # Who was last caught cheating (``None`` = nobody, or it was resolved).
    # The wronged party divorces for free and owes nothing in a forced
    # divorce, so this has to be a stored fact rather than inferred from the
    # strike counter.
    cheater_player_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )

    mahriyeh_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    mahriyeh_paid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    pregnant_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    pregnancy_event_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
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
            f"<Marriage id={self.id} husband={self.husband_player_id} "
            f"wife={self.wife_player_id} status={self.status!r} "
            f"quality={self.relationship_quality}>"
        )
