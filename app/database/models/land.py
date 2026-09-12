"""Land ORM model — every ownable parcel in the game."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class Land(Base):
    """One unique land parcel.

    Fields:
        id: Primary key — the land's unique ID.
        owner_player_id: FK to players.id — ``None`` means the parcel is on
            the system land market and can be bought by anyone.
        city / neighborhood: Location (must exist in the housing catalog).
        area_sqm: Parcel size in square meters.
        location_quality: Human label of how prime the location is
            (لوکس/عالی/خوب/متوسط) — derived from the neighborhood multiplier
            at creation. Pricing itself always uses the live multiplier.
        built_house_id: FK to houses.id — set when a construction project on
            this parcel completes, so a parcel can only ever be built on once.

    The market value is intentionally **not stored**: it is recomputed
    dynamically from city, neighborhood, size and the live market conditions
    (see ``app/game/realestate/land_pricing.py``), so economic changes move
    every parcel's value automatically. ``price_override_per_mille`` is the
    only exception: when an admin sets it, the services scale the dynamic
    value by it; ``None`` (the default) means a purely dynamic price.
    """

    __tablename__ = "lands"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    city: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    neighborhood: Mapped[str] = mapped_column(String(64), nullable=False)

    area_sqm: Mapped[int] = mapped_column(Integer, nullable=False)
    location_quality: Mapped[str] = mapped_column(String(16), nullable=False)

    owner_player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    built_house_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="SET NULL"),
        nullable=True,
    )

    price_override_per_mille: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
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
            f"<Land id={self.id} city={self.city!r} "
            f"neighborhood={self.neighborhood!r} area={self.area_sqm} "
            f"owner={self.owner_player_id} built_house={self.built_house_id}>"
        )
