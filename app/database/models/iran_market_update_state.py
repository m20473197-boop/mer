"""Singleton state used to schedule and claim Iranian-market updates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class IranMarketUpdateState(Base):
    """Persistent scheduler cursor and short-lived cross-process lease."""

    __tablename__ = "iran_market_update_state"

    # There is exactly one row (id=1). The row survives restarts, so the
    # three-day timer is never reset by creating a new service instance.
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    last_successful_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_attempted_update: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lock_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lock_acquired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(String(256), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
