"""Owned business model for the predefined Business System."""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class Business(Base):
    """One business started by one player.

    ``business_type`` is always validated against the code catalog by
    ``BusinessService``; players never supply an arbitrary business row. The
    financial fields are snapshots of the configured terms at purchase time,
    so rebalancing the catalog does not silently rewrite an existing owner's
    deal.
    """

    __tablename__ = "businesses"
    __table_args__ = (
        UniqueConstraint(
            "owner_player_id",
            "business_type",
            name="uq_businesses_owner_player_type",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    owner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    business_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)

    startup_cost: Mapped[int] = mapped_column(BigInteger, nullable=False)
    min_daily_income: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_daily_income: Mapped[int] = mapped_column(BigInteger, nullable=False)

    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    balance: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    latest_daily_income: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    last_income_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, default=None
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
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

    @property
    def latest_income(self) -> int:
        """Short alias used by some callers when rendering balances."""
        return self.latest_daily_income

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<Business id={self.id} owner_player_id={self.owner_player_id} "
            f"type={self.business_type!r} balance={self.balance}>"
        )
