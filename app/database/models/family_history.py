"""FamilyHistory ORM model — the append-only timeline of a family.

Where ``relationship_events`` records interactions inside a marriage,
``family_history`` records *milestones across* marriages (wedding, divorce,
birth, discovery, forced divorce) for both players at once, so a future
«تاریخچه خانواده» screen needs one indexed query and no joins. Rows are never
updated or deleted by game code.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

EVENT_MARRIAGE: str = "marriage"
EVENT_DIVORCE: str = "divorce"
EVENT_FORCED_DIVORCE: str = "forced_divorce"
EVENT_BIRTH: str = "birth"
EVENT_PREGNANCY: str = "pregnancy"
EVENT_CHEATING_DISCOVERED: str = "cheating_discovered"
EVENT_MARRIAGE_REQUEST: str = "marriage_request"
EVENT_REQUEST_REJECTED: str = "request_rejected"
EVENT_REQUEST_EXPIRED: str = "request_expired"


class FamilyHistory(Base):
    """One family milestone, attributed to up to two players.

    Fields:
        id: Primary key.
        marriage_id: Related marriage (``None`` when the milestone happened
            before any marriage existed, e.g. a rejected proposal).
        player_id: The player this row belongs to — one row per player is
            written for shared milestones so each spouse keeps their own
            timeline without a join.
        other_player_id: The other party, if any.
        event_type: One of the ``EVENT_*`` constants.
        amount: Money involved (Mahriyeh, fine), 0 when not about money.
        quality_delta: How much the relationship quality moved, 0 when the
            milestone was not about the relationship.
        social_penalty: Reputation damage added by this milestone.
        note: Short human-readable text (already localized Persian).
        created_at: When the milestone happened (UTC).
    """

    __tablename__ = "family_history"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    marriage_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("marriages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    other_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )

    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    quality_delta: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    social_penalty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<FamilyHistory id={self.id} player={self.player_id} "
            f"type={self.event_type!r} marriage={self.marriage_id}>"
        )
