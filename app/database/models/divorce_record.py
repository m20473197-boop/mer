"""DivorceRecord ORM model — one row per ended marriage (divorce history).

Written in the same transaction as the Mahriyeh transfer, so the divorce
history can never drift from the wallets — the same guarantee the housing
money audit trail gives.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

REASON_MUTUAL: str = "mutual"            # both sides just walk away
REASON_INITIATED: str = "initiated"      # one side paid to leave
REASON_CHEATING: str = "cheating"        # forced by repeated infidelity


class DivorceRecord(Base):
    """The record that a marriage ended.

    Fields:
        id: Primary key.
        marriage_id: The marriage that ended (FK).
        husband_player_id / wife_player_id: Snapshot of the two spouses, so
            history stays readable even if a player row disappears.
        initiator_player_id: Who typed «طلاق» (``None`` when the system forced
            the divorce after repeated cheating).
        mahriyeh_amount: What had to be paid.
        mahriyeh_paid: ``True`` when the money actually moved; ``False`` for a
            waived Mahriyeh (the wronged spouse's right after a discovery) or
            a forced divorce where nothing was owed.
        payer_player_id / payee_player_id: The two wallets involved.
        reason: ``mutual`` | ``initiated`` | ``cheating``.
        children_count: How many children the family had at the moment it
            ended — the number the profile keeps showing afterwards.
        created_at: When the divorce happened (UTC).
    """

    __tablename__ = "divorce_records"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    marriage_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("marriages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
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
    initiator_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    mahriyeh_amount: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    mahriyeh_paid: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    payer_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )
    payee_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )

    reason: Mapped[str] = mapped_column(
        String(16), nullable=False, default=REASON_INITIATED
    )
    children_count: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<DivorceRecord id={self.id} marriage={self.marriage_id} "
            f"reason={self.reason!r} mahriyeh={self.mahriyeh_amount} "
            f"paid={self.mahriyeh_paid}>"
        )
