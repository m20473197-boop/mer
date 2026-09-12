"""Historical price changes for the Iranian market."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class IranMarketPriceHistory(Base):
    """One immutable price change for one asset and one update cycle."""

    __tablename__ = "iran_market_price_history"
    __table_args__ = (
        UniqueConstraint(
            "asset_id",
            "cycle_id",
            name="uq_iran_market_history_asset_cycle",
        ),
        Index("ix_iran_market_history_asset_time", "asset_id", "recorded_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    asset_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("iran_market_assets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    previous_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    new_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    change_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    update_type: Mapped[str] = mapped_column(String(32), nullable=False)
    cycle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<IranMarketPriceHistory asset_id={self.asset_id} "
            f"new_price={self.new_price} direction={self.direction!r}>"
        )
