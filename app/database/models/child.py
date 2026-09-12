"""Child ORM model — one row per child of a marriage.

Children are deliberately *light* in this stage: parentage, birth date and a
freezable growth stage. The columns that future systems will need (education,
family expenses, growing up) are already here so those systems only add
behaviour, never a schema change.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base

STAGE_NEWBORN: str = "newborn"
STAGE_INFANT: str = "infant"
STAGE_CHILD: str = "child"
STAGE_TEEN: str = "teen"
STAGE_ADULT: str = "adult"

# Future hook: growth stages in order. Nothing advances a child automatically
# yet — ``FamilyService`` exposes the helper so the education system can.
STAGE_ORDER: tuple[str, ...] = (
    STAGE_NEWBORN,
    STAGE_INFANT,
    STAGE_CHILD,
    STAGE_TEEN,
    STAGE_ADULT,
)


class Child(Base):
    """A child born to two players.

    Fields:
        id: Primary key — the child's unique ID.
        marriage_id: The family it was born into (FK).
        father_player_id / mother_player_id: Parentage (FKs to players).
        name: Display name, assigned at birth from the parents' names.
        birth_date: When the birth was settled (UTC).
        birth_year: Solar-Hijri year of birth — mirrors the housing
            ``construction_year`` convention, so age is always *derived*
            from the calendar, never stored and never left to rot.
        growth_stage: ``newborn`` … ``adult``. Stored for display only; the
            future growth system recomputes it from ``birth_date``.
        expenses_total: Accumulated family expenses attributed to this child.
            Always 0 until the family-expenses system exists — the column is
            the integration point, not a feature.
    """

    __tablename__ = "children"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    marriage_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("marriages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    father_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mother_player_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    birth_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    birth_year: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    growth_stage: Mapped[str] = mapped_column(
        String(16), nullable=False, default=STAGE_NEWBORN
    )
    expenses_total: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover — debugging aid only
        return (
            f"<Child id={self.id} marriage={self.marriage_id} "
            f"father={self.father_player_id} mother={self.mother_player_id} "
            f"stage={self.growth_stage!r}>"
        )


def stage_for_age(age_years: int) -> str:
    """Growth stage implied by an age in whole years.

    Pure helper for the future growth system (``Child.growth_stage`` is not
    auto-advanced in this stage).
    """
    if age_years < 2:
        return STAGE_NEWBORN
    if age_years < 7:
        return STAGE_INFANT
    if age_years < 13:
        return STAGE_CHILD
    if age_years < 18:
        return STAGE_TEEN
    return STAGE_ADULT
