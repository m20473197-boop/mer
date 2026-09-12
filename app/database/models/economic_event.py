"""EconomicEvent ORM model — admin-created market events and crises."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Float, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class EconomicEvent(Base):
    """One economic event that scales all real-estate prices.

    While an event is *live* (``is_active`` and ``starts_at <= now <=
    ends_at``), its ``multiplier`` multiplies the effective market factor —
    e.g. a crisis with multiplier ``1.35`` raises every house/land price and
    every construction/renovation cost by 35%. Expired events are switched
    off by ``AdminService.settle_events()`` (run at startup and whenever the
    economy screen is opened).

    Fields:
        id: Primary key.
        name: Short Persian name (e.g. ``بحران اقتصادی``).
        description: Longer Persian description.
        multiplier: Price multiplier (float, e.g. 1.35 or 0.85).
        starts_at / ends_at: The live window (UTC).
        is_active: ``False`` once ended early or expired.
        created_by: Admin Telegram user ID that created it.
    """

    __tablename__ = "economic_events"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")

    multiplier: Mapped[float] = mapped_column(Float, nullable=False)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_by: Mapped[int] = mapped_column(BigInteger, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<EconomicEvent id={self.id} name={self.name!r} "
            f"x{self.multiplier} active={self.is_active}>"
        )
