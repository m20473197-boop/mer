"""Database model for the four player-facing Iranian market assets."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class IranMarketAsset(Base):
    """One persistent USD/gold/coin/housing market reference quote."""

    __tablename__ = "iran_market_assets"
    __table_args__ = (
        UniqueConstraint("code", name="uq_iran_market_assets_code"),
        Index("ix_iran_market_assets_active", "is_active"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    category: Mapped[str] = mapped_column(String(16), nullable=False, index=True)

    # External quotes are nullable only before the first successful provider
    # response. Once a valid value exists, failures never write null/zero.
    current_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    previous_price: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    base_value: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    last_successful_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempted_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
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

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<IranMarketAsset code={self.code!r} "
            f"current_price={self.current_price}>"
        )
