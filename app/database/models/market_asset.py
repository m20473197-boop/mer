"""MarketAsset ORM model — economy assets managed by the admin panel."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

CATEGORY_CURRENCY: str = "currency"
CATEGORY_GOLD: str = "gold"
CATEGORY_CRYPTO: str = "crypto"


class MarketAsset(Base):
    """One economy asset (currency / gold / crypto) with a live price.

    Prices are exact integers in Toman (never floats). The admin panel seeds
    a starter catalog (dollar, euro, tether, bitcoin, ethereum, 18k gold,
    Bahar-Azad coin) and the admin updates prices from the real market;
    every change also writes a ``MarketPriceTick`` history row.

    Fields:
        id: Primary key.
        code: Stable unique code (e.g. ``USD``, ``GOLD18``).
        name: Persian display name (e.g. ``دلار آمریکا``).
        category: ``currency`` | ``gold`` | ``crypto``.
        price: Current price in Toman (exact integer).
    """

    __tablename__ = "market_assets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False)

    price: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return f"<MarketAsset code={self.code!r} price={self.price}>"
