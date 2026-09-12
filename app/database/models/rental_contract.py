"""RentalContract ORM model — player-to-player tenancy agreements."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class RentalContract(Base):
    """An active (or historical) rental agreement.

    There are no NPC renters or landlords — both sides are always players.

    Fields:
        id: Primary key.
        house_id: The rented house (FK).
        owner_player_id: The landlord player (FK).
        tenant_player_id: The tenant player (FK).
        monthly_rent: Rent per 30-day period (Toman).
        deposit: Refundable deposit paid at contract start (رهن).
        listing_id: The rent listing that produced this contract, when any.
        started_at: Contract start (UTC).
        next_due_at: When the next monthly rent payment is due (UTC).
        is_active: ``False`` once either side ends the contract.
        ended_at: When the contract was ended (``None`` while active).
    """

    __tablename__ = "rental_contracts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    house_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    monthly_rent: Mapped[int] = mapped_column(BigInteger, nullable=False)
    deposit: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    listing_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("house_listings.id", ondelete="SET NULL"),
        nullable=True,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    next_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
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

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<RentalContract id={self.id} house_id={self.house_id} "
            f"owner={self.owner_player_id} tenant={self.tenant_player_id} "
            f"rent={self.monthly_rent} active={self.is_active}>"
        )
