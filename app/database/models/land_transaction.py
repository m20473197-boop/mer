"""LandTransaction ORM model — the money audit trail of the land market."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

TX_MARKET_PURCHASE: str = "market_purchase"   # player buys from system market


class LandTransaction(Base):
    """One money movement caused by the land market.

    Fields:
        id: Primary key.
        land_id: The traded parcel (FK).
        payer_player_id: Who paid (FK players).
        payee_player_id: Who received — ``None`` → system market.
        amount: Amount moved (Toman, exact integer).
        transaction_type: One of the ``TX_*`` constants.
        note: Short human-readable note.
        created_at: When the money moved.
    """

    __tablename__ = "land_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    land_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payer_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    payee_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )

    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(24), nullable=False)
    note: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<LandTransaction id={self.id} land={self.land_id} "
            f"amount={self.amount} payer={self.payer_player_id}>"
        )
