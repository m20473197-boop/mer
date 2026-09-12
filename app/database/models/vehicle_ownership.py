"""Persistent player-owned vehicle records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

VEHICLE_OWNERSHIP_OWNED: str = "owned"
VEHICLE_OWNERSHIP_INACTIVE: str = "inactive"


class VehicleOwnership(Base):
    """A purchase of one predefined vehicle model by one player."""

    __tablename__ = "vehicle_ownerships"
    __table_args__ = (
        CheckConstraint("purchase_price > 0", name="ck_vehicle_ownerships_positive_price"),
        CheckConstraint(
            "status IN ('owned', 'inactive')",
            name="ck_vehicle_ownerships_status",
        ),
        # Selling is intentionally not implemented, but the partial unique
        # index makes repeated/concurrent purchase callbacks idempotent for a
        # player/model pair and leaves room for future inactive records.
        Index(
            "uq_vehicle_active_owner_model",
            "owner_player_id",
            "vehicle_model_id",
            unique=True,
            sqlite_where=text("status = 'owned'"),
            postgresql_where=text("status = 'owned'"),
        ),
        Index("ix_vehicle_ownerships_owner", "owner_player_id", "purchased_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    owner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
    )
    vehicle_model_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("vehicle_models.id", ondelete="RESTRICT"),
        nullable=False,
    )
    purchase_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    purchased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VEHICLE_OWNERSHIP_OWNED, server_default=text("'owned'")
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VehicleOwnership id={self.id} owner={self.owner_player_id} "
            f"model={self.vehicle_model_id} status={self.status!r}>"
        )
