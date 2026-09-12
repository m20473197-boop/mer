"""Generic player-to-player listings for the ``🧱 دیوار ایران`` marketplace.

The marketplace intentionally stores a polymorphic asset reference instead of
copying house/land attributes. ``asset_type`` determines which existing
asset table ``asset_id`` points to; the service validates that reference and
ownership in the same transaction before any listing or sale is accepted.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base
from app.game.marketplace.catalog import LISTING_STATUS_ACTIVE


class MarketplaceListing(Base):
    """One seller's offer for one real, existing player-owned asset."""

    __tablename__ = "marketplace_listings"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_marketplace_listings_positive_price"),
        CheckConstraint("asset_id > 0", name="ck_marketplace_listings_positive_asset_id"),
        CheckConstraint(
            "asset_type IN ('house', 'land', 'car')",
            name="ck_marketplace_listings_supported_asset_type",
        ),
        CheckConstraint(
            "status IN ('active', 'sold', 'cancelled')",
            name="ck_marketplace_listings_status",
        ),
        # The application validates ownership, while this partial unique
        # index closes the final duplicate-listing race for SQLite/PostgreSQL.
        Index(
            "uq_marketplace_active_asset",
            "asset_type",
            "asset_id",
            unique=True,
            sqlite_where=text("status = 'active'"),
            postgresql_where=text("status = 'active'"),
        ),
        Index(
            "ix_marketplace_active_created",
            "status",
            "asset_type",
            "created_at",
        ),
        Index(
            "ix_marketplace_seller_status",
            "seller_player_id",
            "status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    seller_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Polymorphic reference: ('house', houses.id), ('land', lands.id), or
    # ('car', vehicle_ownerships.id). The service validates each reference.
    asset_type: Mapped[str] = mapped_column(String(16), nullable=False)
    asset_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=LISTING_STATUS_ACTIVE, server_default="active"
    )
    buyer_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<MarketplaceListing id={self.id} type={self.asset_type!r} "
            f"asset={self.asset_id} seller={self.seller_player_id} "
            f"price={self.price} status={self.status!r}>"
        )
