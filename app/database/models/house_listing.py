"""HouseListing ORM model — a house offered for sale or rent by its owner."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

LISTING_SALE: str = "sale"
LISTING_RENT: str = "rent"

STATUS_ACTIVE: str = "active"
STATUS_CLOSED: str = "closed"


class HouseListing(Base):
    """An owner's offer on the market (player-to-player sale or rent).

    Fields:
        id: Primary key.
        house_id: The listed house (FK).
        owner_player_id: The listing owner — ``None`` only if the system
            market itself lists a house (currently the system market needs no
            listing rows; prices are computed dynamically).
        listing_type: ``sale`` | ``rent``.
        price: For ``sale`` the asking price; for ``rent`` the monthly rent.
        deposit: Refundable deposit (رهن) — rent listings only.
        status: ``active`` | ``closed`` (sold/rented/cancelled).
        closed_at: When the listing was closed (``None`` while active).

    House type constants live in this module (``LISTING_*`` / ``STATUS_*``).
    """

    __tablename__ = "house_listings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    house_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    listing_type: Mapped[str] = mapped_column(String(8), nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deposit: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default=STATUS_ACTIVE)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<HouseListing id={self.id} house_id={self.house_id} "
            f"type={self.listing_type!r} price={self.price} status={self.status!r}>"
        )
