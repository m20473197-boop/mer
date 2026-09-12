"""HouseSale ORM model — the audit trail of completed house purchases."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class HouseSale(Base):
    """One completed sale of a house.

    Every purchase — from the system market or from another player — writes
    exactly one immutable row here.

    Fields:
        id: Primary key.
        house_id: The sold house (FK).
        seller_player_id: Previous owner — ``None`` when bought from the
            system market (bank/developer).
        buyer_player_id: New owner (FK).
        price: Agreed price in Toman (exact integer).
        listing_id: The sale listing that produced this sale, when any.
        created_at: When the sale happened.
    """

    __tablename__ = "house_sales"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    house_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    seller_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    buyer_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    listing_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("house_listings.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HouseSale id={self.id} house_id={self.house_id} "
            f"seller={self.seller_player_id} buyer={self.buyer_player_id} "
            f"price={self.price}>"
        )
