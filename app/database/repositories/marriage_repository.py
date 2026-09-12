"""Database access for marriages (the family aggregate root).

Follows the project rule: repositories are the only layer that queries the
database, services own the transaction. Completion-style claims use the same
atomic ``UPDATE … WHERE status = …`` pattern as construction projects, so two
concurrent settlers can never create the same child twice.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.marriage import STATUS_ACTIVE, STATUS_DIVORCED, Marriage


class MarriageRepository:
    """All database operations for the ``marriages`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reads ---------------------------------------------------------------

    async def get_by_id(self, marriage_id: int) -> Marriage | None:
        return await self._session.get(Marriage, marriage_id)

    async def get_active_for_player(self, player_id: int) -> Marriage | None:
        """The player's current marriage, or ``None`` when single."""
        statement = select(Marriage).where(
            or_(
                Marriage.husband_player_id == player_id,
                Marriage.wife_player_id == player_id,
            ),
            Marriage.status == STATUS_ACTIVE,
        )
        return (await self._session.execute(statement)).scalar_one_or_none()

    async def list_by_player(
        self, player_id: int, limit: int = 20, offset: int = 0
    ) -> list[Marriage]:
        """Every marriage this player ever had, newest first."""
        statement = (
            select(Marriage)
            .where(
                or_(
                    Marriage.husband_player_id == player_id,
                    Marriage.wife_player_id == player_id,
                )
            )
            .order_by(Marriage.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list((await self._session.execute(statement)).scalars().all())

    async def list_due_pregnancies(self, now: datetime) -> list[Marriage]:
        """Active marriages whose pending baby is due at or before ``now``."""
        statement = select(Marriage).where(
            Marriage.status == STATUS_ACTIVE,
            Marriage.pregnant_due_at.is_not(None),
            Marriage.pregnant_due_at <= now,
        )
        return list((await self._session.execute(statement)).scalars().all())

    # --- Writes --------------------------------------------------------------

    def add(self, marriage: Marriage) -> None:
        """Stage a new marriage; the owning service commits the transaction."""
        self._session.add(marriage)

    async def set_quality(self, marriage_id: int, quality: int) -> None:
        statement = (
            update(Marriage)
            .where(Marriage.id == marriage_id)
            .values(relationship_quality=quality)
        )
        await self._session.execute(statement, execution_options={"synchronize_session": False})

    async def register_cheating(self, marriage_id: int, quality: int, cheater_player_id: int) -> None:
        """Raise the strike + reputation counters, blame ``cheater`` and set quality."""
        statement = (
            update(Marriage)
            .where(Marriage.id == marriage_id)
            .values(
                relationship_quality=quality,
                cheating_strikes=Marriage.cheating_strikes + 1,
                social_penalties=Marriage.social_penalties + 1,
                cheater_player_id=cheater_player_id,
            )
        )
        await self._session.execute(statement, execution_options={"synchronize_session": False})

    async def start_pregnancy(
        self, marriage_id: int, due_at: datetime, event_id: int | None
    ) -> bool:
        """Claim the "no pending pregnancy" slot atomically.

        ``WHERE pregnant_due_at IS NULL`` means a concurrent caller that lost
        the race gets ``False`` instead of queueing a second baby.
        """
        statement = (
            update(Marriage)
            .where(
                Marriage.id == marriage_id,
                Marriage.status == STATUS_ACTIVE,
                Marriage.pregnant_due_at.is_(None),
            )
            .values(pregnant_due_at=due_at, pregnancy_event_id=event_id)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def claim_birth(self, marriage_id: int) -> bool:
        """Claim a due pregnancy exactly once (race-safe settler guard)."""
        statement = (
            update(Marriage)
            .where(
                Marriage.id == marriage_id,
                Marriage.status == STATUS_ACTIVE,
                Marriage.pregnant_due_at.is_not(None),
            )
            .values(pregnant_due_at=None, pregnancy_event_id=None)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def end(self, marriage_id: int, when: datetime) -> bool:
        """Divorce a marriage — only if it is still active.

        The status guard doubles as the lock: a concurrent divorce that loses
        the race returns ``False`` and never double-pays the Mahriyeh.
        """
        statement = (
            update(Marriage)
            .where(Marriage.id == marriage_id, Marriage.status == STATUS_ACTIVE)
            .values(
                status=STATUS_DIVORCED, ended_at=when, pregnant_due_at=None, pregnancy_event_id=None
            )
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)

    async def mark_mahriyeh_paid(self, marriage_id: int) -> None:
        statement = (
            update(Marriage)
            .where(Marriage.id == marriage_id)
            .values(mahriyeh_paid=True)
        )
        await self._session.execute(statement, execution_options={"synchronize_session": False})

    async def spouse_id_of(self, marriage: Marriage, player_id: int) -> int | None:
        """The other half of ``marriage`` (``None`` if the player is not in it)."""
        if marriage.husband_player_id == player_id:
            return marriage.wife_player_id
        if marriage.wife_player_id == player_id:
            return marriage.husband_player_id
        return None

__all__ = ["MarriageRepository"]
