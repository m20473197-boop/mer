"""ConstructionProject ORM model — time-based house construction on a parcel."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

STATUS_IN_PROGRESS: str = "in_progress"
STATUS_COMPLETED: str = "completed"
STATUS_CANCELLED: str = "cancelled"


class ConstructionProject(Base):
    """One construction project — never instant, always takes real time.

    The full blueprint is snapshotted onto the project row, so the house that
    gets created on completion is exactly what the player paid for even if
    other systems change in the meantime.

    Fields:
        id: Primary key.
        land_id: The parcel being built on (FK).
        house_id: The produced house — ``None`` until completion.
        owner_player_id: The builder (FK) — the wallet that paid.
        status: ``in_progress`` | ``completed`` | ``cancelled``.
        building_type: ``a`` (آپارتمانی) | ``v`` (ویلایی).
        floors / area_sqm / bedrooms / bathrooms / living_rooms: Blueprint.
        quality: Material grade token ``m`` | ``g`` | ``e``.
        kitchen_type: Snapshot of the derived kitchen grade.
        parking / elevator / storage: Blueprint facilities.
        cost_total: Paid upfront (Toman, exact integer).
        started_at: Construction start (UTC).
        duration_seconds: Planned duration.
        completes_at: started_at + duration_seconds (UTC).
        completed_at: Actual completion (``None`` while in progress).
    """

    __tablename__ = "construction_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    land_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("lands.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    house_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="SET NULL"),
        nullable=True,
    )
    owner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_IN_PROGRESS, index=True
    )

    building_type: Mapped[str] = mapped_column(String(1), nullable=False)
    floors: Mapped[int] = mapped_column(Integer, nullable=False)
    area_sqm: Mapped[int] = mapped_column(Integer, nullable=False)
    bedrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    bathrooms: Mapped[int] = mapped_column(Integer, nullable=False)
    living_rooms: Mapped[int] = mapped_column(Integer, nullable=False)
    quality: Mapped[str] = mapped_column(String(1), nullable=False)
    kitchen_type: Mapped[str] = mapped_column(String(32), nullable=False)
    parking: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    elevator: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    storage: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cost_total: Mapped[int] = mapped_column(BigInteger, nullable=False)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    duration_seconds: Mapped[int] = mapped_column(BigInteger, nullable=False)
    completes_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
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

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ConstructionProject id={self.id} land={self.land_id} "
            f"status={self.status!r} area={self.area_sqm} cost={self.cost_total}>"
        )
