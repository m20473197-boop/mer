"""Persistent player holdings for the player-facing Iranian market."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class IranMarketHolding(Base):
    """The aggregate quantity of one market asset owned by one player."""

    __tablename__ = "iran_market_holdings"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_iran_market_holdings_positive_quantity"),
        UniqueConstraint(
            "owner_player_id",
            "asset_id",
            name="uq_iran_market_holdings_owner_asset",
        ),
        Index("ix_iran_market_holdings_owner", "owner_player_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    owner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iran_market_assets.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # USD and coin are counted in units; GOLD18 is counted in grams.
    quantity: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<IranMarketHolding owner={self.owner_player_id} "
            f"asset={self.asset_id} quantity={self.quantity}>"
        )
