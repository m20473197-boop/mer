"""RelationshipEvent ORM model — one «رابطه» (or cheating) event on a marriage.

These rows are the immutable audit trail of family life: what happened, how
the relationship quality moved, and whether the event rolled a pregnancy. A
pregnancy recorded here is *pending* until its due date passes; the child is
then created by the lazy settler and the row is marked ``settled``.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

# Event kinds
EVENT_RELATIONSHIP: str = "relationship"          # «رابطه»
EVENT_CHEATING_SUCCESS: str = "cheating_success"  # «خیانت», nobody noticed
EVENT_CHEATING_FAILED: str = "cheating_failed"    # «خیانت», the attempt failed
EVENT_CHEATING_DISCOVERED: str = "cheating_discovered"
EVENT_PREGNANCY: str = "pregnancy"                 # created child (birth)
EVENT_FORCED_DIVORCE: str = "forced_divorce"

OUTCOME_NEUTRAL: str = "neutral"
OUTCOME_PREGNANCY: str = "pregnancy"


class RelationshipEvent(Base):
    """A single family interaction (never edited, only appended).

    Fields:
        id: Primary key.
        marriage_id: The marriage this happened in (FK).
        actor_player_id: Who triggered it (FK; ``None`` for system births).
        event_type: One of the ``EVENT_*`` constants.
        outcome: ``neutral`` | ``pregnancy``.
        quality_before / quality_after: Live snapshot of the relationship
            quality, so a profile screen can show how it drifted over time.
        success: Whether the *attempt* succeeded (cheating: the act itself;
            relationship: the moment landed well).
        discovered: Whether a cheating attempt was found out. This is the only
            flag that produces consequences for the spouse.
        social_penalty: Reputation damage applied by this event.
        pregnancy_due_at / birth_child_id: Pending birth (lazy settlement) and
            the child created once it was due.
        settled: Marks a pregnancy event as consumed by the settler — the
            atomic claim that makes concurrent settling race-safe.
        created_at: When the event happened (UTC).
    """

    __tablename__ = "relationship_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    marriage_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("marriages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    event_type: Mapped[str] = mapped_column(String(24), nullable=False)
    outcome: Mapped[str] = mapped_column(
        String(16), nullable=False, default=OUTCOME_NEUTRAL, server_default=text("'neutral'")
    )

    quality_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quality_after: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    discovered: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    social_penalty: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    pregnancy_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    birth_child_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("children.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    settled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<RelationshipEvent id={self.id} marriage={self.marriage_id} "
            f"type={self.event_type!r} outcome={self.outcome!r}>"
        )
