"""PropertyUpgrade ORM model — the value audit trail of properties."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

PROPERTY_LAND: str = "land"
PROPERTY_HOUSE: str = "house"

KIND_CONSTRUCTION: str = "construction"


class PropertyUpgrade(Base):
    """One value-changing event on a property (audit trail).

    Written inside the same transaction as the change itself:
    * a construction completing (house value created),
    * a renovation completing (house value increased).

    ``value_before`` / ``value_after`` are the dynamic market values around
    the event — this table is the proof that construction and renovation
    really move property values.

    Fields:
        id: Primary key.
        property_type: ``house`` | ``land`` (polymorphic link with
            ``property_id``).
        player_id: Who caused the upgrade (nullable for safety).
        upgrade_kind: ``construction`` | the renovation type code.
        description: Human-readable summary (Persian).
        value_before / value_after: Dynamic market value around the event
            (Toman; ``None`` when not applicable).
        cost: What the upgrade cost the player.
        created_at: When the upgrade completed.
    """

    __tablename__ = "property_upgrades"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    property_type: Mapped[str] = mapped_column(String(8), nullable=False)
    property_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    player_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    upgrade_kind: Mapped[str] = mapped_column(String(24), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    value_before: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    value_after: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    cost: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PropertyUpgrade id={self.id} {self.property_type}#{self.property_id} "
            f"kind={self.upgrade_kind!r} {self.value_before}->{self.value_after}>"
        )
