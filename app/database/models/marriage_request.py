"""MarriageRequest ORM model — a pending «ازدواج» proposal.

A request is created when one player replies to another player's message with
the command, and lives until the target accepts, rejects, the proposer cancels
or it expires. Only *pending* rows are actionable: the accept/reject updates
claim the row atomically (``status == pending`` guard), so two devices racing
can never create two marriages.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

STATUS_PENDING: str = "pending"
STATUS_ACCEPTED: str = "accepted"
STATUS_REJECTED: str = "rejected"
STATUS_CANCELLED: str = "cancelled"
STATUS_EXPIRED: str = "expired"


class MarriageRequest(Base):
    """A one-way marriage proposal between two players.

    Fields:
        id: Primary key.
        proposer_player_id: Who sent «ازدواج» (FK players).
        target_player_id: Who must answer (FK players).
        status: ``pending`` | ``accepted`` | ``rejected`` | ``cancelled`` |
            ``expired``.
        mahriyeh_amount: The Mahriyeh that *would* be stored if accepted —
            quoted up-front so the target sees the number before agreeing.
        message / reject_message: Optional short note (max 256 chars).
        created_at / answered_at / expires_at: Lifecycle timestamps (UTC).
        marriage_id: Set to the created marriage once accepted.

    Uniqueness: a *partial* unique index keeps at most one **pending** request
    per proposer and per target (``ix_marriage_requests_*_pending_unique``) —
    the guard lives in the database, while closed requests (accepted/rejected/
    cancelled/expired) stay in the table as history and never block a new
    proposal. The service pre-checks both rules so players get a friendly
    Persian message instead of an integrity error.
    """

    __tablename__ = "marriage_requests"
    __table_args__ = (
        Index(
            "ix_marriage_requests_proposer_pending_unique",
            "proposer_player_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
        Index(
            "ix_marriage_requests_target_pending_unique",
            "target_player_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    proposer_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    target_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_PENDING, index=True
    )
    mahriyeh_amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    message: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    reject_message: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    marriage_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("marriages.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<MarriageRequest id={self.id} {self.proposer_player_id} -> "
            f"{self.target_player_id} status={self.status!r}>"
        )
