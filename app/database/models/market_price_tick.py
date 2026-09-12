"""MarketPriceTick ORM model — price history of economy assets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class MarketPriceTick(Base):
    """One historical price point of a market asset.

    Written on every admin price change (and once per asset at seeding), so
    the admin panel can show how a price moved over time. Old ticks can be
    pruned from 🗄 Database Tools.

    Fields:
        id: Primary key.
        asset_id: The asset (FK, cascade delete).
        price: The price in Toman at that moment (exact integer).
        created_at: When the price was recorded.
    """

    __tablename__ = "market_price_ticks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    asset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("market_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return f"<MarketPriceTick asset={self.asset_id} price={self.price}>"
