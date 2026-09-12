"""RenovationProject ORM model — time-based renovations on a house."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

STATUS_IN_PROGRESS: str = "in_progress"
STATUS_COMPLETED: str = "completed"


class RenovationProject(Base):
    """One renovation job on a house — costs money and takes real time.

    Fields:
        id: Primary key.
        house_id: The house being renovated (FK).
        owner_player_id: Who paid for the renovation (FK; may differ from the
            current house owner if the house is sold mid-renovation).
        renovation_type: One of the ``R_*`` codes from
            ``app/game/realestate/renovation.py``.
        title / description: Snapshots of the quoted work for history screens.
        cost: Paid upfront (Toman, exact integer).
        status: ``in_progress`` | ``completed``.
        started_at / completes_at / completed_at: Time tracking (UTC).
    """

    __tablename__ = "renovation_projects"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    house_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("houses.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    renovation_type: Mapped[str] = mapped_column(String(2), nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(128), nullable=False, default="")

    cost: Mapped[int] = mapped_column(BigInteger, nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STATUS_IN_PROGRESS, index=True
    )

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
            f"<RenovationProject id={self.id} house={self.house_id} "
            f"type={self.renovation_type!r} status={self.status!r} cost={self.cost}>"
        )
