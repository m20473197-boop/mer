"""Job model — defines available jobs in the game."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core import constants
from app.database.models.base import Base


class Job(Base):
    """A job definition (e.g. Worker, Employee, Specialist).

    Fields:
        id: Primary key
        name: Job name (e.g. "کارگر")
        description: Job description
        salary: Legacy per-action income (Toman, exact integer) — kept for
            backward compatibility; the time-based system uses ``hourly_salary``.
        hourly_salary: Income per hour of work (Toman, exact integer)
        employer: Name of the employer (صاحبکار)
        cooldown: Cooldown in seconds between work actions (legacy)
        required_level: Minimum player level to apply
        required_skill: Optional skill requirement (nullable, for future)
        is_active: Whether job is currently available
        created_at: When job was created
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    salary: Mapped[int] = mapped_column(BigInteger, nullable=False)
    hourly_salary: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default=text("0")
    )
    employer: Mapped[str] = mapped_column(
        String(64), nullable=False, default="", server_default=text("''")
    )
    cooldown: Mapped[int] = mapped_column(Integer, nullable=False, default=300)
    required_level: Mapped[int] = mapped_column(
        Integer, nullable=False, default=constants.STARTING_LEVEL
    )
    required_skill: Mapped[str | None] = mapped_column(
        String(64), nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Job id={self.id} name={self.name!r} hourly_salary={self.hourly_salary} "
            f"employer={self.employer!r} level={self.required_level}>"
        )
