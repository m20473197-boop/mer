"""Persisted predefined car-model configuration."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base
from app.game.vehicle.catalog import VEHICLE_MODEL_AVAILABLE


class VehicleModel(Base):
    """One dealership model; players cannot create rows of this table."""

    __tablename__ = "vehicle_models"
    __table_args__ = (
        CheckConstraint("purchase_price > 0", name="ck_vehicle_models_positive_price"),
        CheckConstraint(
            "availability_status IN ('available', 'unavailable')",
            name="ck_vehicle_models_availability_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    purchase_price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    availability_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=VEHICLE_MODEL_AVAILABLE, server_default=text("'available'")
    )
    # The current future activity metadata is deliberately small. More tags
    # can be added later without changing Telegram handlers.
    shoti_eligible: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<VehicleModel id={self.id} code={self.code!r} "
            f"price={self.purchase_price} status={self.availability_status!r}>"
        )
