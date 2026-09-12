"""Database access for relationship events (``relationship_events``).

Append-only. Pregnancy settlement claims the pending row atomically so two
settlers can never hand the same baby to the family twice.
"""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.relationship_event import RelationshipEvent


class RelationshipEventRepository:
    """All database operations for the ``relationship_events`` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, event_id: int) -> RelationshipEvent | None:
        return await self._session.get(RelationshipEvent, event_id)

    def add(self, event: RelationshipEvent) -> None:
        self._session.add(event)

    async def mark_settled(self, event_id: int, child_id: int) -> bool:
        """Claim the pregnancy exactly once (race-safe settler guard)."""
        statement = (
            update(RelationshipEvent)
            .where(
                RelationshipEvent.id == event_id,
                RelationshipEvent.settled.is_(False),
            )
            .values(settled=True, birth_child_id=child_id)
        )
        result = await self._session.execute(
            statement, execution_options={"synchronize_session": False}
        )
        return bool(result.rowcount)


__all__ = ["RelationshipEventRepository"]
